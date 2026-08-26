"""The setup wizard's routes: thin, and writing through what exists.

Every step here saves the way the ordinary screen for that thing saves --
the same settings keys, the same service call -- so nothing in the app
has two ways of being configured. What the wizard adds is the ORDER, the
plain wording, and the fact that somebody is asked at all.
"""
import json

from flask import request, flash, redirect, url_for, render_template

from . import bp, get_site_settings, get_email_settings, COLOR_PRESETS
from . import FONT_PAIRINGS, NAV_LAYOUTS
from ..auth import login_required
from ...db import get_db
from ...services import legal, site as site_service, wizard, packages
from ...services import palette as palette_service


def _templates(db):
    return db.execute(
        "SELECT id, slug, name, is_active, is_builtin FROM templates ORDER BY is_builtin DESC, name"
    ).fetchall()


def _context(db, step):
    """What the step being shown needs. Deliberately one function: a step
    that needed something exotic would be a step doing something the app
    cannot already do."""
    settings = get_site_settings(db) or {}
    details = legal.settings_for(db)
    email = get_email_settings(db)
    active = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    return {
        "step": step,
        "title": dict(wizard.STEPS)[step],
        "state": wizard.state(db),
        "steps": wizard.STEPS,
        "fresh": wizard.is_fresh(db),
        "site": settings,
        "details": details,
        "countries": legal.COUNTRIES,
        "email": email,
        "site_address": site_service.public_base(db),
        "detected_address": site_service.detected_base(db),
        "address_is_set": site_service.is_configured(db),
        "templates": _templates(db),
        "active_template": active,
        "color_presets": COLOR_PRESETS,
        "font_pairings": FONT_PAIRINGS,
        "nav_layouts": NAV_LAYOUTS,
        "ai_ready": bool((db.execute(
            "SELECT value FROM settings WHERE key = 'openwebui_url'").fetchone() or {"value": ""})["value"]),
        "summary": wizard.summary(db),
    }


@bp.route("/setup")
@login_required
def setup():
    """Wherever the walk got to."""
    db = get_db()
    return redirect(url_for("admin.setup_step", step=wizard.state(db)["step"]))


@bp.route("/setup/<step>")
@login_required
def setup_step(step):
    db = get_db()
    if step not in wizard.STEP_KEYS:
        return redirect(url_for("admin.setup"))
    #  Remembered on ARRIVAL, so leaving in the middle of a step comes
    #  back to that step rather than to the one after it.
    wizard.remember(db, step)
    db.commit()
    return render_template("admin/wizard.html", **_context(db, step))


@bp.route("/setup/<step>", methods=["POST"])
@login_required
def setup_save(step):
    """Saves one step and moves on.

    Every branch below writes exactly what the ordinary screen for that
    thing writes. Skipping is a first-class answer: the button says so,
    and nothing here is required.
    """
    db = get_db()
    if step not in wizard.STEP_KEYS:
        return redirect(url_for("admin.setup"))
    if request.form.get("skip"):
        return redirect(url_for("admin.setup_step", step=wizard.next_step(step)))

    if step == "name":
        title = (request.form.get("site_title") or "").strip()
        if not title:
            flash("Give the site a name — it is the one thing everything else uses.", "error")
            return redirect(url_for("admin.setup_step", step=step))
        for key, value in (("site_title", title),
                           ("site_tagline", (request.form.get("site_tagline") or "").strip())):
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        #  The answer to the question _apply_pack_identity was guessing
        #  at. From here a template can never rename this site.
        wizard.record_identity(db)

    elif step == "look":
        _apply_look(db)

    elif step == "details":
        legal.save_settings(db, request.form)

    elif step == "address":
        given = (request.form.get("site_base") or "").strip()
        if given:
            saved, problem = site_service.set_base(db, given)
            if problem:
                flash(problem, "error")
                return redirect(url_for("admin.setup_step", step=step))

    elif step == "email":
        from . import EMAIL_SETTINGS_KEYS
        for key in EMAIL_SETTINGS_KEYS:
            if key == "smtp_use_tls":
                value = "1" if request.form.get("smtp_use_tls") else "0"
            elif key not in request.form:
                continue
            else:
                value = request.form.get(key, "").strip()
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    db.commit()
    return redirect(url_for("admin.setup_step", step=wizard.next_step(step)))


def _apply_look(db):
    """The look step: a template, and optionally a palette and fonts.

    Activation goes through the ordinary route's own helpers rather than
    a copy of them -- including the choice the template panel already
    offers, take everything or just the look, which is the same `force`
    the confirm dialog sends.
    """
    from . import _apply_pack_content, _apply_default_layout
    from .templates import refresh_site_menus
    from ...routes.admin.templates import _retire_foreign_pack_pages
    from flask import current_app

    chosen = request.form.get("template", type=int)
    row = db.execute("SELECT * FROM templates WHERE id = ?", (chosen,)).fetchone() if chosen else None
    if row is not None:
        pack = packages.load_template_package(current_app.static_folder, row["slug"],
                                              bool(row["is_builtin"]))
        if not row["is_active"]:
            db.execute("UPDATE templates SET is_active = 0")
            db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (row["id"],))
            #  Deliberately NOT _apply_pack_identity: the owner has just
            #  told this site its own name, and a template brings a look
            #  and some pages, never an identity.
            if pack:
                _apply_default_layout(db, row["id"], pack, force=True)
        #  Content is applied because it was ASKED for, not because the
        #  template happened to be changing. Choosing the look you already
        #  have and asking for its pages used to do nothing at all and say
        #  nothing about it -- which is how a coach's site kept a
        #  landscaping blog through two runs of the walk-through.
        if pack and pack.get("pages") and request.form.get("content") == "everything":
            _apply_pack_content(db, pack)
            _retire_foreign_pack_pages(db, row["slug"])
        refresh_site_menus(db)

    active = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    if active is None:
        return

    preset = (request.form.get("colors") or "").strip()
    if preset and preset != "keep":
        chosen_preset = COLOR_PRESETS.get(preset)
        if chosen_preset:
            #  Written the way the Colors panel writes it: an override on
            #  top of the template's own palette, never a rewrite of it.
            roles = palette_service._match_palette_roles(
                json.loads(active["palette_json"] or "[]"))
            overrides = {}
            for role, colour in (("primary", chosen_preset["primary"]),
                                 ("secondary", chosen_preset["secondary"]),
                                 ("accent", chosen_preset["accent"])):
                slug = roles.get(role)
                if slug:
                    overrides[slug] = colour
            if overrides:
                db.execute("UPDATE templates SET color_overrides = ? WHERE id = ?",
                           (json.dumps(overrides), active["id"]))

    fonts = (request.form.get("fonts") or "").strip()
    if fonts and fonts != "keep" and fonts in FONT_PAIRINGS:
        db.execute("UPDATE templates SET font_overrides = ? WHERE id = ?",
                   (json.dumps({"preset": fonts}), active["id"]))


@bp.route("/setup/finish", methods=["POST"])
@login_required
def setup_finish():
    db = get_db()
    wizard.finish(db)
    db.commit()
    flash("Your site is set up. Everything you chose can be changed again from these screens.",
          "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/setup/restart", methods=["POST"])
@login_required
def setup_restart():
    """Always available: somebody changing template a year later wants the
    same walk-through, and nothing they have set is touched by restarting
    it."""
    db = get_db()
    wizard.restart(db)
    db.commit()
    return redirect(url_for("admin.setup"))
