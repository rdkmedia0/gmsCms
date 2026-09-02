"""
Admin-only AI assistant. Provider-agnostic: OpenWebUI, Ollama, or Gemini,
picked and configured from the Dashboard (AI Settings) — see
get_ai_settings/save_ai_settings. API keys are encrypted at rest (see
app/crypto.py) before ever reaching the database; the .env-based
OPEN_WEBUI_* variables from earlier deployments still work as a fallback
so an existing docker-compose setup keeps working with zero changes, but
are only ever used when nothing's been saved in the Dashboard.

Security model: safety comes from a whitelisted tool surface, not from
trusting the model's judgment. The model can only call the functions
defined below — there is no "run arbitrary code" or "delete" tool, so it
is structurally incapable of destructive changes regardless of what it's
asked or how it's prompted. Read-only tools (list_pages, get_section)
execute immediately so the model can ground its answers in the real site.
Write tools (update_section_content, reformat_section_html) never touch
the database directly — they return a *proposal* that the admin must
explicitly review and click Apply on before anything is saved.

Every provider call is normalized to/from one shape internally —
{"content": str|None, "tool_calls": [{"id", "name", "arguments": dict}]} —
so run_turn() below never needs to know which provider answered it.
"""
import os
import json
import urllib.request
import urllib.error

from flask import render_template

from .db import get_db
from . import crypto

DEFAULT_OPENWEBUI_MODEL = "qwen3-coder"
DEFAULT_OLLAMA_MODEL = "qwen2.5"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

AI_PROVIDERS = ("openwebui", "ollama", "gemini")
PROVIDER_LABELS = {"openwebui": "Open WebUI", "ollama": "Ollama", "gemini": "Google Gemini"}

AI_SETTINGS_KEYS = (
    "ai_provider",
    "openwebui_url", "openwebui_model", "openwebui_image_model", "openwebui_video_model",
    "ollama_url", "ollama_model",
    "gemini_model", "gemini_image_model",
)
# Stored encrypted (app/crypto.py) — never read/written as plain settings rows directly.
AI_SECRET_KEYS = {
    "openwebui_api_key": "openwebui_api_key_enc",
    "gemini_api_key": "gemini_api_key_enc",
}


def _system_prompt():
    """The assistant's persona + full feature-set description — content,
    not code, so it lives in its own template (see CLAUDE.md's "AI prompts
    live in template files" rule) rather than a Python string literal."""
    return render_template("prompts/assistant_system_prompt.j2")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_pages",
            "description": (
                "List all pages on the site with their sections (id, type, a short content "
                "preview). The result also includes one site_zones entry with the active "
                "template's header/sidebar/sidebar_right/footer sections — site-wide chrome "
                "shared by every page, not any one page's own content. Use those section_ids "
                "with get_section/update_section_content exactly like a normal page section."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_section",
            "description": "Get the full current content of one section by id.",
            "parameters": {
                "type": "object",
                "properties": {"section_id": {"type": "integer"}},
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_section_content",
            "description": (
                "Propose new content for a section. This does NOT save anything — it "
                "returns a proposal the admin must approve. IMPORTANT: preserve any "
                "cms-* class already on the section's root element(s) (e.g. class=\"cms-table\" "
                "on a <table>, cms-banner/cms-card-shape/cms-menu wrappers) — those classes are "
                "what apply this site's actual styling; dropping them silently reverts the "
                "element to an unstyled browser default. Fetch the section with get_section "
                "first and copy its existing class/wrapper structure forward, only changing the "
                "content inside it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "integer"},
                    "new_content": {"type": "string", "description": "The full replacement HTML/text content."},
                    "reason": {"type": "string", "description": "One sentence: what changed and why."},
                },
                "required": ["section_id", "new_content", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reformat_section_html",
            "description": (
                "Propose cleaned-up/reformatted HTML for a section (e.g. fix broken tags, "
                "tidy indentation) without changing its visible content or meaning. Does NOT "
                "save anything — returns a proposal the admin must approve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "integer"},
                    "reformatted_html": {"type": "string"},
                },
                "required": ["section_id", "reformatted_html"],
            },
        },
    },
]

WRITE_TOOL_NAMES = {"update_section_content", "reformat_section_html"}


