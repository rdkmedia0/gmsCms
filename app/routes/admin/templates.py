import os
import re
import json
import shutil
import tempfile
import datetime
from flask import request, flash, redirect, url_for, jsonify, current_app, send_file

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services.menu import refresh_site_menus
from ...services import packages
from ...services.palette import _match_palette_roles, color_scheme_choices
from . import (
    COLOR_PRESETS, FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS, SHADE_SPREADS,
    GOOGLE_FONT_CHOICES, wants_json, _redirect_next,
    NAV_LAYOUTS, _set_setting, slugify, _google_fonts_stylesheet_url,
    _apply_pack_content, SIDEBAR_LAYOUT_PRESETS, _apply_sidebar_layout,
    FOOTER_LAYOUT_PRESETS, _apply_footer_layout, _apply_default_layout, _apply_pack_identity,
    _retire_foreign_pack_pages,
    _default_layout_conflicts,
)


def pack_content_conflicts(db, pack):
    """Would loading this pack's content replace something already
    there? True if any of the pack's pages match a live page (by is_home
    for "home", by slug otherwise — same matching _apply_pack_content
    itself uses) that already has section content. Loading a template's
    content is all-or-nothing (see template_load_content below — no
    per-page picker), so this is just a single yes/no signal the
    activate/Dashboard confirm flow needs before activating/showing a
    template. Read-only, no mutation."""
    for p in pack.get("pages", []):
        if p["slug_suffix"] == "home":
            live = db.execute("SELECT id FROM pages WHERE is_home = 1").fetchone()
        else:
            live = db.execute("SELECT id FROM pages WHERE slug = ?", (p["slug_suffix"],)).fetchone()
        if live and db.execute("SELECT 1 FROM sections WHERE page_id = ? LIMIT 1", (live["id"],)).fetchone():
            return True
    return False


def dashboard_template_maps(db, static_folder, templates):
    """Two things the Dashboard and the live-page Theme & Layout panel
    both need:
    - activate_conflict_map: per template, would activating it — its own
      default layout (_default_layout_conflicts) AND, if it has any, its
      page content (pack_content_conflicts) — replace something that's
      already there. Every "Use This Look" button needs its own answer up
      front, since activating now loads both the look and the content in
      one step (see template_activate), and any button might get clicked
      next.
    - active_content: {"template_id", "name"} for the CURRENTLY ACTIVE
      template's own content, or None if it has none to (re-)load. Load
      Content — an all-or-nothing action, no per-page picker (a template
      has its base data; you load all of it or none) — is a single,
      always-in-the-same-place action on whichever template is active
      right now, for reloading its content later without reactivating it,
      not a picker listed per library entry.
    Computed fresh per render; a manifest.json read per installed
    template is cheap next to a page render."""
    activate_conflict_map = {}
    active_content = None
    for t in templates:
        pack = packages.load_template_package(static_folder, t["slug"], bool(t["is_builtin"]))
        conflict = _default_layout_conflicts(db, t["id"], pack)
        pack_pages = pack.get("pages") if pack else None
        if not conflict and pack_pages:
            conflict = pack_content_conflicts(db, pack)
        activate_conflict_map[t["id"]] = conflict
        if t["is_active"] and pack_pages:
            active_content = {"template_id": t["id"], "name": t["name"]}
    return activate_conflict_map, active_content

@bp.route("/pages/tidy", methods=["POST"])
@login_required
def pages_tidy():
    """Removes pages left behind by templates that are no longer in use.

    The same clean-up activation performs, but reachable on its own —
    because activation also REPLACES page content, and "get rid of the
    Education page a different template left" should not require
    overwriting everything else to achieve it.
    """
    db = get_db()
    active = db.execute("SELECT slug FROM templates WHERE is_active = 1").fetchone()
    if not active:
        return redirect(url_for("admin.dashboard"))
    removed = _retire_foreign_pack_pages(db, active["slug"])
    db.commit()
    if removed:
        flash("Removed " + ", ".join(removed) + ". Those pages came with templates you are no "
              "longer using.", "success")
    else:
        flash("Nothing to tidy — every page belongs to the template you are using, or to you.",
              "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/templates/<int:template_id>/colors", methods=["POST"])
