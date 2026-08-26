"""
AI image generation. Follows whichever provider is set as the chat
provider on the AI Settings page — Gemini (native image-output models) or
Open WebUI (proxies to whatever image backend it's configured with —
ComfyUI, AUTOMATIC1111, etc. — via its own unified images API). Ollama has
no image-generation API of its own, so it's not a valid image-gen
provider even when it's the chat provider.

Called directly from a tool's "Generate" button (Image/Banner/Card, both
top-level sections and Columns cells — see the *_image_generate routes in
admin.py).
"""
import json
import base64
import urllib.request
import urllib.error

from . import assistant

DEFAULT_GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# Gemini's image models don't take literal pixel dimensions — they accept
# one of a small fixed set of aspect ratios. Map the tool's actual target
# size to the closest one so a Banner (wide) doesn't come back square.
_ASPECT_RATIOS = [
    ("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4), ("16:9", 16 / 9),
    ("9:16", 9 / 16), ("3:2", 3 / 2), ("2:3", 2 / 3),
]

IMAGE_GEN_PROVIDERS = ("openwebui", "gemini")


def is_configured(db):
    settings = assistant.get_ai_settings(db)
    if settings["provider"] == "gemini":
        return bool(settings["gemini_api_key"])
    if settings["provider"] == "openwebui":
        return bool(settings["openwebui_url"] and settings["openwebui_api_key"])
    return False


def _closest_aspect_ratio(width, height):
    if not width or not height:
        return "1:1"
    target = width / height
    return min(_ASPECT_RATIOS, key=lambda pair: abs(pair[1] - target))[0]


class ImageGenError(Exception):
    pass


def _size_prompt_suffix(width, height):
    if not (width and height):
        return ""
    return (
        f"\n\nThe image will be used at exactly {width}x{height} pixels "
        f"({'landscape' if width > height else 'portrait' if height > width else 'square'} "
        f"orientation) — compose it to fill that shape cleanly, with the main subject "
        f"framed so it isn't cropped awkwardly at those proportions."
    )


# Keywords that mean the admin is genuinely asking for lettering in the
# image (a sign, a label, a title card, ...) — image models are
# unreliable at rendering legible text at all, tending to produce
# garbled pseudo-text that looks worse than no text. Defaulting to "no
# text" unless the prompt itself asks for it avoids that failure mode
# for the common case (a plain background/photo/illustration) without
# blocking the rare case where text actually is the point.
_TEXT_REQUEST_KEYWORDS = (
    "text", "word", "words", "caption", "sign", "label", "title",
    "writing", "written", "letter", "letters", "typograph", "logo",
    "headline", "quote", "slogan",
)


def _wants_text(prompt):
    lower = prompt.lower()
    return any(kw in lower for kw in _TEXT_REQUEST_KEYWORDS)


def _no_text_suffix(prompt):
    if _wants_text(prompt):
        return ""
    return (
        "\n\nDo not render any text, words, letters, numbers, captions, signage, "
        "typography, menu boards, chalkboard signs, price lists, or price tags "
        "anywhere in the image — a purely visual background/subject, no lettering "
        "or lettered objects of any kind, even blurred or in the background. "
        "(Any text needed goes on top separately, as this tool's own text overlay "
        "— not baked into the generated image, which tends to come out garbled "
        "and unreadable.)"
    )


# A real negative-prompt field, for backends that support one separately
# from the positive prompt (most Stable Diffusion-family workflows behind
# Open WebUI do) — this is more reliable than a positive-prompt suffix
# alone at actually suppressing text, since the model weighs it as "avoid"
# rather than just more text to interpret. Kept in sync with
# _no_text_suffix's reasoning (same opt-out via _wants_text) so both paths
# agree on when text is/isn't wanted.
_NO_TEXT_NEGATIVE_PROMPT = (
    "text, words, letters, numbers, captions, signage, typography, menu board, "
    "chalkboard sign, price list, price tag, watermark, logo, title card, "
    "readable text, blurry text, garbled text"
)


def _negative_prompt(prompt):
    return "" if _wants_text(prompt) else _NO_TEXT_NEGATIVE_PROMPT


def generate_image(db, prompt, width=None, height=None, reference_image_bytes=None, reference_mime="image/png"):
    """
    Generates one image via whichever provider is currently selected for
    chat (Gemini or Open WebUI — see IMAGE_GEN_PROVIDERS). `width`/`height`
    (the exact target slot size, in px) steers aspect ratio/framing, not
    literal output dimensions — folded into the prompt text, which models
    follow far more reliably than a size parameter alone for framing.
    `reference_image_bytes`, if given, is the "keyframe" — an existing
    image the new one should be guided by (style/content/composition),
    sent as image-to-image input rather than text-only generation. Not
    every backend actually honors image-to-image (e.g. a ComfyUI workflow
    behind Open WebUI may be text-to-image only) — if so, it's typically
    just ignored rather than erroring.

    Returns raw image bytes. Raises ImageGenError with a message that's
    safe to show the admin directly.
    """
    settings = assistant.get_ai_settings(db)
    provider = settings["provider"]
    if provider == "gemini":
        return _generate_gemini(settings, prompt, width, height, reference_image_bytes, reference_mime)
    if provider == "openwebui":
        return _generate_openwebui(settings, prompt, width, height, reference_image_bytes, reference_mime)
    raise ImageGenError(
        "Image generation needs Gemini or Open WebUI selected as the AI provider "
        "(Ollama has no image-generation API of its own) — check AI Settings."
    )


def _generate_gemini(settings, prompt, width, height, reference_image_bytes, reference_mime):
    api_key = settings["gemini_api_key"]
    if not api_key:
        raise ImageGenError("Image generation isn't configured — set a Gemini API key on the AI Settings page.")
    model = settings["gemini_image_model"] or DEFAULT_GEMINI_IMAGE_MODEL

    full_prompt = prompt.strip() + _no_text_suffix(prompt) + _size_prompt_suffix(width, height)
    parts = [{"text": full_prompt}]
    if reference_image_bytes:
        parts.insert(0, {
            "inline_data": {
                "mime_type": reference_mime,
                "data": base64.b64encode(reference_image_bytes).decode("ascii"),
            },
        })

    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": _closest_aspect_ratio(width, height)},
        },
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        raise ImageGenError(f"Gemini returned an error ({e.code}): {detail}")
    except urllib.error.URLError as e:
        raise ImageGenError(f"Couldn't reach Gemini: {e.reason}")
    except TimeoutError:
        raise ImageGenError("Gemini took too long to respond.")

    candidates = data.get("candidates") or []
    for cand in candidates:
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])

    # No image in the response — surface whatever text explanation Gemini
    # gave (a safety refusal, usually) instead of a bare "nothing came back".
    text_parts = [
        part.get("text", "")
        for cand in candidates
        for part in (cand.get("content") or {}).get("parts", [])
        if part.get("text")
    ]
    reason = " ".join(text_parts).strip() or "Gemini didn't return an image."
    raise ImageGenError(reason)