# ---------- Settings (Dashboard-configurable, encrypted secrets) ----------

def get_ai_settings(db):
    """Every field, decrypted where relevant, with env-var fallback for
    openwebui only (the pre-existing docker-compose deployment path) —
    used purely so an existing install with OPEN_WEBUI_* env vars set and
    nothing ever saved in the Dashboard keeps working unchanged. Once the
    admin saves anything here, the DB value wins from then on."""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ({})".format(
            ",".join("?" * (len(AI_SETTINGS_KEYS) + len(AI_SECRET_KEYS)))
        ),
        AI_SETTINGS_KEYS + tuple(AI_SECRET_KEYS.values()),
    ).fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    provider = raw.get("ai_provider") or ""
    if not provider and os.environ.get("OPEN_WEBUI_URL"):
        provider = "openwebui"  # legacy env-only deployment, never configured here
    return {
        "provider": provider if provider in AI_PROVIDERS else "",
        "openwebui_url": raw.get("openwebui_url") or os.environ.get("OPEN_WEBUI_URL", ""),
        "openwebui_api_key": crypto.decrypt(raw.get("openwebui_api_key_enc")) or os.environ.get("OPEN_WEBUI_API_KEY", ""),
        "openwebui_model": raw.get("openwebui_model") or os.environ.get("OPEN_WEBUI_MODEL", DEFAULT_OPENWEBUI_MODEL),
        "openwebui_image_model": raw.get("openwebui_image_model") or os.environ.get("OPEN_WEBUI_IMAGE_MODEL", ""),
        "ollama_url": raw.get("ollama_url") or os.environ.get("OLLAMA_URL", ""),
        "ollama_model": raw.get("ollama_model") or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        "gemini_api_key": crypto.decrypt(raw.get("gemini_api_key_enc")) or os.environ.get("GEMINI_API_KEY", ""),
        "gemini_model": raw.get("gemini_model") or os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        "gemini_image_model": raw.get("gemini_image_model") or os.environ.get("GEMINI_IMAGE_MODEL", ""),
        # A model/persona on the Open WebUI instance that has a video-generation Tool
        # attached (see app/ai_video.py) — same idea as openwebui_image_model, just for
        # video. This app has no idea what's behind that tool (ComfyUI, a hosted API,
        # anything) — same "no visibility into the backend" boundary as image generation.
        "openwebui_video_model": raw.get("openwebui_video_model") or os.environ.get("OPEN_WEBUI_VIDEO_MODEL", ""),
        # Whether a key is already saved (DB or env) — the settings form uses this to show
        # "•••• already set" instead of ever putting the decrypted secret back in the page.
        "openwebui_api_key_set": bool(raw.get("openwebui_api_key_enc") or os.environ.get("OPEN_WEBUI_API_KEY")),
        "gemini_api_key_set": bool(raw.get("gemini_api_key_enc") or os.environ.get("GEMINI_API_KEY")),
    }


def save_ai_settings(db, form):
    """Plain fields overwrite unconditionally; secret fields only overwrite
    when the admin actually typed something new (a blank submit keeps
    whatever's already saved — the form never carries the real key back
    down to the browser to begin with, so "blank" can only mean "didn't
    change this")."""
    provider = form.get("ai_provider", "")
    if provider not in AI_PROVIDERS:
        provider = ""
    plain = {
        "ai_provider": provider,
        "openwebui_url": form.get("openwebui_url", "").strip(),
        "openwebui_model": form.get("openwebui_model", "").strip(),
        "openwebui_image_model": form.get("openwebui_image_model", "").strip(),
        "openwebui_video_model": form.get("openwebui_video_model", "").strip(),
        "ollama_url": form.get("ollama_url", "").strip(),
        "ollama_model": form.get("ollama_model", "").strip(),
        "gemini_model": form.get("gemini_model", "").strip(),
        "gemini_image_model": form.get("gemini_image_model", "").strip(),
    }
    for key, value in plain.items():
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    for form_key, settings_key in AI_SECRET_KEYS.items():
        new_value = form.get(form_key, "").strip()
        if not new_value:
            continue
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (settings_key, crypto.encrypt(new_value)),
        )
    db.commit()


