from flask import request, url_for, jsonify

from . import bp
from ..auth import login_required
from ...db import get_db
from ... import assistant

# ---------- AI Assistant (admin-only, read-only tools + propose-then-approve edits) ----------
# The chat UI itself lives in partials/assistant_panel.html, included as a
# collapsible side panel on every admin and (when logged in) public page —
# see inject_admin_theme() above and public.py's _render_page().


@bp.route("/assistant/chat", methods=["POST"])
@login_required
def assistant_chat():
    db = get_db()
    if not assistant.is_configured(db):
        return jsonify({"error": "The AI assistant isn't configured on this server yet."}), 400
    history = request.get_json(silent=True) or {}
    messages = history.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "No message provided."}), 400
    image = history.get("image")
    if not (isinstance(image, dict) and isinstance(image.get("mime"), str) and isinstance(image.get("data"), str)):
        image = None
    try:
        result = assistant.run_turn(db, messages, image=image)
    except assistant.ProviderError as e:
        return jsonify({"error": str(e)}), 502
    except Exception:
        return jsonify({"error": "Couldn't reach the AI assistant — check the connection and try again."}), 502
    return jsonify(result)


@bp.route("/assistant/apply", methods=["POST"])
@login_required
def assistant_apply():
    proposal = request.get_json(silent=True) or {}
    ok, error = assistant.apply_proposal(proposal, url_for)
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


