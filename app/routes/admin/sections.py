import os
import re
import json
import uuid
from flask import (request, flash, redirect, url_for, jsonify, render_template,
                   current_app, Response, session)
from werkzeug.utils import secure_filename

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import packages
from ...services import blog as blog_service
from ... import ai_image
from ...services.menu import _menu_updated_html
from ...services.tools import export_tools, export_all_custom_tools, import_tools
from ...services.sections import (
    _generate_and_save_video,
    IMAGE_WIDTHS, IMAGE_ANIMATIONS, IMAGE_MASKS, FILE_EXTENSIONS,
    MEDIA_TYPES, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, FILE_DISPLAYS, MEDIA_IMAGE_EXTS,
    _breadcrumb_starter_html, _divider_starter_html, _resolve_tool_content,
    apply_contact_form,
    _columns_section_or_404, _get_columns_cells, _save_columns_cells, _normalize_cell, _cell_slot,
    _update_banner_classes, _update_banner_overlay_style, _card_div, _update_card_classes,
    _set_card_image, _set_banner_image, _banner_dom_response, _save_card_image_file, _reset_card_style,
    set_card_button, strip_editor_markup,
    IMAGE_WIDTH_PX, BANNER_SIZE_PX, CARD_SIZE_PX, ACCORDION_PANEL_SIZE_PX,
    _generate_and_save_images, _apply_image_to_slot, _list_media,
    _set_accordion_panel_image, apply_accordion_form,
    build_video_gallery, video_gallery_form_clips, set_video_gallery_clip_src,
    apply_faq_form, apply_buy_button_form, apply_shop_form, apply_search_form,
    faq_document_errors, check_faq_document,
)
from ...services import blocks
from . import wants_json, _redirect_next, _undo_snapshot, SHAPE_PRESETS, SHADOW_PRESETS, slugify

# ---------- Sections ----------
# A section is a frame on the page; a tool (Text, Image, Table, Menu, a
# custom tool, ...) is what's placed inside it. _resolve_tool_content()
# is the one place that turns "which tool, with which form fields" into
# (type, content) — shared by creating a brand-new section (section_new)
# and by dropping a different tool onto a frame that already exists
# (section_set_tool), so a frame's tool can be swapped in place instead of
# only ever appending a new frame at the end of the page.



def _saved_upload(field, allowed, refusal):
    """(url, filename, extension, error) for one uploaded file.

    Three routes wrote this out in full -- choose the file, secure the
    name, check the extension against an allowlist, generate a unique
    name, make the folder, save -- and a fourth would have written it
    again. The rule that matters is in CLAUDE.md: never trust a
    client-supplied filename on disk, so `secure_filename` plus a
    generated name, always, and an allowlist rather than a denylist.
    """
    file = request.files.get(field)
    if not file or file.filename == "":
        return None, None, None, refusal
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed:
        return None, None, None, "Please upload one of: %s" % ", ".join(sorted(allowed))
    unique_name = "%s%s" % (uuid.uuid4().hex, ext)
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
    file.save(path)
    return "/static/uploads/%s" % unique_name, filename, ext, None


class _Where:
    """Where one tool's markup lives: a section of its own, or a cell.

    Every "update this tool" route in this file existed twice -- once for
    a tool standing as a section, once for the same tool standing in a
    Columns cell -- and the two differed only in how they read and wrote
    the markup. The interesting half, working out what the new markup
    should be, was already shared; this shares the dull half, so a route
    is now one function registered on both URLs.

    Two things it settles on the way past:

    * **The tool is always named.** The cell versions were split between
      setting `tool_name` and `setdefault`-ing it, and setdefault is
      wrong on a cell that was blank: `_normalize_cell` gives an empty
      cell `tool_name: ""`, which is present, so the name never landed
      and the panel showed a tool with no name. Three tools had that.
    * **A cell holding a tool is `html`.** Some routes set the type and
      some did not; a cell whose content is a tool's markup and whose
      type says "text" is offered a bold/italic ribbon.
    """

    def __init__(self, db, section, cells=None, container=None, index=None):
        self.db = db
        self.section = section
        self.cells = cells
        self.container = container
        self.index = index

    @property
    def is_cell(self):
        return self.container is not None

    @property
    def cell(self):
        return self.container[self.index] if self.is_cell else None

    def read(self):
        """The markup as it stands."""
        if self.is_cell:
            return _normalize_cell(self.container[self.index], "html").get("content", "")
        return self.section["content"] or ""

    def write(self, content, tool_name=None, cell_type="html", **fields):
        """Save the markup, and whatever else this tool remembers.

        `fields` is the small asymmetry between the two containers: a
        section keeps `title`, `file_size` and `media_type` in its own
        columns, while a cell keeps them as keys in its dict. Naming them
        here means an upload route does not have to know which it is
        standing in.
        """
        if self.is_cell:
            cell = _normalize_cell(self.container[self.index], cell_type)
            cell["content"] = content
            cell["type"] = cell_type
            if tool_name:
                cell["tool_name"] = tool_name
            cell.update(fields)
            self.container[self.index] = cell
            _save_columns_cells(self.db, self.section["id"], self.cells)
        else:
            columns = ["content = ?"] + ["%s = ?" % name for name in fields]
            self.db.execute(
                "UPDATE sections SET %s WHERE id = ?" % ", ".join(columns),
                (content, *fields.values(), self.section["id"]),
            )
            self.db.commit()

    def get(self, name, default=None):
        """One field of whichever container this is."""
        if self.is_cell:
            return _normalize_cell(self.container[self.index], "html").get(name, default)
        try:
            return self.section[name]
        except (IndexError, KeyError):
            return default

    def fail(self, message, status=400):
        """A refusal the editor can read, or a flash for a plain post."""
        if wants_json():
            return jsonify({"error": message}), status
        flash(message, "error")
        return _section_home(self.section)

    def respond(self, payload=None):
        """Back where the person was, or an answer in place.

        `payload` is the tool's own reply and is per-route rather than
        automatic, because the tools genuinely differ: a Menu hands back
        `content` to splice into the live nav, a Contact block and a
        declared block hand back `html`, and a Banner hands back the
        class and style its wrapper should now carry. A route that has
        no answer to give passes nothing and keeps redirecting exactly
        as it did.
        """
        if payload is not None and wants_json():
            return jsonify({"ok": True, **payload})
        return _redirect_next("admin.page_edit", page_id=self.section["page_id"],
                              anchor="section-%s" % self.section["id"])


def _where(section_id, col_index=None, row_index=None):
    """(where, bail). `bail` is a response to return when there is nowhere.

    `row_index` is read from the query string when it is not passed,
    because that is where every cell route already looked for it.
    """
    db = get_db()
    if col_index is None:
        section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not section:
            return None, redirect(url_for("admin.dashboard"))
        return _Where(db, section), None
    db, section = _columns_section_or_404(section_id)
    if not section:
        return None, redirect(url_for("admin.dashboard"))
    if row_index is None:
        row_index = request.args.get("row", type=int)
    cells = _get_columns_cells(section)
    slot = _cell_slot(cells, col_index, row_index)
    if slot is None:
        return None, _section_home(section)
    container, index = slot
    return _Where(db, section, cells, container, index), None