def is_configured(db):
    s = get_ai_settings(db)
    if s["provider"] == "openwebui":
        return bool(s["openwebui_url"] and s["openwebui_api_key"])
    if s["provider"] == "ollama":
        return bool(s["ollama_url"])
    if s["provider"] == "gemini":
        return bool(s["gemini_api_key"])
    return False


# ---------- Provider calls, each normalized to {"content", "tool_calls"} ----------

class ProviderError(Exception):
    pass


#  How long a provider gets to answer, per kind of call.
#
#  60s is right for the assistant panel: somebody is watching a cursor
#  blink, and a minute of that is already too long. It is wrong for
#  GENERATION -- a self-hosted model writing a structured JSON answer
#  regularly takes longer, and the whole theme generator ran against the
#  chat timeout. What that looked like from the outside was the tool
#  failing at random: some calls came in under the minute and some did
#  not, so the same brief succeeded, then produced a template with two
#  unwritten pages, then refused outright.
#
#  Nobody is watching a batch run's cursor -- it already says "Generating
#  ... 240s" -- so it can wait.
CHAT_TIMEOUT = 60
GENERATE_TIMEOUT = 300


def _post_json(url, body, headers, timeout=CHAT_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Never echo the raw response back up to a flash/UI surface — it can
        # include request-context detail from the provider's own error
        # formatting. Just the status is enough to act on.
        raise ProviderError(f"The AI provider returned an error (HTTP {e.code}).")
    except TimeoutError:
        # A slow-to-respond model (large prompt, cold start, ...) raises a
        # bare TimeoutError on the response read, not urllib.error.URLError
        # (that only covers connection-level failures) — left uncaught,
        # this surfaced as a full 60s+ hang with no user-facing error at
        # all instead of a clean failure message.
        raise ProviderError("The AI provider took too long to respond.")
    except urllib.error.URLError:
        raise ProviderError("Couldn't reach the configured AI provider.")


def _get_json(url, headers, timeout=15):
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise ProviderError(f"The AI provider returned an error (HTTP {e.code}).")
    except TimeoutError:
        raise ProviderError("The AI provider took too long to respond.")
    except urllib.error.URLError:
        raise ProviderError("Couldn't reach the configured AI provider.")


def _openai_wire_messages(messages):
    """run_turn() re-appends *normalized* tool_calls to `messages` between
    loop iterations — [{"id","name","arguments": dict}], the shape every
    provider's response gets translated into (see _call_open_webui's own
    return value below) so run_turn itself never needs to know which
    provider answered. But that normalized shape isn't valid OpenAI wire
    format: OpenAI expects each tool_calls entry as
    {"id","type":"function","function":{"name","arguments": JSON STRING}}
    (arguments as a *string*, not the parsed dict run_turn works with).
    Sent back as-is, OpenWebUI/any OpenAI-compatible endpoint rejects the
    request with HTTP 400 the moment a tool was actually called — i.e.
    every turn past the first plain reply. This rebuilds the wire shape
    from the normalized one before every request."""
    out = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            m2 = dict(m)
            m2["tool_calls"] = [
                {
                    "id": c.get("id", ""),
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments", {}))},
                }
                for c in m["tool_calls"]
            ]
            out.append(m2)
        else:
            out.append(m)
    return out


def _openai_vision_messages(messages):
    """OpenAI-style vision input: a message carrying `image` ({mime, data})
    gets its plain string `content` replaced with a list of parts (text +
    image_url as a data: URI) — everything else passes through untouched.
    Shared by OpenWebUI (speaks this format natively); Ollama and Gemini
    have their own shapes, handled separately."""
    out = []
    for m in messages:
        image = m.get("image")
        if not image:
            out.append(m)
            continue
        m2 = dict(m)
        m2.pop("image", None)
        m2["content"] = [
            {"type": "text", "text": m.get("content") or ""},
            {"type": "image_url", "image_url": {"url": f"data:{image['mime']};base64,{image['data']}"}},
        ]
        out.append(m2)
    return out


def _call_open_webui(settings, messages, tools, want_json=False, timeout=CHAT_TIMEOUT):
    """OpenWebUI speaks an OpenAI-style /api/chat/completions shape."""
    headers = {"Content-Type": "application/json"}
    if settings["openwebui_api_key"]:
        headers["Authorization"] = f"Bearer {settings['openwebui_api_key']}"
    body = {"model": settings["openwebui_model"],
            "messages": _openai_vision_messages(_openai_wire_messages(messages)),
            "tools": tools}
    if want_json:
        #  Said in the protocol, not only in the prose. A model held to
        #  this cannot spend its budget thinking out loud before the
        #  first brace, which is how a perfectly good answer arrived
        #  truncated mid-string.
        body["response_format"] = {"type": "json_object"}
    data = _post_json(
        f"{settings['openwebui_url'].rstrip('/')}/api/chat/completions",
        body,
        headers,
        timeout,
    )
    choice = data["choices"][0]["message"]
    tool_calls = []
    for call in (choice.get("tool_calls") or []):
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except ValueError:
            args = {}
        tool_calls.append({"id": call.get("id", ""), "name": call["function"]["name"], "arguments": args})
    return {"content": choice.get("content"), "tool_calls": tool_calls}


def _ollama_vision_messages(messages):
    """Ollama's chat API takes a message's image as a raw-base64 `images`
    list on that same message — no data: prefix, no mime type (Ollama
    infers it from the bytes)."""
    out = []
    for m in messages:
        image = m.get("image")
        if not image:
            out.append(m)
            continue
        m2 = dict(m)
        m2.pop("image", None)
        m2["images"] = [image["data"]]
        out.append(m2)
    return out


def _ollama_wire_messages(messages):
    """Same problem/fix as _openai_wire_messages, for Ollama's native
    shape: an assistant tool_calls entry there is
    {"function": {"name", "arguments": dict}} — no "id"/"type" wrapper,
    and arguments stays a real object rather than a JSON string."""
    out = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            m2 = dict(m)
            m2["tool_calls"] = [
                {"function": {"name": c["name"], "arguments": c.get("arguments", {})}}
                for c in m["tool_calls"]
            ]
            out.append(m2)
        else:
            out.append(m)
    return out


def _call_ollama(settings, messages, tools, want_json=False, timeout=CHAT_TIMEOUT):
    base = settings["ollama_url"].rstrip("/")
    headers = {"Content-Type": "application/json"}
    body = {"model": settings["ollama_model"],
            "messages": _ollama_vision_messages(_ollama_wire_messages(messages)),
            "tools": tools, "stream": False}
    if want_json:
        #  Ollama's own name for the same thing.
        body["format"] = "json"
    data = _post_json(f"{base}/api/chat", body, headers, timeout)
    msg = data.get("message", {})
    tool_calls = []
    for call in (msg.get("tool_calls") or []):
        fn = call.get("function", {})
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = {}
        tool_calls.append({"id": call.get("id", ""), "name": fn.get("name", ""), "arguments": args or {}})
    return {"content": msg.get("content"), "tool_calls": tool_calls}


def _openai_messages_to_gemini(messages):
    """Gemini has no 'system' role message and no 'tool' role — system
    content becomes systemInstruction, and a tool result becomes a
    functionResponse part on a 'user'-role turn (Gemini's convention)."""
    system_text = None
    contents = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system_text = (system_text + "\n" + m["content"]) if system_text else m["content"]
        elif role == "tool":
            contents.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": m.get("name", "tool"), "response": {"result": m.get("content", "")}}}],
            })
        elif role == "assistant":
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for call in (m.get("tool_calls") or []):
                parts.append({"functionCall": {"name": call["name"], "args": call.get("arguments", {})}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        else:
            parts = [{"text": m.get("content", "")}]
            image = m.get("image")
            if image:
                parts.append({"inline_data": {"mime_type": image["mime"], "data": image["data"]}})
            contents.append({"role": "user", "parts": parts})
    return system_text, contents


def _openai_tools_to_gemini(tools):
    declarations = []
    for t in tools:
        fn = t["function"]
        declarations.append({"name": fn["name"], "description": fn.get("description", ""), "parameters": fn.get("parameters", {})})
    return [{"functionDeclarations": declarations}]


def _call_gemini(settings, messages, tools, timeout=CHAT_TIMEOUT):
    model = settings["gemini_model"]
    system_text, contents = _openai_messages_to_gemini(messages)
    body = {"contents": contents, "tools": _openai_tools_to_gemini(tools)}
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings['gemini_api_key']}"
    data = _post_json(url, body, {"Content-Type": "application/json"}, timeout)
    candidates = data.get("candidates") or []
    if not candidates:
        return {"content": None, "tool_calls": []}
    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts, tool_calls = [], []
    for i, part in enumerate(parts):
        if "text" in part:
            text_parts.append(part["text"])
        elif "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append({"id": f"gemini-{i}", "name": fc.get("name", ""), "arguments": fc.get("args", {})})
    return {"content": "\n".join(text_parts) if text_parts else None, "tool_calls": tool_calls}


def _call_provider(db, messages, tools, want_json=False, timeout=CHAT_TIMEOUT):
    """One reply from whatever provider is configured.

    `want_json` says the CALLER will parse the answer, and it is passed
    down to the wire rather than only written in the prompt. Asking in
    prose alone is what "please reply with only a JSON object" is, and a
    small thinking model reads that, thinks out loud first, and runs out
    of room mid-string -- which arrives as an unterminated JSON, not as
    an error, and reads to the owner as "the AI didn't return usable
    content" about a model that was answering fine.
    """
    settings = get_ai_settings(db)
    provider = settings["provider"]
    if provider == "openwebui":
        return _call_open_webui(settings, messages, tools, want_json, timeout)
    if provider == "ollama":
        return _call_ollama(settings, messages, tools, want_json, timeout)
    if provider == "gemini":
        return _call_gemini(settings, messages, tools, timeout)
    raise ProviderError("No AI provider is configured.")


def _sees(entry):
    """Whether one Open WebUI model entry can look at a picture.

    Three answers, and the third is the point: True, False, or None for
    "it does not say". A caller that cannot tell should TRY the model
    and let it answer, not refuse on its behalf.

    Read from the backend's own capability list, which is the field that
    means something. Open WebUI also keeps an
    `info.meta.capabilities.vision`, and it is deliberately NOT read
    here: measured against a real server it was `true` on all thirteen
    models, coder models included -- it is the UI's per-model toggle
    block, defaulted on, not a statement about the weights. **A field
    that is true for everything answers nothing**, and believing it is
    how "yes it can see" came to be said about a model that cannot.
    """
    listed = (entry.get("ollama") or {}).get("capabilities")
    if isinstance(listed, list) and listed:
        return "vision" in listed
    return None


def list_models(provider, url, api_key):
    """Live model list for the Settings page's dropdowns — takes the
    url/key straight from the (possibly-unsaved) form, not from the DB, so
    an admin can test before clicking Save. Each entry is
    {"id": str, "vision": bool} — "vision" is best-effort: Ollama exposes
    real per-model capability data (queried below), Open WebUI passes
    its backend's list through (so an Ollama-backed one is exact, and
    anything else is None — "it does not say", which is not the same as
    no), and Gemini model names reliably indicate it (every current
    Gemini chat model is multimodal). This used to return False for
    every Open WebUI model on the grounds that it "doesn't expose this";
    it does, and the cost of that guess landed on somebody uploading a
    screenshot to a coder model and being told afterwards that nothing
    could be read from it.
    Raises ProviderError on any failure — the caller shows it inline."""
    if provider == "ollama":
        base = (url or "").rstrip("/")
        if not base:
            raise ProviderError("Enter the Ollama server URL first.")
        data = _get_json(f"{base}/api/tags", {})
        models = []
        for m in data.get("models", []):
            name = m.get("name") or m.get("model")
            if not name:
                continue
            vision = False
            try:
                show = _post_json(f"{base}/api/show", {"name": name}, {"Content-Type": "application/json"})
                vision = "vision" in (show.get("capabilities") or [])
            except ProviderError:
                pass  # older Ollama without /api/show capabilities — list it plain
            models.append({"id": name, "vision": vision})
        return models

    if provider == "openwebui":
        base = (url or "").rstrip("/")
        if not base:
            raise ProviderError("Enter the Open WebUI server URL first.")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        data = _get_json(f"{base}/api/models", headers)
        items = data.get("data") if isinstance(data, dict) else data
        return [{"id": m.get("id") or m.get("name"), "vision": _sees(m)}
                for m in (items or []) if m.get("id") or m.get("name")]

    if provider == "gemini":
        if not api_key:
            raise ProviderError("Enter the Gemini API key first.")
        data = _get_json(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}", {})
        out = []
        for m in data.get("models", []):
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = (m.get("name") or "").split("/")[-1]
            if not name:
                continue
            # Every current Gemini chat model is multimodal (accepts image
            # input); "image" in the name additionally means it can
            # generate images, not just see them.
            out.append({"id": name, "vision": True, "image_gen": "image" in name})
        return out

    raise ProviderError("Unknown provider.")


def _nothing_came_back(db):
    """What to say when the model said nothing at all.

    Names the likely cause rather than apologising, because the owner can
    act on the cause. A small self-hosted model asked something it cannot
    map to a tool very often returns an empty completion instead of
    saying it does not know -- so the advice is different depending on
    what is running, and saying "try again" to somebody on a 3B model is
    useless.
    """
    settings = get_ai_settings(db)
    if settings.get("provider") == "ollama":
        return ("I didn't have an answer for that one. Smaller self-hosted models often "
                "go quiet rather than say they are unsure — try asking again in "
                "plainer words, or one step at a time. A larger model handles "
                "instructions like this more reliably.")
    return ("I didn't have an answer for that one — try asking again with a bit "
            "more detail.")


def _execute_read_tool(db, name, args):
    if name == "list_pages":
        pages = db.execute("SELECT id, title, slug, is_home FROM pages ORDER BY nav_order").fetchall()
        out = []
        for p in pages:
            sections = db.execute(
                "SELECT id, type, content FROM sections WHERE page_id = ? ORDER BY position", (p["id"],)
            ).fetchall()
            out.append({
                "page_id": p["id"],
                "title": p["title"],
                "is_home": bool(p["is_home"]),
                "sections": [
                    {"section_id": s["id"], "type": s["type"], "preview": (s["content"] or "")[:120]}
                    for s in sections
                ],
            })
        # Site-wide chrome (header/sidebar/sidebar_right/footer) lives on
        # the active template, scoped by zone instead of page_id — without
        # this, get_section/update_section_content have no way to be
        # reached at all: their section_ids never show up anywhere else.
        active_tpl = db.execute("SELECT id, name FROM templates WHERE is_active = 1").fetchone()
        if active_tpl:
            zone_out = {}
            for zone in ("header", "sidebar", "sidebar_right", "footer"):
                zone_sections = db.execute(
                    "SELECT id, type, content FROM sections WHERE template_id = ? AND zone = ? ORDER BY position",
                    (active_tpl["id"], zone),
                ).fetchall()
                zone_out[zone] = [
                    {"section_id": s["id"], "type": s["type"], "preview": (s["content"] or "")[:120]}
                    for s in zone_sections
                ]
            out.append({
                "site_zones": True,
                "template": active_tpl["name"],
                "note": "header/sidebar/sidebar_right/footer — site-wide, shared by every page, not page-specific content.",
                "zones": zone_out,
            })
        return out
    if name == "get_section":
        s = db.execute("SELECT * FROM sections WHERE id = ?", (args.get("section_id"),)).fetchone()
        if not s:
            return {"error": "Section not found."}
        return {"section_id": s["id"], "type": s["type"], "title": s["title"], "content": s["content"]}
    return {"error": f"Unknown tool {name}"}


def run_turn(db, message_history, image=None):
    """
    Runs the tool-calling loop for one user turn, against whichever
    provider is currently configured (see get_ai_settings). Read-only tool
    calls are executed and looped back to the model automatically (up to a
    small cap). The first write-tool call halts the loop and is returned
    as a proposal instead of being executed.

    `image`, if given, is {"mime": str, "data": base64-str} — attached to
    the latest user message only (the question being asked right now, not
    the whole conversation) and translated into whichever shape the
    active provider needs (see _openai_vision_messages / Ollama's `images`
    field / Gemini's inline_data part). Every provider here (OpenWebUI,
    Ollama, Gemini) accepts image input as long as the configured model
    itself does — a text-only model will just ignore or error on it.

    Returns {"reply": str} or {"reply": str|None, "proposal": {...}}.
    """
    messages = [{"role": "system", "content": _system_prompt()}] + message_history
    if image and messages:
        messages[-1] = dict(messages[-1], image=image)

    for _ in range(5):  # bound the read-tool loop
        result = _call_provider(db, messages, TOOLS)
        tool_calls = result["tool_calls"]

        if not tool_calls:
            said = (result.get("content") or "").strip()
            #  A model that returns nothing at all -- no words and no tool
            #  call -- used to be relayed as an empty reply, so the panel
            #  showed nothing whatsoever: you asked, and the screen did
            #  not change. Read as "the assistant is ignoring me", which
            #  is the worst available reading and not what happened.
            #
            #  It is much commoner on a small self-hosted model than on a
            #  hosted one: asked something it cannot map to a tool, it
            #  often produces an empty completion rather than saying so.
            #  The app cannot make it answer, but it can stop pretending
            #  the silence was an answer.
            return {"reply": said or _nothing_came_back(db)}

        messages.append({"role": "assistant", "content": result.get("content"), "tool_calls": tool_calls})
        halted_proposal = None

        for call in tool_calls:
            name = call["name"]
            args = call.get("arguments") or {}

            if name in WRITE_TOOL_NAMES:
                halted_proposal = {"tool": name, "args": args}
                # Satisfy the loop's requirement that every tool_call gets a
                # response message, even though we're not executing it yet.
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name,
                                  "content": "Proposed — awaiting admin approval, not yet applied."})
                continue

            tool_result = _execute_read_tool(db, name, args)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name,
                              "content": json.dumps(tool_result)})

        if halted_proposal:
            #  A proposal with no words beside it is a change offered
            #  with no account of itself. Rare, and the same silence as
            #  above: better a plain sentence than a bare Apply button.
            return {"reply": (result.get("content") or "").strip()
                    or "Here is what I would change. Have a look before applying it.",
                    "proposal": halted_proposal}

    return {"reply": "I wasn't able to finish looking into that — try asking again with more detail."}


