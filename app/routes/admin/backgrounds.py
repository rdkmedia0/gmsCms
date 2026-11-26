"""The Colors panel's Background controls: the picture behind the site or
one page, and one page's own colour. (The site-wide colour belongs to the
template -- see templates.template_ground.)"""
from flask import request, jsonify, current_app

from . import bp, wants_json, _redirect_next
from ..auth import login_required
from ...db import get_db
from ...services import packages
from ...services import page_background as backgrounds


def _done():
    if wants_json():
        return jsonify({"ok": True})
    return _redirect_next("admin.dashboard")


@bp.route("/background", methods=["POST"])
@login_required
def background_update():
    db = get_db()
    page_id = request.form.get("page_id", type=int)
    whole_site = request.form.get("scope") == "site"
    if not whole_site and not db.execute(
            "SELECT 1 FROM pages WHERE id = ?", (page_id,)).fetchone():
        return jsonify({"ok": False, "error": "That page no longer exists."}), 404

    #  Only what the submitted form carried changes: colour and picture are
    #  separate controls and saving one must not clear the other.
    if not whole_site and "ground_choice" in request.form:
        db.execute("UPDATE pages SET bg_color = ? WHERE id = ?",
                   (backgrounds.stored_colour(request.form.get("ground_choice", ""),
                                              request.form.get("ground", "")), page_id))

    if "bg_image" in request.form:
        #  A clicked button says what it wants; otherwise the form's field does.
        chosen = (request.form.get("bg_image_op") or request.form.get("bg_image") or "").strip()
        if chosen == "inherit":
            chosen = ""
        if chosen and chosen != backgrounds.NO_PICTURE:
            if not chosen.startswith("/static/"):
                return jsonify({"ok": False, "error": "Choose a picture from the Media Library."}), 400
            #  A template's picture becomes the site's own copy, so it
            #  survives that template being removed.
            chosen = packages.adopt_template_picture(
                chosen, current_app.static_folder, current_app.config["UPLOAD_FOLDER"])
        values = {
            "bg_image": chosen or None,
            "bg_overlay": backgrounds.picked(request.form.get("bg_overlay"), backgrounds.OVERLAYS),
            "bg_surface": backgrounds.picked(request.form.get("bg_surface"), backgrounds.SURFACES),
            "bg_attach": backgrounds.picked(request.form.get("bg_attach"), backgrounds.ATTACHMENTS),
        }
        if whole_site:
            for field, key in backgrounds.SITE_KEYS.items():
                db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                           (key, values[field] or ""))
        else:
            db.execute("UPDATE pages SET bg_image = ?, bg_overlay = ?, bg_surface = ?, "
                       "bg_attach = ? WHERE id = ?", (*values.values(), page_id))
    db.commit()
    return _done()