def _section_home(section):
    """Where to send somebody when a section route gives up.

    A zone section -- header, sidebar, footer -- belongs to a template and
    has no page_id, and `url_for("admin.page_edit", page_id=None)` does not
    build a URL, it raises. Twenty-seven "that did not work" paths were
    written as a direct redirect to the page editor, so every one of them
    answered 500 instead of redirecting, and only ever for a tool standing
    in a side rail or a footer. `_redirect_next` had already worked this
    out and falls back to the dashboard; this is the same answer for the
    paths that do not go through it.
    """
    if section is not None and section["page_id"]:
        return redirect(url_for("admin.page_edit", page_id=section["page_id"]))
    return redirect(url_for("admin.dashboard"))


@bp.route("/pages/<int:page_id>/sections/new", methods=["POST"])
@login_required
def section_new(page_id):
    db = get_db()
    section_type, content = _resolve_tool_content(db, request.form)
    if section_type is None:
        if wants_json():
            return jsonify({"error": "That tool no longer exists."}), 404
        flash("That tool no longer exists.", "error")
        return redirect(url_for("admin.page_edit", page_id=page_id))
    # `before` (a section id) comes from a divider's own "+"  button, placed
    # between/around every section — lets a new section be inserted at that
    # exact spot instead of always appending at the end.
    before_id = request.form.get("before", type=int)
    before = db.execute(
        "SELECT position FROM sections WHERE id = ? AND page_id = ?", (before_id, page_id)
    ).fetchone() if before_id else None
    if before:
        new_position = before["position"]
        db.execute(
            "UPDATE sections SET position = position + 1 WHERE page_id = ? AND position >= ?",
            (page_id, new_position),
        )
        cur = db.execute(
            "INSERT INTO sections (page_id, type, title, content, position) VALUES (?, ?, '', ?, ?)",
            (page_id, section_type, content, new_position),
        )
    else:
        cur = db.execute(
            "INSERT INTO sections (page_id, type, title, content, position) "
            "VALUES (?, ?, '', ?, (SELECT COALESCE(MAX(position),-1)+1 FROM sections WHERE page_id = ?))",
            (page_id, section_type, content, page_id),
        )
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "id": cur.lastrowid, "type": section_type})
    flash("Section added. Edit it below.", "success")
    return _redirect_next("admin.page_edit", page_id=page_id, anchor=f"section-{cur.lastrowid}")


@bp.route("/templates/<int:template_id>/<zone>/sections/new", methods=["POST"])
@login_required
def zone_section_new(template_id, zone):
    """Header/footer's version of section_new — identical in every way
    except it belongs to a template+zone instead of a page. Every other
    section route (set-tool, divide, columns, delete, ...) works on
    section_id alone and needed no header/footer-specific version at all."""
    if zone not in ("header", "sidebar", "sidebar_right", "footer"):
        return redirect(url_for("admin.dashboard"))
    db = get_db()
    # Each sidebar is a single rail, not a stack of independently addable
    # sections (more rows come from Divide on that one section, not a
    # second top-level section) — the UI never offers an "add" control
    # once it's filled, this just backs that up server-side.
    if zone in ("sidebar", "sidebar_right") and db.execute(
        "SELECT 1 FROM sections WHERE template_id = ? AND zone = ? LIMIT 1", (template_id, zone)
    ).fetchone():
        if wants_json():
            return jsonify({"error": "This sidebar already has a section — use Divide for more rows."}), 400
        flash("This sidebar already has a section — use Divide for more rows.", "error")
        return redirect(url_for("admin.dashboard"))
    section_type, content = _resolve_tool_content(db, request.form)
    if section_type is None:
        if wants_json():
            return jsonify({"error": "That tool no longer exists."}), 404
        flash("That tool no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    before_id = request.form.get("before", type=int)
    before = db.execute(
        "SELECT position FROM sections WHERE id = ? AND template_id = ? AND zone = ?",
        (before_id, template_id, zone),
    ).fetchone() if before_id else None
    if before:
        new_position = before["position"]
        db.execute(
            "UPDATE sections SET position = position + 1 WHERE template_id = ? AND zone = ? AND position >= ?",
            (template_id, zone, new_position),
        )
        cur = db.execute(
            "INSERT INTO sections (template_id, zone, type, title, content, position) VALUES (?, ?, ?, '', ?, ?)",
            (template_id, zone, section_type, content, new_position),
        )
    else:
        cur = db.execute(
            "INSERT INTO sections (template_id, zone, type, title, content, position) "
            "VALUES (?, ?, ?, '', ?, (SELECT COALESCE(MAX(position),-1)+1 FROM sections WHERE template_id = ? AND zone = ?))",
            (template_id, zone, section_type, content, template_id, zone),
        )
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "id": cur.lastrowid, "type": section_type})
    flash("Section added.", "success")
    return _redirect_next("admin.dashboard", anchor=f"section-{cur.lastrowid}")


@bp.route("/templates/<int:template_id>/<zone>/sections/reorder", methods=["POST"])
@login_required
def zone_section_reorder(template_id, zone):
    if zone not in ("header", "sidebar", "sidebar_right", "footer"):
        return jsonify({"error": "not found"}), 404
    db = get_db()
    order = [int(x) for x in request.form.get("order", "").split(",") if x.strip().isdigit()]
    valid_ids = {
        row["id"] for row in db.execute(
            "SELECT id FROM sections WHERE template_id = ? AND zone = ?", (template_id, zone)
        )
    }
    _undo_snapshot(db, f"Reorder {zone}", template_id=template_id, zone=zone, next_url=request.form.get("next"))
    for position, section_id in enumerate(order):
        if section_id in valid_ids:
            db.execute("UPDATE sections SET position = ? WHERE id = ?", (position, section_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/sections/<int:section_id>/set-tool", methods=["POST"])
@login_required
def section_set_tool(section_id):
    """Drop a tool onto an existing section frame — replaces its content
    with the new tool, keeping the same frame (id, position, width,
    bg_color, ...) instead of appending a whole new section."""
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.dashboard"))
    section_type, content = _resolve_tool_content(db, request.form)
    if section_type is None:
        if wants_json():
            return jsonify({"error": "That tool no longer exists."}), 404
        flash("That tool no longer exists.", "error")
        return _section_home(section)
    _undo_snapshot(
        db, "Drop tool onto section",
        page_id=section["page_id"], template_id=section["template_id"], zone=section["zone"],
        next_url=request.form.get("next"),
    )
    db.execute(
        "UPDATE sections SET type = ?, title = '', content = ?, link_url = '', "
        "width = 'normal', animation = 'none', mask_shape = 'none' WHERE id = ?",
        (section_type, content, section_id),
    )
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "id": section_id, "type": section_type})
    flash("Section updated.", "success")
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")