def _generate_openwebui(settings, prompt, width, height, reference_image_bytes, reference_mime):
    """Open WebUI's own image-generation API — /api/v1/images/generations,
    OpenAI DALL-E-shaped. It proxies to whatever backend is configured on
    the server side (ComfyUI, AUTOMATIC1111, ...); this app has no idea
    which, or what workflow it runs, so `reference_image_bytes` (i2i) is
    sent as a best-effort `image` field some backends read — a backend
    that's text-to-image only will most likely just ignore it rather than
    error, but that's the backend's choice, not something detectable here.
    """
    base_url = settings["openwebui_url"].rstrip("/")
    api_key = settings["openwebui_api_key"]
    if not (base_url and api_key):
        raise ImageGenError("Image generation isn't configured — set the Open WebUI URL and API key on the AI Settings page.")

    full_prompt = prompt.strip() + _no_text_suffix(prompt) + _size_prompt_suffix(width, height)
    body = {"prompt": full_prompt, "n": 1}
    if width and height:
        body["size"] = f"{width}x{height}"
    if settings["openwebui_image_model"]:
        body["model"] = settings["openwebui_image_model"]
    if reference_image_bytes:
        body["image"] = base64.b64encode(reference_image_bytes).decode("ascii")
    negative = _negative_prompt(prompt)
    if negative:
        # Not part of the OpenAI-images schema Open WebUI's endpoint
        # otherwise follows, but it proxies straight through to whatever
        # backend workflow is configured (ComfyUI, AUTOMATIC1111, ...) —
        # most Stable Diffusion-family workflows read this field directly
        # if it's present, and simply ignore it if their workflow has no
        # negative-prompt input at all, so sending it is safe either way.
        body["negative_prompt"] = negative

    req = urllib.request.Request(
        f"{base_url}/api/v1/images/generations",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        raise ImageGenError(f"Open WebUI returned an error ({e.code}): {detail}")
    except urllib.error.URLError as e:
        raise ImageGenError(f"Couldn't reach Open WebUI: {e.reason}")
    except TimeoutError:
        raise ImageGenError("Open WebUI took too long to respond — image generation backends can be slow; try again.")

    # Response shape varies by Open WebUI version: a plain list, or
    # {"data": [...]} (OpenAI-compatible) — each item either a "url"
    # (relative to this same server) or a "b64_json"/"image" base64 field.
    items = data.get("data") if isinstance(data, dict) else data
    if not items:
        raise ImageGenError("Open WebUI didn't return an image — check its image generation backend is configured and running.")
    item = items[0]
    b64 = item.get("b64_json") or item.get("image")
    if b64:
        return base64.b64decode(b64)
    image_url = item.get("url")
    if image_url:
        if image_url.startswith("/"):
            image_url = base_url + image_url
        img_req = urllib.request.Request(image_url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(img_req, timeout=30) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            raise ImageGenError(f"Open WebUI generated an image but it couldn't be fetched: {e}")
    raise ImageGenError("Open WebUI's response didn't include an image.")