@login_required
def template_colors(template_id):
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl or not tpl["palette_json"]:
        flash("This template has no color palette to customize.", "error")
        return redirect(url_for("admin.dashboard"))
    palette = json.loads(tpl["palette_json"])
    valid_slugs = {c["slug"] for c in palette}
    hex_re = re.compile(r"^#[0-9a-fA-F]{3,8}$")
    overrides = {}
    for slug in valid_slugs:
        value = request.form.get(f"color_{slug}", "").strip()
        if value and hex_re.match(value):
            overrides[slug] = value
    db.execute("UPDATE templates SET color_overrides = ? WHERE id = ?", (json.dumps(overrides), template_id))
    db.commit()
    flash("Colors updated!", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/colors/preset", methods=["POST"])
@login_required
def template_colors_preset(template_id):
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl or not tpl["palette_json"]:
        flash("This template has no color palette to customize.", "error")
        return redirect(url_for("admin.dashboard"))
    #  Built-in schemes and every template's own palette come from one
    #  place now, so "use the Bakery colours on this site" is a pick
    #  rather than a reason to activate a whole other template.
    preset = color_scheme_choices(db).get(request.form.get("preset", ""))
    if not preset:
        flash("Unknown color collection.", "error")
        return redirect(url_for("admin.dashboard"))
    palette = json.loads(tpl["palette_json"])
    roles = _match_palette_roles(palette)
    overrides = json.loads(tpl["color_overrides"]) if tpl["color_overrides"] else {}
    for role, slug in roles.items():
        if preset.get(role):
            overrides[slug] = preset[role]
    db.execute("UPDATE templates SET color_overrides = ? WHERE id = ?", (json.dumps(overrides), template_id))
    db.commit()
    flash(f'Applied the "{preset["name"]}" color collection!', "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/colors/reset", methods=["POST"])
@login_required
def template_colors_reset(template_id):
    """'Reset to theme default' means back to pristine, not just the
    template-wide role colors — a section's own bg/border color and a
    zone's own bg/border are more specific overrides layered underneath
    the same palette, so they're cleared too, same as shape's cascade
    below. Only when this is the active template: a non-active template's
    colors have no visible sections to reach anyway."""
    db = get_db()
    tpl = db.execute("SELECT is_active FROM templates WHERE id = ?", (template_id,)).fetchone()
    db.execute("UPDATE templates SET color_overrides = NULL, zone_style_overrides = NULL WHERE id = ?", (template_id,))
    if tpl and tpl["is_active"]:
        db.execute("UPDATE sections SET bg_color = NULL, border_color = NULL WHERE bg_color IS NOT NULL OR border_color IS NOT NULL")
    db.commit()
    flash("Colors reset to the theme's originals.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/fonts/preset", methods=["POST"])
@login_required
def template_fonts_preset(template_id):
    db = get_db()
    tpl = db.execute("SELECT 1 FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        return redirect(url_for("admin.dashboard"))
    preset = FONT_PAIRINGS.get(request.form.get("preset", ""))
    if not preset:
        flash("Unknown font pairing.", "error")
        return redirect(url_for("admin.dashboard"))
    overrides = {
        "heading_font_family": preset["heading"],
        "body_font_family": preset["body"],
        "google_fonts_url": preset["google_fonts_url"],
    }
    db.execute("UPDATE templates SET font_overrides = ? WHERE id = ?", (json.dumps(overrides), template_id))
    db.commit()
    flash(f'Applied the "{preset["name"]}" font pairing!', "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/fonts/reset", methods=["POST"])
@login_required
def template_fonts_reset(template_id):
    db = get_db()
    db.execute("UPDATE templates SET font_overrides = NULL WHERE id = ?", (template_id,))
    db.commit()
    flash("Fonts reset to the theme's own defaults.", "success")
    return _redirect_next("admin.dashboard")


_SYSTEM_SANS = "-apple-system, \"Segoe UI\", sans-serif"
_GOOGLE_FONT_NAMES = {name for name, _ in GOOGLE_FONT_CHOICES}
_GOOGLE_FONT_FALLBACK = dict(GOOGLE_FONT_CHOICES)


_FONT_ROLE_KEYS = {"heading": "heading_font_family", "body": "body_font_family", "footer": "footer_font_family"}


def _rebuild_google_fonts_url(overrides):
    """Collects whichever of heading/body/footer are currently actual
    Google Fonts names (a system-sans or unset role contributes nothing to
    fetch) into one combined stylesheet — always exactly what's currently
    in effect, not an accumulating stale list from earlier picks."""
    active_names = []
    for key in _FONT_ROLE_KEYS.values():
        family_css = overrides.get(key) or ""
        match = re.match(r'^"([^"]+)"', family_css)
        if match and match.group(1) in _GOOGLE_FONT_NAMES and match.group(1) not in active_names:
            active_names.append(match.group(1))
    return _google_fonts_stylesheet_url(active_names)


def _set_individual_font(template_id, role):
    """Shared body for the heading/body/footer individual-font pickers.
    Only the picked role changes. Heading/body default to system sans if
    no font_overrides exists yet (there's no other reliable way to know a
    theme's own font from Python — see GOOGLE_FONT_CHOICES' docstring);
    footer is different — it stays genuinely unset (inheriting body, its
    real default — see site-base.css) until explicitly picked, rather
    than defaulting to a value that would silently stop following body."""
    db = get_db()
    tpl = db.execute("SELECT font_overrides FROM templates WHERE id = ?", (template_id,)).fetchone()
    if tpl is None:
        return redirect(url_for("admin.dashboard"))
    name = request.form.get("font_name", "")
    if name not in _GOOGLE_FONT_NAMES:
        flash("Unknown font.", "error")
        return redirect(url_for("admin.dashboard"))
    current = json.loads(tpl["font_overrides"]) if tpl["font_overrides"] else {}
    overrides = {
        "heading_font_family": current.get("heading_font_family", _SYSTEM_SANS),
        "body_font_family": current.get("body_font_family", _SYSTEM_SANS),
    }
    if current.get("footer_font_family"):
        overrides["footer_font_family"] = current["footer_font_family"]
    overrides[_FONT_ROLE_KEYS[role]] = f"\"{name}\", {_GOOGLE_FONT_FALLBACK[name]}"
    overrides["google_fonts_url"] = _rebuild_google_fonts_url(overrides)
    db.execute("UPDATE templates SET font_overrides = ? WHERE id = ?", (json.dumps(overrides), template_id))
    db.commit()
    flash(f"{role.title()} font set to {name}.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/fonts/heading", methods=["POST"])
@login_required
def template_heading_font(template_id):
    return _set_individual_font(template_id, "heading")


@bp.route("/templates/<int:template_id>/fonts/body", methods=["POST"])
@login_required
def template_body_font(template_id):
    return _set_individual_font(template_id, "body")


@bp.route("/templates/<int:template_id>/fonts/footer", methods=["POST"])
@login_required
def template_footer_font(template_id):
    return _set_individual_font(template_id, "footer")


@bp.route("/templates/<int:template_id>/fonts/footer/reset", methods=["POST"])
@login_required
def template_footer_font_reset(template_id):
    """Drops just the footer override so it goes back to inheriting body —
    heading/body stay exactly as they are, unlike the all-or-nothing
    template_fonts_reset."""
    db = get_db()
    tpl = db.execute("SELECT font_overrides FROM templates WHERE id = ?", (template_id,)).fetchone()
    if tpl is None or not tpl["font_overrides"]:
        return _redirect_next("admin.dashboard")
    overrides = json.loads(tpl["font_overrides"])
    overrides.pop("footer_font_family", None)
    overrides["google_fonts_url"] = _rebuild_google_fonts_url(overrides)
    db.execute("UPDATE templates SET font_overrides = ? WHERE id = ?", (json.dumps(overrides), template_id))
    db.commit()
    flash("Footer font reset to match Body.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shadow/preset", methods=["POST"])
@login_required
def template_shadow_preset(template_id):
    db = get_db()
    tpl = db.execute("SELECT 1 FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        return redirect(url_for("admin.dashboard"))
    key = request.form.get("preset", "")
    if key not in SHADOW_PRESETS:
        flash("Unknown shadow style.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE templates SET shadow_override = ? WHERE id = ?", (key, template_id))
    db.commit()
    flash(f'Applied the "{SHADOW_PRESETS[key]["name"]}" depth!', "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shadow/reset", methods=["POST"])
@login_required
def template_shadow_reset(template_id):
    """Cascades into every section's own override too, same reasoning as
    template_shape_reset — "reset to theme default" means pristine, not
    the site-wide value with per-section ones still underneath it."""
    db = get_db()
    tpl = db.execute("SELECT is_active FROM templates WHERE id = ?", (template_id,)).fetchone()
    db.execute("UPDATE templates SET shadow_override = NULL WHERE id = ?", (template_id,))
    if tpl and tpl["is_active"]:
        db.execute("UPDATE sections SET shadow_style = NULL WHERE shadow_style IS NOT NULL")
    db.commit()
    flash("Depth reset to the theme's own default.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shades/preset", methods=["POST"])
@login_required
def template_shades_preset(template_id):
    """How colourful the shades derived from the palette are — see
    SHADE_SPREADS. One site-wide choice, like Corners and Depth, rather
    than a value per colour: the shades are derived, so what an admin is
    choosing is how the derivation behaves, and that is one decision."""
    db = get_db()
    if not db.execute("SELECT 1 FROM templates WHERE id = ?", (template_id,)).fetchone():
        return redirect(url_for("admin.dashboard"))
    key = request.form.get("preset", "")
    if key not in SHADE_SPREADS:
        flash("Unknown shade style.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE templates SET shade_spread = ? WHERE id = ?", (key, template_id))
    db.commit()
    flash(f'Shades set to "{SHADE_SPREADS[key]["name"]}"!', "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shades/reset", methods=["POST"])
@login_required
def template_shades_reset(template_id):
    db = get_db()
    db.execute("UPDATE templates SET shade_spread = NULL WHERE id = ?", (template_id,))
    db.commit()
    flash("Shades reset to Balanced.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shape/preset", methods=["POST"])
@login_required
def template_shape_preset(template_id):
    db = get_db()
    tpl = db.execute("SELECT 1 FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        return redirect(url_for("admin.dashboard"))
    key = request.form.get("preset", "")
    if key not in SHAPE_PRESETS:
        flash("Unknown shape style.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE templates SET shape_override = ? WHERE id = ?", (key, template_id))
    db.commit()
    flash(f'Applied the "{SHAPE_PRESETS[key]["name"]}" shape style!', "success")
    return _redirect_next("admin.dashboard")


@bp.route("/templates/<int:template_id>/shape/reset", methods=["POST"])
@login_required
def template_shape_reset(template_id):
    """Cascades into every section's own Corner Style override too, same
    reasoning as template_colors_reset — 'reset to theme default' means
    pristine, not just the site-wide shape with more specific overrides
    still sitting underneath it."""
    db = get_db()
    tpl = db.execute("SELECT is_active FROM templates WHERE id = ?", (template_id,)).fetchone()
    db.execute("UPDATE templates SET shape_override = NULL WHERE id = ?", (template_id,))
    if tpl and tpl["is_active"]:
        db.execute("UPDATE sections SET corner_style = NULL WHERE corner_style IS NOT NULL")
    db.commit()
    flash("Shape reset to the theme's own default.", "success")
    return _redirect_next("admin.dashboard")


ZONE_STYLE_ZONES = ("header", "footer", "sidebar", "sidebar_right", "body")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@bp.route("/templates/<int:template_id>/zone/<zone>/style", methods=["POST"])
@login_required
def template_zone_style(template_id, zone):
    """Header/footer/sidebar background+border, at the zone level rather
    than a template-wide 'Colors' setting — the zone's own background has
    always been the theme's own hardcoded color (or tied to --primary),
    with nothing in between that and recoloring the whole brand palette.
    Same override-on-default shape as everything else in this file, just
    keyed by zone within one JSON blob instead of its own column pair."""
    if zone not in ZONE_STYLE_ZONES:
        return jsonify({"error": "Unknown zone."}), 400
    db = get_db()
    tpl = db.execute("SELECT zone_style_overrides FROM templates WHERE id = ?", (template_id,)).fetchone()
    if tpl is None:
        return redirect(url_for("admin.dashboard"))
    overrides = json.loads(tpl["zone_style_overrides"]) if tpl["zone_style_overrides"] else {}
    zone_style = dict(overrides.get(zone) or {})
    if "bg_color" in request.form:
        bg = request.form.get("bg_color", "").strip()
        if bg and not _HEX_RE.match(bg):
            return jsonify({"error": "Invalid color."}), 400
        if bg:
            zone_style["bg"] = bg
        else:
            zone_style.pop("bg", None)
    if "border_color" in request.form:
        border = request.form.get("border_color", "").strip()
        if border and not _HEX_RE.match(border):
            return jsonify({"error": "Invalid color."}), 400
        if border:
            zone_style["border"] = border
        else:
            zone_style.pop("border", None)
    if zone_style:
        overrides[zone] = zone_style
    else:
        overrides.pop(zone, None)
    db.execute(
        "UPDATE templates SET zone_style_overrides = ? WHERE id = ?",
        (json.dumps(overrides) if overrides else None, template_id),
    )
    db.commit()
    return _redirect_next("admin.dashboard")


@bp.route("/settings/nav-layout", methods=["POST"])
@login_required
def settings_nav_layout():
    db = get_db()
    layout = request.form.get("nav_layout", "topbar")
    if layout not in NAV_LAYOUTS:
        layout = "topbar"
    _set_setting(db, "nav_layout", layout)
    # These 4 header arrangements are the "no sidebars" layouts, sitting in
    # the same unified Layout menu as the 5 sidebar presets — picking one
    # is a genuine structural choice, same as picking a sidebar preset, and
    # should equally "take over": clear any existing sidebar section(s) so
    # the page actually ends up sectionless-sided, instead of the header
    # changing while old sidebar content silently keeps rendering. Opt-in
    # (clear_sidebars=1) since it's destructive — the JS only sends it once
    # the admin has confirmed there's something there to clear.
    cleared = 0
    if request.form.get("clear_sidebars") == "1":
        active = db.execute("SELECT id FROM templates WHERE is_active = 1").fetchone()
        if active:
            cur = db.execute(
                "DELETE FROM sections WHERE template_id = ? AND zone IN ('sidebar', 'sidebar_right')",
                (active["id"],),
            )
            cleared = cur.rowcount
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "cleared": cleared})
    flash(f'Menu structure set to "{NAV_LAYOUTS[layout][0]}".', "success")
    return _redirect_next("admin.dashboard")



# ---------- Templates ----------

def _surviving_page(db, path):
    """Where to send an admin after a template change.

    The page they were on if it is still there, and the home page if it is
    not. Same-site paths only, and the home page is always a safe answer
    because a site cannot exist without one.
    """
    home = url_for("public.home")
    if not path or not path.startswith("/") or path.startswith("//"):
        return home
    slug = path.strip("/").split("/")[0]
    if not slug:
        return home
    page = db.execute("SELECT 1 FROM pages WHERE slug = ?", (slug,)).fetchone()
    return path if page else home


@bp.route("/templates/<int:template_id>/activate", methods=["POST"])
@login_required
def template_activate(template_id):
    """Makes this template the active one and applies everything it ships:
    its own default layout (nav_layout/page_layout/footer_layout — see
    _apply_default_layout) and, if it has any, its page content (see
    _apply_pack_content) — activating a look loads what comes with it,
    the same one-step action as picking a look has always been. The
    standalone load-content route below still exists for reloading a
    template's content later without reactivating it (e.g. resetting a
    page back to the template's own copy after editing it).

    `force=1` (sent only after the admin has confirmed — see
    template-panel.js) lets either the default layout replace a
    sidebar/footer zone that already has sections, or the content replace
    a page that already has some; without it, whichever part(s) would be
    destructive are skipped and the admin is told to apply them
    explicitly (Theme & Layout panel for layout, Load Content for
    content) once confirmed."""
    db = get_db()
    tpl = db.execute("SELECT slug, is_builtin FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE templates SET is_active = 0")
    db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (template_id,))
    force = request.form.get("force") == "1"
    pack = packages.load_template_package(current_app.static_folder, tpl["slug"], bool(tpl["is_builtin"]))
    #  The look, the content, and the name that belongs with them — but
    #  only when the name on the site is still somebody else's demo. See
    #  _apply_pack_identity.
    if pack:
        _apply_pack_identity(db, pack)
    needs_confirm = False
    if pack and pack.get("pages"):
        content_conflict = pack_content_conflicts(db, pack)
        if force or not content_conflict:
            _apply_pack_content(db, pack)
            #  And take away what the last template left. Same
            #  all-or-nothing confirmation as replacing the content: this
            #  only runs once the admin has agreed to that.
            retired = _retire_foreign_pack_pages(db, tpl["slug"])
            if retired:
                flash("Removed " + ", ".join(retired) +
                      " — those pages belonged to the template you were using before.", "success")
        elif content_conflict:
            needs_confirm = True
    #  After the content, not before it. A template's header menu is built
    #  from the pages the site actually has, and until the template's own
    #  pages have been written the only page there is is the home page —
    #  which is how a four-page bakery came to be activated with a header
    #  menu that said "Home" and nothing else.
    needs_confirm = _apply_default_layout(db, template_id, pack, force=force) or needs_confirm
    #  After the retiring, not before it. Pages have just appeared and
    #  others have just gone, and a menu still names the ones that went —
    #  which is how a shop came to have a Classes link.
    refresh_site_menus(db)
    db.commit()
    if needs_confirm and not force:
        if wants_json():
            return jsonify({"ok": True, "needs_confirm": True,
                            "go": _surviving_page(db, request.form.get("from"))})
        flash('Template activated, but its default layout and/or content would replace what\'s already there, so that part was skipped — apply the layout from the Theme & Layout panel, or its content from the Load Content picker below, to confirm and finish.', "warning")
        return redirect(url_for("admin.dashboard"))
    if wants_json():
        #  Activating can retire the very page the admin was standing on,
        #  and reloading that address lands on "page not found" — which
        #  reads as the template having broken the site rather than as
        #  the page simply being gone. Only the server knows what
        #  survived, so it says where to go.
        return jsonify({"ok": True, "go": _surviving_page(db, request.form.get("from"))})
    flash("Template activated! Your site now uses this look.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/templates/<int:template_id>/delete", methods=["POST"])
@login_required
def template_delete(template_id):
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        if wants_json():
            return jsonify({"error": "Template not found."}), 404
        return redirect(url_for("admin.dashboard"))
    if tpl["is_active"]:
        if wants_json():
            return jsonify({"error": "Can't delete the active template. Activate another one first."}), 400
        flash("Can't delete the active template. Activate another one first.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    db.commit()
    # A builtin's own package is the .zip built into the image and is
    # never touched — deleting it here only removes the unpacked copy
    # install_theme_package made at static/themes/<slug>/, which the next
    # start puts back (the seed loop reinstalls every shipped template,
    # and this one no longer has a `templates` row, so its "already
    # installed" stamp does not spare it). A non-builtin's
    # static/themes/<slug>/ IS its only copy (an import or "Save current
    # site as a new template" both write there — see
    # packages.save_current_site_as_package) — deleting it here is
    # permanent for those, same as removing the `templates` row is.
    pkg_dir = os.path.join(current_app.static_folder, "themes", tpl["slug"])
    if os.path.isdir(pkg_dir):
        shutil.rmtree(pkg_dir, ignore_errors=True)
    if wants_json():
        return jsonify({"ok": True})
    flash("Template deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/templates/<int:template_id>/export")
@login_required
def template_export(template_id):
    """Downloads this template (CSS + palette, no page content — see
    CLAUDE.md's Template Packages section) as a .zip, importable on any
    other install via 'Import Template Package' below."""
    db = get_db()
    try:
        zip_path = packages.export_package_zip(db, template_id, current_app.static_folder)
    except packages.PackageError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.dashboard"))
    tpl = db.execute("SELECT slug FROM templates WHERE id = ?", (template_id,)).fetchone()
    return send_file(zip_path, as_attachment=True, download_name=f"{tpl['slug']}.zip")


@bp.route("/packages/import", methods=["POST"])
@login_required
def package_import():
    """Uploads a .zip built by 'Export' (here or on another install) and
    installs it as a new template — its theme immediately, and its page
    content (if the package has any) merged into the site's own matching
    pages, exactly as Load Content does for a built-in. See
    packages.safe_extract_zip for why this is careful about what an
    uploaded archive is allowed to contain."""
    db = get_db()
    file = request.files.get("package")
    if not file or not file.filename:
        flash("Choose a .zip file to import.", "error")
        return redirect(url_for("admin.dashboard"))

    work_dir = tempfile.mkdtemp(prefix="pkgimport-")
    try:
        try:
            packages.safe_extract_zip(file, work_dir)
        except packages.PackageError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.dashboard"))

        manifest_path = os.path.join(work_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            flash("That archive doesn't look like a Template Package (no manifest.json).", "error")
            return redirect(url_for("admin.dashboard"))

        pack = packages.load_package_dir(work_dir)
        slug = slugify(pack.get("slug") or pack["name"])

        #  The same template must not quietly land twice. Importing one
        #  that is already installed used to add "bakery-2" beside
        #  "bakery" without a word, so re-importing a template you had
        #  edited and exported left you with two entries, alike enough
        #  that the only way to tell them apart was to activate one and
        #  look. Now it is a question with two honest answers: replace the
        #  one that is there, or keep both — and keeping both is what
        #  makes the numbered name, so it is a choice rather than an
        #  accident.
        #
        #  A built-in cannot be replaced, and saying so is better than
        #  appearing to: its package ships inside the image and the seed
        #  loop reinstalls it on every boot, so an overwrite would look
        #  right until the next restart put the original back.
        existing = db.execute("SELECT id, name, is_builtin FROM templates WHERE slug = ?", (slug,)).fetchone()
        choice = (request.form.get("on_conflict") or "").strip()
        if existing and choice != "replace":
            if choice != "keep-both":
                payload = {"needs_choice": True, "slug": slug,
                           "name": existing["name"], "incoming": pack.get("name") or slug,
                           "can_replace": not existing["is_builtin"]}
                if wants_json():
                    return jsonify(payload), 409
                flash(f'"{existing["name"]}" is already installed. Import it again and choose '
                      "whether to replace it or keep both.", "warning")
                return redirect(url_for("admin.dashboard"))
            base_slug, i = slug, 2
            while db.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
                slug = f"{base_slug}-{i}"
                i += 1
        elif existing and existing["is_builtin"]:
            #  Asked to replace something that cannot be replaced.
            base_slug, i = slug, 2
            while db.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
                slug = f"{base_slug}-{i}"
                i += 1
            flash(f'"{existing["name"]}" is built in and comes back on every restart, so it '
                  f'cannot be replaced — imported as "{slug}" instead.', "warning")
        pack["slug"] = slug

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in pack.items() if k not in ("pages", "blog_posts")}, f)
        #  Every package becomes a template row and keeps its whole
        #  package folder, CSS or no CSS — see CLAUDE.md's "Template
        #  Packages". It used to install only when the upload happened to
        #  carry a theme.css, so a content package arrived, was applied
        #  once, and left nothing behind to activate again.
        packages.install_theme_package(
            db, slug, current_app.static_folder, pkg_dir_override=work_dir, is_builtin=False,
        )

        page_count = 0
        if pack.get("pages"):
            #  Point the content at the pictures in the package that was
            #  just installed. The same path a builtin uses, and the same
            #  path this template will resolve to every later time it is
            #  activated — where copying them into uploads under a fresh
            #  name meant re-activating produced another copy of every
            #  picture and pages that no longer matched the package.
            pack = packages.point_media_at_installed_copy(pack, slug)
            touched = _apply_pack_content(db, pack)
            page_count = len(touched)
        db.commit()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if page_count:
        flash(f'Imported "{pack["name"]}" — theme installed and content applied to {page_count} page(s).', "success")
    else:
        flash(f'Imported "{pack["name"]}" as a new theme.', "success")
    return redirect(url_for("admin.dashboard"))



@bp.route("/templates/<int:template_id>/apply-sidebar-layout", methods=["POST"])
@login_required
def template_apply_sidebar_layout(template_id):
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    preset_key = request.form.get("preset", "")
    preset = SIDEBAR_LAYOUT_PRESETS.get(preset_key)
    if not tpl or not preset:
        if wants_json():
            return jsonify({"error": "Unknown layout preset."}), 400
        flash("Unknown layout preset.", "error")
        return redirect(url_for("admin.dashboard"))
    force = request.form.get("force") == "1"
    applied, skipped = _apply_sidebar_layout(db, template_id, preset_key, force=force)
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "applied": applied, "skipped": skipped})
    if applied:
        zone_names = " and ".join(z.replace("sidebar_right", "right sidebar").replace("sidebar", "left sidebar") for z in applied)
        msg = f'Applied "{preset["name"]}" — added a Menu to the {zone_names}.'
        if skipped:
            msg += " (Some sides already had a section, so those were left as-is.)"
        flash(msg, "success")
    else:
        flash("Both sides already have a section — clear one first if you want to apply a different starting layout.", "error")
    return redirect(url_for("admin.dashboard"))



