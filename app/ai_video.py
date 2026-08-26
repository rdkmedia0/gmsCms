"""
AI video generation — via Open WebUI only (see IMAGE_GEN_PROVIDERS' note in
ai_image.py for why Gemini/Ollama aren't options here either: Gemini's
public API has no video endpoint, Ollama has no media-generation API of
its own). Unlike images, Open WebUI has no built-in "video generation"
REST endpoint to proxy through — video only works via a Tool (a Python
function an admin registers in Open WebUI's own Workspace -> Tools,
attached to one of their models/personas) that Open WebUI executes
server-side. This app has no idea what that Tool actually calls (ComfyUI,
a hosted API, anything) — same "no visibility into the backend" boundary
ai_image.py already draws for images.

CONFIRMED WORKING (2026-08-22) against a real Open WebUI instance with a
video-generation Tool attached to a model: calling /api/chat/completions
directly (even streaming, even passing tool_ids) only ever returns the
model's tool_calls decision — Open WebUI does NOT execute the Tool from a
bare completions call. Execution only happens when the request is tied to
a real chat (chat_id + message id), which switches the response to an
async task dispatch ({"task_ids": [...]}) instead of a normal completion.
The task's result is never written back into the chat itself over plain
REST (that part is client/websocket-driven, which this app doesn't
speak) — but the Tool's own generated file lands in Open WebUI's Files
store as a real side effect of running the task, independent of the chat
save step, and is retrievable via GET /api/v1/files/{id}/content like any
other Open WebUI file. That's the path used below: dispatch once, then
poll Files for the newest video-typed file created since the dispatch —
polling whether or not the dispatch came back with a task id, because a
dispatch that answers a bare `null` can still be running the render (also
confirmed live, 2026-08-22; see _dispatch_once).
"""
import json
import time
import urllib.request
import urllib.error
import uuid

from . import assistant

DEFAULT_DURATION_S = 24
POLL_INTERVAL_S = 4
POLL_TIMEOUT_S = 1200  # a real video model can take several minutes to render
DISPATCH_WAKE_TIMEOUT_S = 360  # a cold GPU box booting from off typically takes 2-5 minutes


class VideoGenError(Exception):
    pass


def is_configured(db):
    settings = assistant.get_ai_settings(db)
    return (
        settings["provider"] == "openwebui"
        and bool(settings["openwebui_url"] and settings["openwebui_api_key"] and settings["openwebui_video_model"])
    )


def generate_video(db, prompt, duration_s=DEFAULT_DURATION_S, width=None, height=None):
    """Returns raw video bytes (mp4). Raises VideoGenError with a message
    safe to show the admin directly.

    `width`/`height` are a request, not a parameter: this app deliberately
    knows nothing about the Tool on the other side (see the module
    docstring), so the size is stated in the prompt the tool-calling model
    reads and passed on by it, the same way the duration already is. A
    Tool with no size argument just ignores it. Worth stating even so —
    the one this was built against defaults to 256x448 PORTRAIT, so
    saying nothing produced phone-shaped clips for a landscape player."""
    settings = assistant.get_ai_settings(db)
    if settings["provider"] != "openwebui":
        raise VideoGenError("Video generation needs Open WebUI selected as the AI provider — check AI Settings.")
    base_url = settings["openwebui_url"].rstrip("/")
    api_key = settings["openwebui_api_key"]
    model_name = settings["openwebui_video_model"]
    if not (base_url and api_key):
        raise VideoGenError("Video generation isn't configured — set the Open WebUI URL and API key on the AI Settings page.")
    if not model_name:
        raise VideoGenError(
            "Video generation isn't configured — set a Video Generation Model on the AI Settings page "
            "(a model/persona in Open WebUI that has a video-generation Tool attached)."
        )
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    model_id, tool_ids = _resolve_model_tools(base_url, headers, model_name)
    if not tool_ids:
        raise VideoGenError(
            f'Open WebUI model "{model_name}" has no Tools attached — attach a video-generation Tool to it '
            "in Open WebUI's own Workspace → Tools first."
        )

    chat_id = _new_chat(base_url, headers, model_id)
    #  Which videos already exist, BEFORE anything is dispatched — the
    #  result is then "the video whose id wasn't here before", which is
    #  exact. Recognising it by timestamp instead ("newest video created
    #  since dispatch") is not: polling only starts once the dispatch call
    #  returns, which can be two minutes later, so a clip that landed in
    #  between satisfies the filter. Generating two videos back to back
    #  really did hand the second job the first job's clip.
    known_ids = _video_file_ids(base_url, headers)
    dispatch_time = time.time()
    size = ""
    if width and height:
        shape = "landscape" if width > height else ("portrait" if height > width else "square")
        size = f", {width} by {height} pixels ({shape})"
    full_prompt = f"Generate a {round(duration_s)} second video{size}: {prompt.strip()}"
    try:
        confirmed = _dispatch_once(base_url, headers, model_id, tool_ids, chat_id, full_prompt)
        file_id = _wait_for_video_file(
            base_url, headers, dispatch_time, known_ids,
            redispatch=None if confirmed else (
                lambda: _dispatch_once(base_url, headers, model_id, tool_ids, chat_id, full_prompt)
            ),
        )
        return _fetch_file(base_url, headers, file_id)
    finally:
        _delete_chat(base_url, headers, chat_id)