@bp.route("/sections/<int:section_id>/columns/<int:col_index>/set-tool", methods=["POST"])
@login_required
def section_column_set_tool(section_id, col_index):
    """Drop a tool onto one cell of a Columns section — sets just that
    cell's content, leaving every other cell and the column count alone.
    (section_set_tool, above, is for non-columns sections/frames, where the
    whole section is a single cell.)"""
    db, section = _columns_section_or_404(section_id)
    if not section:
        if wants_json():
            return jsonify({"error": "Not a columns section."}), 404
        return redirect(url_for("admin.dashboard"))
    row_index = request.args.get("row", type=int)
    cells = _get_columns_cells(section)
    slot = _cell_slot(cells, col_index, row_index)
    if slot is None:
        if wants_json():
            return jsonify({"error": "Column not found."}), 404
        return _section_home(section)
    container, idx = slot
    tool_id = request.form.get("tool_id", type=int)
    tool = db.execute("SELECT * FROM content_tools WHERE id = ?", (tool_id,)).fetchone() if tool_id else None
    section_type, content = _resolve_tool_content(db, request.form)
    if section_type is None:
        if wants_json():
            return jsonify({"error": "That tool no longer exists."}), 404
        flash("That tool no longer exists.", "error")
        return _section_home(section)
    _undo_snapshot(
        db, "Drop tool into column",
        page_id=section["page_id"], template_id=section["template_id"], zone=section["zone"],
        next_url=request.form.get("next"),
    )
    container[idx] = {
        "type": section_type,
        "content": content,
        "tool_name": tool["name"] if tool else section_type.title(),
    }
    _save_columns_cells(db, section_id, cells)
    if wants_json():
        return jsonify({"ok": True})
    flash("Tool added.", "success")
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/columns/<int:col_index>/clear", methods=["POST"])
@login_required
def section_column_clear(section_id, col_index):
    """The per-cell equivalent of the section-level 'x' delete — removes
    just this cell's tool, reverting it to an empty 'Drop a tool here' cell.
    The Columns section itself and its other cells are untouched."""
    db, section = _columns_section_or_404(section_id)
    if not section:
        return redirect(url_for("admin.dashboard"))
    row_index = request.args.get("row", type=int)
    cells = _get_columns_cells(section)
    slot = _cell_slot(cells, col_index, row_index)
    if slot is not None:
        container, idx = slot
        container[idx] = ""
        _save_columns_cells(db, section_id, cells)
    if wants_json():
        return jsonify({"ok": True})
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/columns/<int:col_index>/rows", methods=["POST"])
@login_required
def section_column_split_rows(section_id, col_index):
    """Divides one column cell into N rows, each its own independent tool
    slot (same shape as any other cell) — mirrors the section-level Divide
    control, one level down. Whatever tool already occupied the cell
    becomes row 0; count=1 merges back down to that single tool, dropping
    the wrapper."""
    db, section = _columns_section_or_404(section_id)
    if not section:
        return redirect(url_for("admin.dashboard"))
    cells = _get_columns_cells(section)
    if not (0 <= col_index < len(cells)):
        return _section_home(section)
    count = request.form.get("rows", type=int) or 1
    count = max(1, min(4, count))
    existing = cells[col_index]
    if isinstance(existing, dict) and existing.get("type") == "rows":
        rows = existing.get("rows", [])
    else:
        rows = [existing]
    if count == 1:
        cells[col_index] = rows[0] if rows else ""
    else:
        rows = (rows + [""] * count)[:count]
        cells[col_index] = {"type": "rows", "rows": rows, "tool_name": "Rows"}
    _save_columns_cells(db, section_id, cells)
    if wants_json():
        return jsonify({"ok": True})
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/columns/<int:col_index>/update", methods=["POST"])
@login_required
def section_column_update(section_id, col_index):
    """Per-cell version of section_update — saves whichever fields the
    cell's placed tool needs (text content, image link/width/animation/mask,
    file display style, ...), scoped to just that one cell's dict."""
    db, section = _columns_section_or_404(section_id)
    if not section:
        if wants_json():
            return jsonify({"error": "not found"}), 404
        return redirect(url_for("admin.dashboard"))
    row_index = request.args.get("row", type=int)
    cells = _get_columns_cells(section)
    slot = _cell_slot(cells, col_index, row_index)
    if slot is None:
        if wants_json():
            return jsonify({"error": "bad index"}), 404
        return _section_home(section)
    container, idx = slot
    cell = _normalize_cell(container[idx])
    if "content" in request.form:
        cell["content"] = strip_editor_markup(request.form.get("content", ""))
    if "title" in request.form:
        cell["title"] = request.form.get("title", "")
    if "width" in request.form and request.form["width"] in IMAGE_WIDTHS:
        cell["width"] = request.form["width"]
    if "animation" in request.form and request.form["animation"] in IMAGE_ANIMATIONS:
        cell["animation"] = request.form["animation"]
    if "mask_shape" in request.form and request.form["mask_shape"] in IMAGE_MASKS:
        cell["mask_shape"] = request.form["mask_shape"]
    if "media_type" in request.form and request.form["media_type"] in MEDIA_TYPES:
        cell["media_type"] = request.form["media_type"]
    if "link_url" in request.form:
        cell["link_url"] = request.form.get("link_url", "").strip()
    #  A caption is part of the Image tool wherever it stands. The field
    #  existed for a section and not for a cell, which is why the same
    #  tool offered it in one place and not the other.
    if "caption" in request.form:
        cell["caption"] = request.form.get("caption", "").strip()
    if "file_display" in request.form and request.form["file_display"] in FILE_DISPLAYS:
        cell["file_display"] = request.form["file_display"]
    #  A cell holds a tool, so it gets the tool level of Corners too.
    if "corner_style" in request.form:
        value = request.form["corner_style"]
        if value in SHAPE_PRESETS or value == "":
            cell["corner_style"] = value
    if "shadow_style" in request.form:
        value = request.form["shadow_style"]
        if value in SHADOW_PRESETS or value == "":
            cell["shadow_style"] = value
    container[idx] = cell
    _save_columns_cells(db, section_id, cells)
    if wants_json():
        return jsonify({"ok": True})
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/menu-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/menu-update", methods=["POST"])
@login_required
def section_menu_update(section_id, col_index=None):
    """Which pages a Menu shows, and how -- configured where it stands."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    #  A Menu in a side rail stands up rather than across. A cell has no
    #  zone of its own, so it takes the ordinary default.
    default_direction = ("vertical" if not where.is_cell
                         and where.section["zone"] in ("sidebar", "sidebar_right")
                         else "horizontal")
    content = _menu_updated_html(where.db, request.form, default_direction)
    where.write(content, tool_name="Menu")
    #  A plain page-checkbox toggle is the single most common edit this
    #  form makes -- reloading the whole page for it scrolls back to
    #  wherever the section happens to sit, which for a full-height zone
    #  like the sidebar is always near the very top. The editor splices
    #  this HTML into the live <nav> instead.
    return where.respond({"content": content})


@bp.route("/sections/<int:section_id>/breadcrumb-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/breadcrumb-update", methods=["POST"])
@login_required
def section_breadcrumb_update(section_id, col_index=None):
    """Breadcrumb is placed with its defaults and reconfigured in place. The %%CMS_BREADCRUMB%% placeholder is rebuilt fresh each time, so this cannot accidentally destroy it the way editing resolved HTML would."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = _breadcrumb_starter_html(request.form.get("size"), request.form.get("style"))
    where.write(content, tool_name="Breadcrumb")
    return where.respond()