@bp.route("/templates/<int:template_id>/apply-footer-layout", methods=["POST"])
@login_required
def template_apply_footer_layout(template_id):
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    preset_key = request.form.get("preset", "")
    preset = FOOTER_LAYOUT_PRESETS.get(preset_key)
    if not tpl or not preset:
        if wants_json():
            return jsonify({"error": "Unknown footer layout preset."}), 400
        flash("Unknown footer layout preset.", "error")
        return redirect(url_for("admin.dashboard"))
    force = request.form.get("force") == "1"
    existing = db.execute(
        "SELECT 1 FROM sections WHERE template_id = ? AND zone = 'footer' LIMIT 1", (template_id,)
    ).fetchone()
    if existing and not force:
        if wants_json():
            return jsonify({"ok": False, "skipped": True})
        flash('The footer already has section(s) — clear it first, or confirm to replace it, if you want to apply a different starting layout.', "error")
        return redirect(url_for("admin.dashboard"))
    _apply_footer_layout(db, template_id, preset_key)
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    flash(f'Applied "{preset["name"]}" to the footer.', "success")
    return redirect(url_for("admin.dashboard"))



@bp.route("/templates/<int:template_id>/load-content", methods=["POST"])
@login_required
def template_load_content(template_id):
    """Merges ALL of this template's own package content into the site's
    pages — all-or-nothing, no per-page picker (a template has its base
    data; you load all of it or none). A separate, always-available
    action from Activate (which already loads it once on first
    activation — see template_activate): mainly for reloading a
    template's content again later, e.g. resetting a page back to the
    template's own copy after editing it.

    Every built-in content pack now ships its own theme.css + palette +
    google_fonts_url directly (see app/data/templates/*/manifest.json) —
    there is no separate companion look to switch to. Earlier revisions of
    this app paired a content pack with a same-slug-free "theme_name"
    package that had to be activated in its place; that indirection is
    gone (see db.py's _migrate() retired_slugs cleanup for the DB side)."""
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        return redirect(url_for("admin.dashboard"))
    pack = packages.load_template_package(current_app.static_folder, tpl["slug"], bool(tpl["is_builtin"]))
    if not pack or not pack.get("pages"):
        flash("This template has no content to load.", "error")
        return redirect(url_for("admin.dashboard"))
    touched = _apply_pack_content(db, pack)
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "count": len(touched)})
    flash(f'Loaded "{pack["name"]}" content onto {len(touched)} page(s).', "success")
    return redirect(url_for("admin.dashboard"))



