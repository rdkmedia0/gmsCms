"""Reading a look from a PICTURE somebody shows you.

This replaced fetching the URL and parsing its CSS, for two reasons the
owner of an install cares about more than we do.

**Fetching gets your server flagged.** A small site's VPS reaching out to
third-party pages, repeatedly, from one address, is what a scraper looks
like -- and being taken for one costs an install its own reachability,
not ours. It was also refused by exactly the sites people most want to
point at: anything behind a bot check answers with a challenge page, and
a challenge page HAS colours, so the reader succeeded and returned the
wrong ones.

**And it could not read a large share of the web anyway.** A page that
renders itself in JavaScript keeps its colours in code, not in a
stylesheet; measured, GitHub returned three colours belonging to nothing
on the page.

So the owner takes a screenshot, or points at any picture they like, and
it is read HERE -- from the pixels. Two readings, and the second is
optional:

  * **Always**: the colours, worked out from the pixels themselves. No
    provider, no network, and on the pictures this was measured against
    it finds what a person would name -- Hacker News orange, Airbnb's
    rausch, Vue's green and indigo.
  * **When the model can see**: the typeface feel, the corner style and
    the shadow depth, which pixels alone cannot name. Offered only when
    the chosen model reports vision, and said plainly when it does not,
    because a control that quietly does nothing is worse than one that
    is missing.

Nothing here returns prose. It returns colours and words from lists this
app already has -- so a picture cannot carry somebody's copy into a
generated site, which was the boundary the URL reader had and this keeps.
"""
import base64
import json
import re

#  What a model will actually accept, measured rather than assumed:
#  on a real vision model 943 KB was refused outright and 87 KB came
#  back EMPTY, which reads exactly like a model with nothing to say. The
#  browser shrinks a picture to around 40 KB before sending it; this is
#  the ceiling that stops anything else getting through.
MAX_BYTES = 512 * 1024
ALLOWED = ("image/png", "image/jpeg", "image/webp", "image/gif")

VISION_SCHEMA = (
    '{"fonts": "a key from the list", "shape": "a key from the list", '
    '"shadow": "a key from the list", "feel": "three or four words"}'
)


class PictureError(Exception):
    """Why this picture cannot be read, in the owner's terms."""


def accept(value):
    """(mime, bytes) for one picture arriving as a data: URL, or a refusal.

    It arrives already shrunk, from the canvas the colours were counted
    on -- this app has no image library on the server, and does not need
    one for this. Two things are still checked here, because what the
    browser sends is a string like any other: that it decodes, and that
    what it decodes to is a picture, judged from its first bytes rather
    than from anything the sender called it.
    """
    if not value:
        return None, None
    match = re.match(r"^data:([\w/+.-]+);base64,(.*)$", value.strip(), re.S)
    if not match:
        raise PictureError("That picture did not arrive in a form I could read.")
    if len(match.group(2)) > (MAX_BYTES * 4) // 3 + 8:
        raise PictureError("That picture is too large to send to the model.")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError):
        raise PictureError("That picture did not arrive in a form I could read.")
    if not data:
        raise PictureError("That picture was empty.")
    if len(data) > MAX_BYTES:
        raise PictureError("That picture is too large to send to the model.")
    kind = _sniff(data)
    if not kind:
        raise PictureError("That does not look like a picture. PNG, JPEG, WEBP "
                           "and GIF can be read.")
    return kind, data


def _sniff(data):
    """What this file actually is, from its first bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


# ------------------------------------------------------- what a model sees


def can_see(db):
    """Whether the chosen model can look at a picture -- asked, not guessed.

    Both self-hosted providers publish this per model, so it is read
    rather than assumed, and a no NAMES the models on the same server
    that can. That is the difference between a refusal somebody can act
    on and one they can only be annoyed by: this install had a coder
    model selected and four vision models sitting beside it, and the old
    answer was an unqualified yes followed, a minute later, by "the model
    could not tell me anything about that picture".

    Falls back to trying rather than refusing when the list cannot be
    read: not being able to check is not evidence of an incapable model,
    and `read_with_model` already answers in words when it fails.
    """
    from .. import assistant
    settings = assistant.get_ai_settings(db)
    provider = settings.get("provider")
    if not provider:
        return False, ("No AI provider is set up, so a picture can only be read "
                       "for its colours.")
    if provider == "gemini":
        return True, ""

    chosen = (settings.get("%s_model" % provider) or "").strip()
    try:
        models = assistant.list_models(
            provider,
            settings.get("%s_url" % provider),
            settings.get("openwebui_api_key") if provider == "openwebui" else "")
    except Exception:                                             # noqa: BLE001
        return True, ""
    seeing = [m["id"] for m in models if m.get("vision") is True]
    here = [m for m in models if m["id"] == chosen]
    #  Only a model that SAYS it cannot is refused. Not in the list (an
    #  alias, or a server that has moved on) and does-not-say are both
    #  "try it": refusing on a model's behalf is the mistake this
    #  replaced, and `read_with_model` already answers in words.
    if not here or here[0].get("vision") is not False:
        return True, ""
    if seeing:
        return False, ("%s cannot look at pictures, so this one is read for its "
                       "colours only. %s on the same server can — choose one under "
                       "Settings → AI to have the typefaces and shapes read too."
                       % (chosen, ", ".join(seeing[:4])))
    return False, ("%s cannot look at pictures, and no model on your server can, "
                   "so a picture is read for its colours only. A vision model — "
                   "llava, minicpm-v or qwen3-vl — would also read the typefaces "
                   "and the shapes." % (chosen or "The model you have chosen"))


def read_with_model(db, mime, data, vocab):
    """The typeface feel, corners and depth, from a picture.

    Every answer is checked against the lists this app actually has --
    `vocab` is (fonts, shapes, shadows) -- because a model naming a font
    this app cannot load is a look that silently falls back to nothing.
    Returns {} rather than raising: colours are the point, and this is
    the part that is allowed to be unavailable.
    """
    from .. import assistant
    from flask import current_app
    fonts, shapes, shadows = vocab
    prompt = current_app.jinja_env.get_template(
        "prompts/look_from_picture.j2").render(
            schema=VISION_SCHEMA, fonts=fonts, shapes=shapes, shadows=shadows)
    try:
        result = assistant._call_provider(db, [{
            "role": "user",
            "content": prompt,
            "image": {"mime": mime, "data": base64.b64encode(data).decode()},
        }], [])
    except Exception:                                         # noqa: BLE001
        return {}
    content = (result.get("content") or "").strip()
    content = re.sub(r"^```(?:json)?", "", content).strip()
    content = re.sub(r"```$", "", content).strip()
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {}
    try:
        said = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(said, dict):
        return {}
    return {
        "fonts": said.get("fonts") if said.get("fonts") in dict(fonts) else "",
        "shape": said.get("shape") if said.get("shape") in shapes else "",
        "shadow": said.get("shadow") if said.get("shadow") in shadows else "",
        "feel": str(said.get("feel") or "")[:80],
    }