@bp.route("/sections/<int:section_id>/divider-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/divider-update", methods=["POST"])
@login_required
def section_divider_update(section_id, col_index=None):
    """A Divider's style, width, spacing and colour."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = _divider_starter_html(
        request.form.get("divider_style"), request.form.get("divider_width"),
        request.form.get("divider_spacing"), request.form.get("divider_color"),
    )
    where.write(content, tool_name="Divider")
    return where.respond()


@bp.route("/sections/<int:section_id>/buy-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/buy-update", methods=["POST"])
@login_required
def section_buy_update(section_id, col_index=None):
    """What this button sells, and how it looks."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    #  Read back from what is already there, so a submit that changes one
    #  field keeps the rest.
    content = apply_buy_button_form(where.read())
    where.write(content, tool_name="Buy Button")
    return where.respond()


@bp.route("/sections/<int:section_id>/block-update/<key>", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/block-update/<key>", methods=["POST"])
@login_required
def section_block_update(section_id, key, col_index=None):
    """Saves any declared block. One route for all of them -- see services/blocks.py for why the alternative was eight of these."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    if key not in blocks.BLOCKS:
        return redirect(url_for("admin.dashboard"))
    content = blocks.apply_form(key, request.form, where.read())
    where.write(content, tool_name=blocks.BLOCKS[key]["name"])
    #  Hand the rebuilt block back so the editor can swap it in place. A
    #  declared block used to need an explicit Apply and a page load, while
    #  every other tool changed as you changed it.
    return where.respond({"html": content})


@bp.route("/sections/<int:section_id>/shop-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/shop-update", methods=["POST"])
@login_required
def section_shop_update(section_id, col_index=None):
    """How the storefront is laid out. What is FOR SALE is read live at render time, never stored here -- see build_shop."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = apply_shop_form()
    where.write(content, tool_name="Shop")
    return where.respond()


@bp.route("/sections/<int:section_id>/basket-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/basket-update", methods=["POST"])
@login_required
def section_basket_update(section_id, col_index=None):
    """How the basket looks. What is in it is never stored here."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    from ...services import cart as cart_service
    content = cart_service.apply_basket_form(request.form)
    where.write(content, tool_name="Basket")
    return where.respond()


@bp.route("/sections/<int:section_id>/blog-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/blog-update", methods=["POST"])
@login_required
def section_blog_update(section_id, col_index=None):
    """Which blog this tool shows, how, and how many -- one submit."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = blog_service.apply_blog_form(where.db, request.form)
    where.write(content, tool_name="Blog")
    return where.respond()


@bp.route("/sections/<int:section_id>/search-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/search-update", methods=["POST"])
@login_required
def section_search_update(section_id, col_index=None):
    """One submit rebuilds the search control -- the same shape as every other derived tool (see apply_search_form)."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = apply_search_form(request.form)
    where.write(content, tool_name="Search")
    return where.respond()


@bp.route("/sections/<int:section_id>/contact-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/contact-update", methods=["POST"])
@login_required
def section_contact_update(section_id, col_index=None):
    """Rebuilds a Contact Info block from the form's own fields.\n\n    The block IS the storage -- build_contact_tool writes the phone\n    number into the markup and read_contact_tool takes it back out --\n    so one submit rebuilds the whole thing, carrying every row plus\n    any +/- that was pressed. Same shape as Search, FAQ and the\n    Accordion's panels.\n    """
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = apply_contact_form(where.read())
    where.write(content, tool_name="Contact Info")
    #  The rebuilt block goes back to the editor so it swaps in place.
    #  Without this the form posted, saved, and then failed to read a
    #  redirect as JSON -- so every keystroke saved correctly and reported
    #  "couldn't save", which is worse than either.
    return where.respond({"html": content})


@bp.route("/sections/<int:section_id>/faq-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/faq-update", methods=["POST"])
@login_required
def section_faq_update(section_id, col_index=None):
    """Questions, answers, style, one-at-a-time and any add/remove -- one submit, one rebuild (see apply_faq_form)."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    #  Checked before it is parsed. A document that would produce no
    #  usable FAQ is refused rather than saved into an empty-looking
    #  block, and the text is handed back with what to fix -- losing what
    #  somebody just pasted would be a worse answer than any error.
    if "faq_md" in request.form:
        report = check_faq_document(request.form.get("faq_md", ""))
        if any(p["level"] == "error" for p in report):
            session["faq_report"] = {"section": section_id, "problems": report,
                                     "draft": request.form.get("faq_md", "")}
            return where.respond()
        session["faq_report"] = ({"section": section_id, "problems": report,
                                  "draft": ""} if report else None)
    where.write(apply_faq_form(where.read()), tool_name="FAQ")
    return where.respond()


@bp.route("/sections/<int:section_id>/video-gallery-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/video-gallery-update", methods=["POST"])
@login_required
def section_video_gallery_update(section_id, col_index=None):
    """One submit rebuilds the whole gallery from the form's clip rows (see\n    video_gallery_form_clips) -- including the +/x buttons, which just\n    add or drop a row before the rebuild. Same shape as the Menu tool:\n    the markup is derived state, never hand-edited, so there is no way\n    for the clip list and the rendered thumbnails to disagree.\n    """
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = build_video_gallery(
        video_gallery_form_clips(request.form), request.form.get("layout")
    )
    where.write(content, tool_name="Video Gallery")
    return where.respond()


@bp.route("/sections/<int:section_id>/video-gallery/<int:clip_index>/upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/video-gallery/<int:clip_index>/upload", methods=["POST"])
@login_required
def section_video_gallery_clip_upload(section_id, clip_index, col_index=None):
    """Puts an uploaded video into one clip of a gallery. The gallery is
    not YouTube-only: a site can show its own footage without publishing
    it to a third party first."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, error = _save_gallery_clip_file()
    if error:
        return jsonify({"error": error[0]}), error[1]
    where.write(set_video_gallery_clip_src(where.read(), clip_index, url),
                tool_name="Video Gallery")
    return jsonify({"ok": True, "url": url})


@bp.route("/sections/<int:section_id>/banner-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/banner-update", methods=["POST"])
@login_required
def section_banner_update(section_id, col_index=None):
    """A Banner's shape, how its picture is attached, and its overlay."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = _update_banner_classes(where.read(), request.form.get("shape"),
                                     request.form.get("attachment"))
    content = _update_banner_overlay_style(content, request.form)
    where.write(content, tool_name="Banner", cell_type="banner")
    return where.respond(_banner_dom_response(content))


@bp.route("/sections/<int:section_id>/banner-image-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/banner-image-upload", methods=["POST"])
@login_required
def section_banner_image_upload(section_id, col_index=None):
    """The picture behind a Banner."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, error = _save_card_image_file()
    if error:
        return jsonify({"error": error[0]}), error[1]
    where.write(_set_banner_image(where.read(), url), tool_name="Banner", cell_type="banner")
    return jsonify({"ok": True, "url": url})


@bp.route("/sections/<int:section_id>/banner-image-clear", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/banner-image-clear", methods=["POST"])
@login_required
def section_banner_image_clear(section_id, col_index=None):
    """Takes the picture out of a Banner and leaves the words."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    where.write(_set_banner_image(where.read(), None), cell_type="banner")
    return where.respond()