@bp.route("/templates/save-current", methods=["POST"])
@login_required
def template_save_current():
    """Captures the active template's look (CSS/palette), header/sidebar/
    footer sections, and site-wide layout, plus every live page's content
    as a brand new, independent template — saved straight into the local
    library, the same place an imported .zip lands, so it's immediately
    activatable/exportable/loadable like any other entry. This is also
    the app's "save a point to get back to" mechanism (replacing a
    separate Snapshots feature that did the same job with a second data
    model): the destructive-confirm flow in template-panel.js calls this
    route with no `name` before a risky layout/content change, which
    auto-names the save `"<active template> - <timestamp>"` rather than
    interrupting the admin for a name they can pick later — see
    template_delete/template_export for renaming/exporting it afterward.
    Exporting to a .zip stays a separate, always-available action."""
    db = get_db()
    active = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    #  Overwrite updates the template the site is already on, which is
    #  what "save my work" means once the first edit has given the site a
    #  template of its own (see fork_active_builtin). Refused for a
    #  builtin: its package ships in the image and is reinstalled on every
    #  boot, so an overwrite would last until the next restart.
    overwrite = request.form.get("overwrite") == "1" and active and not active["is_builtin"]
    name = (request.form.get("name") or "").strip()
    if overwrite:
        name = name or active["name"]
        slug = active["slug"]
    else:
        if not name:
            base_name = active["name"] if active else "Site"
            name = f"{base_name} - {datetime.datetime.now():%Y-%m-%d %H:%M}"
        slug = slugify(name)
        base_slug, i = slug, 2
        while db.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{i}"
            i += 1
    page_ids = [p["id"] for p in db.execute("SELECT id FROM pages").fetchall()]
    try:
        new_id = packages.save_current_site_as_package(
            db, current_app.static_folder, slug, name, page_ids=page_ids,
        )
    except packages.PackageError as e:
        if wants_json():
            return jsonify({"error": str(e)}), 400
        flash(str(e), "error")
        return redirect(url_for("admin.dashboard"))
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "id": new_id, "name": name})
    flash(f'Updated "{name}" with the site as it is now.' if overwrite
          else f'Saved the current site as a new template: "{name}".', "success")
    return redirect(url_for("admin.dashboard"))