def _get_json(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        raise VideoGenError(f"Open WebUI returned an error ({e.code}): {detail}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise VideoGenError(f"Couldn't reach Open WebUI: {e}")


def _post_json(url, headers, body, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        raise VideoGenError(f"Open WebUI returned an error ({e.code}): {detail}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise VideoGenError(f"Couldn't reach Open WebUI: {e}")


def _resolve_model_tools(base_url, headers, model_name):
    """Matches the admin's configured model name against Open WebUI's model
    list by id or display name (case-insensitive — the settings field's
    placeholder shows a lowercase example, same as openwebui_image_model),
    and reads the tool ids already attached to it in Open WebUI's own UI
    (Workspace -> Tools) — the admin never has to know or type Open WebUI's
    internal tool id. A model's own toolIds list can reference ids that no
    longer resolve to a real registered Tool (renamed/deleted since being
    attached) — passing a dangling id to /api/chat/completions makes the
    whole dispatch fail, so this filters down to ids that actually exist."""
    data = _get_json(f"{base_url}/api/models", headers)
    needle = model_name.strip().lower()
    tool_ids = None
    model_id = None
    for entry in data.get("data", []):
        if entry.get("id", "").lower() == needle or entry.get("name", "").lower() == needle:
            model_id = entry["id"]
            meta = ((entry.get("info") or {}).get("meta") or {})
            tool_ids = meta.get("toolIds") or []
            break
    if model_id is None:
        raise VideoGenError(f'No Open WebUI model named "{model_name}" was found — check the Video Generation Model setting.')

    valid_ids = {tool["id"] for tool in _get_json(f"{base_url}/api/v1/tools/", headers)}
    return model_id, [t for t in tool_ids if t in valid_ids]


def _new_chat(base_url, headers, model_id):
    data = _post_json(f"{base_url}/api/v1/chats/new", headers, {"chat": {"title": "AI video generation", "models": [model_id], "messages": []}})
    chat_id = data.get("id")
    if not chat_id:
        raise VideoGenError("Open WebUI didn't create a chat session for the video job.")
    return chat_id


def _delete_chat(base_url, headers, chat_id):
    req = urllib.request.Request(f"{base_url}/api/v1/chats/{chat_id}", method="DELETE", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except (urllib.error.HTTPError, urllib.error.URLError):
        pass  # best-effort cleanup — a leftover empty chat isn't worth failing the whole job over


def _dispatch_once(base_url, headers, model_id, tool_ids, chat_id, prompt):
    """Fires one generation and reports whether Open WebUI acknowledged it
    with a task id. Returns True on {"task_ids": [...]}, False on the two
    responses that look like a failure but aren't necessarily one:

    * a bare `null` body, and
    * a timed-out/dropped connection.

    Both were originally read as "the backend is still waking up, try
    again" and retried on a loop. That was wrong twice over — confirmed
    live: a dispatch that answers `null` can still have RUN, with the
    Tool's video landing in the Files store a couple of minutes later. So
    the retry loop was firing a fresh render every 15 seconds against a
    backend that was already busy rendering, and then reporting failure
    for a video that existed. Deciding what a False means is the caller's
    job now (see _wait_for_video_file's `redispatch`): watch the Files
    store first, and only re-dispatch if nothing shows up.
    """
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "tool_ids": tool_ids,
        "chat_id": chat_id,
        "id": str(uuid.uuid4()),
    }
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/chat/completions", data=json.dumps(body).encode(),
                method="POST", headers=headers,
            ),
            timeout=120,
        ) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # A real refusal (bad model, bad key, bad request) is worth failing
        # on immediately — unlike the ambiguous cases below, waiting out a
        # 20-minute poll for it would just hide the actual reason.
        detail = e.read().decode(errors="ignore")[:300]
        raise VideoGenError(f"Open WebUI returned an error ({e.code}): {detail}")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False  # dropped/timed out/unparseable — may still be running
    return bool(data and data.get("task_ids"))


def _video_file_ids(base_url, headers):
    """Ids of every video already in Open WebUI's Files store."""
    data = _get_json(f"{base_url}/api/v1/files/", headers)
    return {
        item.get("id") for item in data.get("items", [])
        if (item.get("meta") or {}).get("content_type", "").startswith("video/")
    }


def _wait_for_video_file(base_url, headers, dispatch_time, known_ids=frozenset(), redispatch=None):
    """Polls the Files store for a video created since the dispatch.

    `redispatch` is passed only when the dispatch went unacknowledged. A
    backend that really was asleep needs a second nudge once it's up; one
    that simply answered `null` while getting on with the render does not,
    and must not be nudged into rendering the same clip twice. Waiting out
    the wake window before that single retry serves both: by then, a
    render that was actually running has usually landed its file."""
    deadline = time.monotonic() + POLL_TIMEOUT_S
    retry_at = (time.monotonic() + DISPATCH_WAKE_TIMEOUT_S) if redispatch else None
    while time.monotonic() < deadline:
        if retry_at is not None and time.monotonic() >= retry_at:
            retry_at = None  # one extra nudge, never a loop
            redispatch()
        data = _get_json(f"{base_url}/api/v1/files/", headers)
        candidates = [
            item for item in data.get("items", [])
            if item.get("id") not in known_ids
            and item.get("created_at", 0) >= dispatch_time - 5
            and (item.get("meta") or {}).get("content_type", "").startswith("video/")
        ]
        if candidates:
            candidates.sort(key=lambda item: item["created_at"])
            return candidates[-1]["id"]
        time.sleep(POLL_INTERVAL_S)
    raise VideoGenError("Open WebUI took too long to generate the video — try again, or check its Tool/backend directly.")


def _fetch_file(base_url, headers, file_id):
    req = urllib.request.Request(f"{base_url}/api/v1/files/{file_id}/content", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise VideoGenError(f"Open WebUI generated a video but it couldn't be fetched: {e}")