@bp.route("/sections/<int:section_id>/card-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/card-update", methods=["POST"])
@login_required
def section_card_update(section_id, col_index=None):
    """A Card's shape, colour, and the button along its foot."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    content = _update_card_classes(where.read(), request.form.get("shape"),
                                   request.form.get("color", ""))
    content = set_card_button(content, request.form.get("button"),
                              request.form.get("button_link", ""))
    where.write(content, tool_name="Card", cell_type="card")
    _, div = _card_div(content)
    return where.respond({
        "class": " ".join(div.get("class") or []) if div is not None else "cms-card-shape",
        "style": div.get("style", "") if div is not None else "",
    })


@bp.route("/sections/<int:section_id>/card-reset", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/card-reset", methods=["POST"])
@login_required
def section_card_reset(section_id, col_index=None):
    """Puts a Card back to the theme's own shape and colour."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    where.write(_reset_card_style(where.read()), tool_name="Card", cell_type="card")
    _, div = _card_div(where.read())
    return where.respond({
        "class": " ".join(div.get("class") or []) if div is not None else "cms-card-shape",
        "style": div.get("style", "") if div is not None else "",
    })


@bp.route("/sections/<int:section_id>/card-image-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/card-image-upload", methods=["POST"])
@login_required
def section_card_image_upload(section_id, col_index=None):
    """The picture at the top of a Card."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, error = _save_card_image_file()
    if error:
        return jsonify({"error": error[0]}), error[1]
    where.write(_set_card_image(where.read(), url), tool_name="Card", cell_type="card")
    return jsonify({"ok": True, "url": url})


@bp.route("/sections/<int:section_id>/card-image-clear", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/card-image-clear", methods=["POST"])
@login_required
def section_card_image_clear(section_id, col_index=None):
    """Takes the picture out of a Card and leaves the words."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    where.write(_set_card_image(where.read(), None), cell_type="card")
    return where.respond()


@bp.route("/sections/<int:section_id>/accordion-update", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/accordion-update", methods=["POST"])
@login_required
def section_accordion_update(section_id, col_index=None):
    """One submit carries the whole tool state: every caption at once (see\n    _set_accordion_captions -- they are plain text with no independent\n    async action, unlike each panel's image), the display style, the\n    click-to-enlarge flag, and any add/remove-panel button that was\n    pressed. Captions are applied first so a caption typed in the same\n    submit as a remove-panel click is still saved to the panels that
    survive.\n    """
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    where.write(apply_accordion_form(where.read()), tool_name="Accordion")
    return where.respond({})


@bp.route("/sections/<int:section_id>/accordion/<int:panel_index>/image-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/accordion/<int:panel_index>/image-upload", methods=["POST"])
@login_required
def section_accordion_image_upload(section_id, panel_index, col_index=None):
    """A picture for one panel of an Accordion."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, error = _save_card_image_file()
    if error:
        return jsonify({"error": error[0]}), error[1]
    where.write(_set_accordion_panel_image(where.read(), panel_index, url),
                tool_name="Accordion")
    return jsonify({"ok": True, "url": url})


@bp.route("/sections/<int:section_id>/accordion/<int:panel_index>/image-generate", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/accordion/<int:panel_index>/image-generate", methods=["POST"])
@login_required
def section_accordion_image_generate(section_id, panel_index, col_index=None):
    """A few panel-shaped pictures to choose from."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    images, error = _generate_and_save_images(where.db, *ACCORDION_PANEL_SIZE_PX)
    if error and not images:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "images": images, "error": error})


@bp.route("/sections/<int:section_id>/accordion/<int:panel_index>/image-apply", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/accordion/<int:panel_index>/image-apply", methods=["POST"])
@login_required
def section_accordion_image_apply(section_id, panel_index, col_index=None):
    """Puts a picture already in the library into one panel."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url = packages.adopt_template_picture(
        request.form.get("url", ""), current_app.static_folder,
        current_app.config["UPLOAD_FOLDER"])
    if not url:
        return jsonify({"error": "Couldn't apply that image."}), 400
    where.write(_set_accordion_panel_image(where.read(), panel_index, url),
                tool_name="Accordion")
    return jsonify({"ok": True, "url": url})


@bp.route("/sections/<int:section_id>/image-generate", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/image-generate", methods=["POST"])
@login_required
def section_image_generate(section_id, col_index=None):
    """Asks the picture generator for a few to choose from."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    #  Asked for at the size the picture will be shown at. A section
    #  knows its own width; a cell takes the middle size, because a cell's
    #  width is the column's and is not stored on the tool.
    size = (IMAGE_WIDTH_PX.get(where.get("width"), IMAGE_WIDTH_PX["medium"])
            if not where.is_cell else IMAGE_WIDTH_PX["medium"])
    images, error = _generate_and_save_images(where.db, *size)
    if error and not images:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "images": images, "error": error})


@bp.route("/sections/<int:section_id>/banner-image-generate", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/banner-image-generate", methods=["POST"])
@login_required
def section_banner_image_generate(section_id, col_index=None):
    """A few banner-shaped pictures to choose from."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    images, error = _generate_and_save_images(where.db, *BANNER_SIZE_PX)
    if error and not images:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "images": images, "error": error})


@bp.route("/sections/<int:section_id>/card-image-generate", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/card-image-generate", methods=["POST"])
@login_required
def section_card_image_generate(section_id, col_index=None):
    """A few card-shaped pictures to choose from."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    images, error = _generate_and_save_images(where.db, *CARD_SIZE_PX)
    if error and not images:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True, "images": images, "error": error})