def apply_proposal(proposal, next_url_provider):
    """Actually writes an approved proposal. Only ever called after an
    explicit admin click — never by the model directly."""
    db = get_db()
    tool = proposal.get("tool")
    args = proposal.get("args", {})

    section_id = args.get("section_id")
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        return False, "That section no longer exists."

    if tool == "update_section_content":
        db.execute("UPDATE sections SET content = ? WHERE id = ?", (args.get("new_content", ""), section_id))
    elif tool == "reformat_section_html":
        db.execute("UPDATE sections SET content = ? WHERE id = ?", (args.get("reformatted_html", ""), section_id))
    else:
        return False, "Unknown proposal type."

    db.commit()
    return True, None


def where_content_goes(db):
    """Where anything given to an AI tool actually goes, in the owner's terms.

    A NOTICE THAT IS THE SAME ON EVERY INSTALL IS A NOTICE NOBODY READS,
    and on this app it would also be untrue half the time. Three of the
    four providers are self-hosted: with Ollama or Open WebUI the words
    go to a machine the owner runs, which is a different fact from
    sending them to Google, and telling somebody their own server is a
    third party teaches them to ignore the warning that matters.

    So it says which, and where. Returns:

      label     what to call it -- "Google Gemini", "your Open WebUI
                server at 10.0.0.4:3000"
      offsite   True when the words leave this owner's control
      ready     False when no provider is configured, in which case
                nothing is being sent anywhere yet

    Never returns a key, and never the URL's credentials -- host and
    port only, which is what identifies a machine to the person who set
    it up.
    """
    import urllib.parse

    settings = get_ai_settings(db)
    provider = settings.get("provider") or ""
    if not provider:
        return {"label": "", "offsite": False, "ready": False}
    if provider == "gemini":
        return {"label": PROVIDER_LABELS["gemini"], "offsite": True, "ready": True}
    url = settings.get("%s_url" % provider) or ""
    host = ""
    try:
        parsed = urllib.parse.urlsplit(url if "//" in url else "//" + url)
        host = parsed.netloc.rsplit("@", 1)[-1]
    except ValueError:
        host = ""
    label = "your %s server" % PROVIDER_LABELS.get(provider, provider)
    if host:
        label += " at %s" % host
    return {"label": label, "offsite": False, "ready": True}