@bp.route("/sections/<int:section_id>/image-apply", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/image-apply", methods=["POST"])
@login_required
def section_image_apply(section_id, col_index=None):
    """Puts a picture already in the library onto a tool.

    `_apply_image_to_slot` has always taken the column index (None for a
    section), so these two were the same function with one argument
    hard-coded -- the last pair in this file that differed by nothing at
    all.
    """
    url = packages.adopt_template_picture(
        request.form.get("url", ""), current_app.static_folder,
        current_app.config["UPLOAD_FOLDER"])
    if not url or not _apply_image_to_slot(get_db(), section_id, col_index,
                                           request.form.get("kind", ""), url):
        return jsonify({"error": "Couldn't apply that image."}), 400
    return jsonify({"ok": True, "url": url})


@bp.route("/images")
@login_required
def image_library():
    image_only = request.args.get("picker") == "1"
    items = _list_media(image_only=image_only)
    if image_only:
        #  The same set the section-background picker offers: uploads plus
        #  every installed template's pictures. Two pickers offering
        #  different halves of what exists is worse than either.
        from ..public import _pickable_images
        have = {i["url"] for i in items}
        db_tpl = get_db().execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
        for extra in _pickable_images(db_tpl):
            if extra["url"] not in have:
                items.append({"filename": extra["name"], "url": extra["url"],
                              "is_image": True, "prompt": None, "source": "Template"})
    if wants_json():
        return jsonify({"images": items})
    return render_template("admin/image_library.html", images=items)


@bp.route("/images/upload", methods=["POST"])
@login_required
def image_library_upload():
    """Adds a picture to the Media Library and says where it landed.

    Every upload route until now attached its file to one particular
    section, which is no use to a form field that just wants a picture --
    a team member's photo had to be uploaded somewhere else first, then
    found again in a dropdown by filename. Uploads land in the same folder
    the Library lists, so a picture chosen this way is in the Library too.
    """
    url, error = _save_card_image_file()
    if error:
        message, status = error
        return jsonify({"error": message}), status
    return jsonify({"ok": True, "url": url})


@bp.route("/images/generate-from", methods=["POST"])
@login_required
def generate_image_from_library():
    """"Use to generate new image" in the Library's lightbox — an i2i
    variation of an existing file (upload or prior generation) rather than
    generating from a blank prompt. Only saves to the library/disk; there's
    no section context here to auto-apply it to (unlike the per-section
    Generate buttons), so the admin picks it up from the Library afterward
    the same way they would any other reusable image."""
    db = get_db()
    source_filename = os.path.basename(request.form.get("source_filename", ""))
    prompt = (request.form.get("prompt") or "").strip()
    if not source_filename or not prompt:
        return jsonify({"error": "A description is required."}), 400
    source_path = os.path.join(current_app.config["UPLOAD_FOLDER"], source_filename)
    if os.path.commonpath([source_path, current_app.config["UPLOAD_FOLDER"]]) != current_app.config["UPLOAD_FOLDER"] or not os.path.isfile(source_path):
        return jsonify({"error": "Source image not found."}), 404
    ext = os.path.splitext(source_filename)[1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}.get(ext.lstrip("."), "image/png")
    with open(source_path, "rb") as f:
        reference_bytes = f.read()
    try:
        image_bytes = ai_image.generate_image(db, prompt, reference_image_bytes=reference_bytes, reference_mime=mime)
    except ai_image.ImageGenError as e:
        return jsonify({"error": str(e)}), 400
    unique_name = f"{uuid.uuid4().hex}.png"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(image_bytes)
    url = f"/static/uploads/{unique_name}"
    db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
    db.commit()
    return jsonify({"ok": True, "url": url, "filename": unique_name})


@bp.route("/images/<path:filename>/delete", methods=["POST"])
@login_required
def generated_image_delete(filename):
    filename = os.path.basename(filename)
    db = get_db()
    db.execute("DELETE FROM generated_images WHERE url = ?", (f"/static/uploads/{filename}",))
    db.commit()
    # Best-effort: remove the file too. Deliberately not checking whether
    # any section still references this file first — the admin explicitly
    # asked to delete it (the Library page warns about this), so honor
    # that rather than silently keeping an orphaned file around.
    try:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        if os.path.commonpath([path, current_app.config["UPLOAD_FOLDER"]]) == current_app.config["UPLOAD_FOLDER"]:
            os.remove(path)
    except OSError:
        pass
    if wants_json():
        return jsonify({"ok": True})
    flash("File deleted.", "success")
    return redirect(url_for("admin.image_library"))


@bp.route("/sections/<int:section_id>/update", methods=["POST"])
@login_required
def section_update(section_id):
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        flash("Section not found.", "error")
        return redirect(url_for("admin.dashboard"))

    fields, values = [], []
    if "title" in request.form:
        fields.append("title = ?")
        values.append(request.form.get("title", ""))
    if "content" in request.form:
        fields.append("content = ?")
        values.append(strip_editor_markup(request.form.get("content", "")))
    if "width" in request.form and request.form["width"] in IMAGE_WIDTHS:
        fields.append("width = ?")
        values.append(request.form["width"])
    if "animation" in request.form and request.form["animation"] in IMAGE_ANIMATIONS:
        fields.append("animation = ?")
        values.append(request.form["animation"])
    if "mask_shape" in request.form and request.form["mask_shape"] in IMAGE_MASKS:
        fields.append("mask_shape = ?")
        values.append(request.form["mask_shape"])
    if "media_type" in request.form and request.form["media_type"] in MEDIA_TYPES:
        fields.append("media_type = ?")
        values.append(request.form["media_type"])
    if "link_url" in request.form:
        fields.append("link_url = ?")
        values.append(request.form.get("link_url", "").strip())
    #  Stored as plain words and rendered escaped: a caption is one line
    #  of description, never markup, so there is nothing here that has to
    #  survive as HTML.
    if "caption" in request.form:
        fields.append("caption = ?")
        values.append(request.form.get("caption", "").strip() or None)
    #  The tool's own corner, as distinct from its section's — see db.py.
    if "tool_corner_style" in request.form:
        value = request.form["tool_corner_style"]
        if value in SHAPE_PRESETS or value == "":
            fields.append("tool_corner_style = ?")
            values.append(value or None)
    if "tool_shadow_style" in request.form:
        value = request.form["tool_shadow_style"]
        if value in SHADOW_PRESETS or value == "":
            fields.append("tool_shadow_style = ?")
            values.append(value or None)
    if "file_display" in request.form and request.form["file_display"] in FILE_DISPLAYS:
        fields.append("file_display = ?")
        values.append(request.form["file_display"])
    #  A picture behind the section, with how much to dim it and where to
    #  anchor it. Chosen from the Image Library rather than uploaded here,
    #  so there is one place files live.
    if "bg_image" in request.form:
        #  Picked from a template's own pictures? Take a copy into the
        #  library and point at that, so this page keeps its background
        #  even if the template it came from is deleted later. See
        #  packages.adopt_template_picture.
        chosen = (request.form.get("bg_image") or "").strip()
        if chosen:
            chosen = packages.adopt_template_picture(
                chosen, current_app.static_folder, current_app.config["UPLOAD_FOLDER"])
        fields.append("bg_image = ?")
        values.append(chosen or None)
    if "bg_overlay" in request.form:
        overlay = (request.form.get("bg_overlay") or "").strip()
        fields.append("bg_overlay = ?")
        values.append(overlay if overlay in ("light", "medium", "dark", "tint") else None)
    if "bg_position" in request.form:
        position = (request.form.get("bg_position") or "").strip()
        fields.append("bg_position = ?")
        values.append(position if position in ("center", "top", "bottom", "fixed") else None)
    if "bg_color" in request.form:
        bg = request.form.get("bg_color", "").strip()
        if not bg or re.match(r"^#[0-9a-fA-F]{6}$", bg):
            fields.append("bg_color = ?")
            values.append(bg or None)
    if "shadow_style" in request.form:
        shadow = request.form.get("shadow_style", "").strip()
        if not shadow or shadow in SHADOW_PRESETS:
            fields.append("shadow_style = ?")
            values.append(shadow or None)
    if "corner_style" in request.form:
        corner = request.form.get("corner_style", "").strip()
        if not corner or corner in SHAPE_PRESETS:
            fields.append("corner_style = ?")
            values.append(corner or None)
    if "border_color" in request.form:
        border = request.form.get("border_color", "").strip()
        if not border or re.match(r"^#[0-9a-fA-F]{6}$", border):
            fields.append("border_color = ?")
            values.append(border or None)
    if "layout_width" in request.form and request.form["layout_width"] in ("auto", "full", "custom"):
        fields.append("layout_width = ?")
        values.append(request.form["layout_width"])
    if "layout_width_pct" in request.form:
        pct = request.form.get("layout_width_pct", type=int)
        if pct is not None:
            pct = max(10, min(100, pct))
        fields.append("layout_width_pct = ?")
        values.append(pct)
    # Sidebar sections reuse layout_width/layout_width_pct for HEIGHT (see
    # site-base.css) since width there is never a free axis for the
    # SECTION itself — but the RAIL's own width (the 240px default) still
    # is, so it gets its own independent pair here rather than fighting
    # over the same one.
    if "sidebar_width" in request.form and request.form["sidebar_width"] in ("auto", "custom"):
        fields.append("sidebar_width = ?")
        values.append(request.form["sidebar_width"])
    if "sidebar_width_px" in request.form:
        px = request.form.get("sidebar_width_px", type=int)
        if px is not None:
            px = max(160, min(600, px))
        fields.append("sidebar_width_px = ?")
        values.append(px)
    # Horizontal (non-sidebar) sections: an explicit height set by dragging
    # the section's bottom edge — empty string clears it back to auto.
    if "content_height_px" in request.form:
        raw = request.form.get("content_height_px", "").strip()
        height_px = int(raw) if raw.isdigit() else None
        if height_px is not None:
            height_px = max(60, min(2000, height_px))
        fields.append("content_height_px = ?")
        values.append(height_px)

    if fields:
        values.append(section_id)
        db.execute(f"UPDATE sections SET {', '.join(fields)} WHERE id = ?", values)
        db.commit()

    if wants_json():
        return jsonify({"ok": True})
    flash("Section saved.", "success")
    return _redirect_next("admin.page_edit", page_id=section["page_id"])


@bp.route("/sections/<int:section_id>/delete", methods=["POST"])
@login_required
def section_delete(section_id):
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.dashboard"))
    _undo_snapshot(
        db, "Delete section",
        page_id=section["page_id"], template_id=section["template_id"], zone=section["zone"],
        next_url=request.form.get("next"),
    )
    db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    return _redirect_next("admin.page_edit", page_id=section["page_id"])


@bp.route("/sections/<int:section_id>/divide", methods=["POST"])
@login_required
def section_divide(section_id):
    """The section-level "Divide" control — splits any section into N
    columns (or merges back to 1), instead of choosing a column count up
    front when adding the section. Existing content is preserved as the
    first cell going in, or as the whole section's content coming back out."""
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.dashboard"))
    count = request.form.get("columns", type=int) or 1
    count = max(1, min(6, count))
    _undo_snapshot(
        db, "Divide section",
        page_id=section["page_id"], template_id=section["template_id"], zone=section["zone"],
        next_url=request.form.get("next"),
    )

    if section["type"] == "columns":
        try:
            cells = json.loads(section["content"]).get("columns", [])
        except (ValueError, AttributeError):
            cells = []
    else:
        cells = [section["content"] or ""]

    if count == 1:
        #  Collapsing back to one column keeps whatever was in the first
        #  cell, including a tool. A cell is a string when it holds plain
        #  words and a dict when it holds a tool -- and this used to assume
        #  the string, writing the dict itself into a TEXT column: dividing
        #  a section back down with anything but text in its first cell
        #  raised "type 'dict' is not supported" and answered 500. A tool
        #  has to survive being moved, and merging a column is moving it.
        first = cells[0] if cells else ""
        if isinstance(first, dict) and first.get("rows"):
            #  That cell is itself split into rows. Flattening it would
            #  throw the other rows away, so the section stays a Columns
            #  block of one column and keeps them.
            db.execute("UPDATE sections SET type = 'columns', content = ? WHERE id = ?",
                       (json.dumps({"columns": [first]}), section_id))
        elif isinstance(first, dict):
            db.execute("UPDATE sections SET type = ?, content = ? WHERE id = ?",
                       (first.get("type") or "text", first.get("content") or "", section_id))
        else:
            db.execute("UPDATE sections SET type = 'text', content = ? WHERE id = ?",
                       (first, section_id))
    else:
        cells = (cells + [""] * count)[:count]
        db.execute(
            "UPDATE sections SET type = 'columns', content = ? WHERE id = ?",
            (json.dumps({"columns": cells}), section_id),
        )
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    flash("Section divided.", "success")
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/clear", methods=["POST"])
@login_required
def section_clear(section_id):
    """Empties a section's content but keeps the section (and its layout —
    type, width, columns count, etc.) in place, unlike Delete which removes
    the whole section."""
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.dashboard"))
    content = ""
    if section["type"] == "columns":
        try:
            count = len(json.loads(section["content"]).get("columns", []))
        except (ValueError, AttributeError):
            count = 2
        content = json.dumps({"columns": [""] * max(count, 1)})
    _undo_snapshot(
        db, "Clear section",
        page_id=section["page_id"], template_id=section["template_id"], zone=section["zone"],
        next_url=request.form.get("next"),
    )
    db.execute("UPDATE sections SET title = '', content = ?, link_url = '' WHERE id = ?", (content, section_id))
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    flash("Section content cleared.", "success")
    return _redirect_next("admin.page_edit", page_id=section["page_id"], anchor=f"section-{section_id}")


@bp.route("/sections/<int:section_id>/move", methods=["POST"])
@login_required
def section_move(section_id):
    """Swaps a section with its immediate neighbor — the keyboard/click
    alternative to drag-and-drop reordering (same net effect: only the two
    swapped rows' `position` changes). Works for a page's body sections
    (page_id-scoped) exactly the same as for a header/footer/sidebar
    section (template_id+zone-scoped) — whichever this section actually
    belongs to."""
    db = get_db()
    direction = request.form.get("direction")
    section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not section:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.dashboard"))
    page_id = section["page_id"]
    if page_id is not None:
        siblings = db.execute(
            "SELECT * FROM sections WHERE page_id = ? ORDER BY position", (page_id,)
        ).fetchall()
    else:
        siblings = db.execute(
            "SELECT * FROM sections WHERE template_id = ? AND zone = ? ORDER BY position",
            (section["template_id"], section["zone"]),
        ).fetchall()
    idx = next((i for i, s in enumerate(siblings) if s["id"] == section_id), None)
    if idx is None:
        if wants_json():
            return jsonify({"error": "Section not found."}), 404
        return redirect(url_for("admin.page_edit", page_id=page_id) if page_id else url_for("admin.dashboard"))
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(siblings):
        other = siblings[swap_idx]
        _undo_snapshot(
            db, "Move section",
            page_id=page_id, template_id=section["template_id"], zone=section["zone"],
            next_url=request.form.get("next"),
        )
        db.execute("UPDATE sections SET position = ? WHERE id = ?", (other["position"], section["id"]))
        db.execute("UPDATE sections SET position = ? WHERE id = ?", (section["position"], other["id"]))
        db.commit()
    if wants_json():
        return jsonify({"ok": True})
    if page_id:
        return _redirect_next("admin.page_edit", page_id=page_id, anchor=f"section-{section_id}")
    return _redirect_next("admin.dashboard", anchor=f"section-{section_id}")


@bp.route("/pages/<int:page_id>/sections/reorder", methods=["POST"])
@login_required
def section_reorder(page_id):
    """Drag-and-drop reordering: body is a comma-separated list of section
    ids in their new order. Ids belonging to a different page are ignored."""
    db = get_db()
    order = [int(x) for x in request.form.get("order", "").split(",") if x.strip().isdigit()]
    valid_ids = {
        row["id"] for row in db.execute("SELECT id FROM sections WHERE page_id = ?", (page_id,))
    }
    _undo_snapshot(db, "Reorder sections", page_id=page_id, next_url=request.form.get("next"))
    for position, section_id in enumerate(order):
        if section_id in valid_ids:
            db.execute("UPDATE sections SET position = ? WHERE id = ?", (position, section_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/sections/<int:section_id>/image-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/image-upload", methods=["POST"])
@login_required
def section_image_upload(section_id, col_index=None):
    """A picture, uploaded to wherever the Image tool is standing."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, _filename, _ext, error = _saved_upload(
        "image", MEDIA_IMAGE_EXTS, "Please choose an image file.")
    if error:
        return where.fail(error)
    where.write(url, tool_name="Image", cell_type="image")
    if wants_json():
        return jsonify({"ok": True, "url": url})
    flash("Image uploaded!", "success")
    return where.respond()


@bp.route("/sections/<int:section_id>/file-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/file-upload", methods=["POST"])
@login_required
def section_file_upload(section_id, col_index=None):
    """A file to download, uploaded to wherever the File tool is standing."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, filename, _ext, error = _saved_upload(
        "file", FILE_EXTENSIONS, "Please choose a file.")
    if error:
        return where.fail(error)
    size = os.path.getsize(os.path.join(current_app.config["UPLOAD_FOLDER"],
                                        os.path.basename(url)))
    #  The name it arrived under becomes the label, unless this tool has
    #  already been given one -- somebody who titled the download does not
    #  want that replaced by "final-v3-FINAL.pdf".
    where.write(url, tool_name="File / Download", cell_type="file",
                title=where.get("title") or filename, file_size=size)
    if wants_json():
        return jsonify({"ok": True, "url": url, "filename": filename, "size": size})
    flash("File uploaded!", "success")
    return where.respond()


@bp.route("/upload-image", methods=["POST"])
@login_required
def upload_image():
    """Generic image upload, not tied to a section — used by the WYSIWYG
    toolbar's Insert Image button so images can be mixed with text inside
    tables, cards, and text sections."""
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"error": "Please choose an image file."}), 400
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        return jsonify({"error": "Please upload a PNG, JPG, GIF, WEBP, or SVG image."}), 400
    unique_name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name))
    return jsonify({"ok": True, "url": f"/static/uploads/{unique_name}"})


@bp.route("/sections/<int:section_id>/media-upload", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/media-upload", methods=["POST"])
@login_required
def section_media_upload(section_id, col_index=None):
    """An audio or video file, uploaded to wherever the Media Player is standing. Which of the two it is comes from the extension, since the player needs to know before it can draw itself."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, _filename, ext, error = _saved_upload(
        "media", set(VIDEO_EXTENSIONS) | set(AUDIO_EXTENSIONS),
        "Please choose an audio or video file.")
    if error:
        return where.fail(error)
    media_type = "video" if ext in VIDEO_EXTENSIONS else "audio"
    where.write(url, tool_name="Media Player", cell_type="media", media_type=media_type)
    if wants_json():
        return jsonify({"ok": True, "url": url, "media_type": media_type})
    return where.respond()


@bp.route("/sections/<int:section_id>/media-generate", methods=["POST"])
@bp.route("/sections/<int:section_id>/columns/<int:col_index>/media-generate", methods=["POST"])
@login_required
def section_media_generate(section_id, col_index=None):
    """Asks the video generator for a clip and puts it in place."""
    where, bail = _where(section_id, col_index)
    if bail:
        return bail
    url, error = _generate_and_save_video(where.db)
    if error:
        return jsonify({"error": error}), 400
    where.write(url, tool_name="Media Player", cell_type="media", media_type="video")
    return jsonify({"ok": True, "url": url, "media_type": "video"})


@bp.route("/tools/reorder", methods=["POST"])
@login_required
def tools_reorder():
    """Drag-and-drop reordering of the Tools panel itself: body is a
    comma-separated list of tool ids in their new order. Same shape as
    section_reorder — an id belonging to nobody is silently skipped, so a
    stale list from a slow tab can never corrupt another tool's position."""
    db = get_db()
    order = [int(x) for x in request.form.get("order", "").split(",") if x.strip().isdigit()]
    valid_ids = {row["id"] for row in db.execute("SELECT id FROM content_tools")}
    for position, tool_id in enumerate(order):
        if tool_id in valid_ids:
            db.execute("UPDATE content_tools SET position = ? WHERE id = ?", (position, tool_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/tools/<int:tool_id>/delete", methods=["POST"])
@login_required
def tool_delete(tool_id):
    db = get_db()
    tool = db.execute("SELECT * FROM content_tools WHERE id = ?", (tool_id,)).fetchone()
    if not tool:
        if wants_json():
            return jsonify({"error": "Tool not found."}), 404
        flash("Tool not found.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    if tool["is_builtin"]:
        if wants_json():
            return jsonify({"error": "Default tools can't be deleted."}), 400
        flash("Default tools can't be deleted.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    db.execute("DELETE FROM content_tools WHERE id = ?", (tool_id,))
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    flash("Tool deleted.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.route("/tools/export", methods=["GET"])
@login_required
def tools_export():
    """Downloads a portable .json "toolkit" — either the specific tool ids
    named in ?ids=1,2,3, or every custom tool on the site (?ids=all).
    Builtin tools never export (see services.tools.export_tools) — there's
    nothing to hand someone that they don't already have."""
    db = get_db()
    raw_ids = request.args.get("ids", "")
    if raw_ids == "all":
        data = export_all_custom_tools(db)
    else:
        try:
            tool_ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]
        except ValueError:
            tool_ids = []
        data = export_tools(db, tool_ids)
    if not data["tools"]:
        flash("Nothing to export — pick at least one custom tool.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    name = "toolkit.json" if len(data["tools"]) > 1 else f"{slugify(data['tools'][0]['name'])}-tool.json"
    return Response(
        json.dumps(data, indent=2), mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


@bp.route("/tools/import", methods=["POST"])
@login_required
def tools_import():
    """Imports a .json toolkit (see tools_export) — only tools whose name
    doesn't already exist get added (services.tools.import_tools), so
    re-importing the same file, or a template package that happens to
    bundle a tool you already have, never overwrites or duplicates."""
    db = get_db()
    file = request.files.get("toolkit")
    if not file or file.filename == "":
        flash("Choose a .json toolkit file first.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    try:
        data = json.loads(file.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        flash("That file isn't a valid toolkit export.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    imported, skipped = import_tools(db, data)
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "imported": imported, "skipped": skipped})
    if imported:
        msg = f"Imported {len(imported)} tool(s): {', '.join(imported)}."
        if skipped:
            msg += f" Skipped {len(skipped)} already installed: {', '.join(skipped)}."
        flash(msg, "success")
    else:
        flash(f"Nothing new to import — all {len(skipped)} tool(s) already exist.", "error")
    return redirect(request.referrer or url_for("admin.dashboard"))



