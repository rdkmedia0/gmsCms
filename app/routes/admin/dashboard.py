import json
from flask import request, flash, redirect, url_for, render_template, current_app

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import blog as blog_service
from ... import assistant, ai_image, theme_generator as theme_generator_mod
from ...services.palette import _match_palette_roles, color_scheme_choices
from ...services.sections import _insert_layout_chunks
from ...services import site
from . import (
    COLOR_PRESETS, NAV_LAYOUTS, get_nav_layout, SIDEBAR_LAYOUT_PRESETS, FOOTER_LAYOUT_PRESETS,
    get_site_settings, get_layout_settings,
)
from .settings import FAVICON_EMOJI_CHOICES
from .templates import dashboard_template_maps

def _screen_context(db):
    """Everything the Dashboard's old six sections needed.

    They are four screens now -- Dashboard, Blog, and Design's tabs -- and
    they share this rather than each growing its own query set. It fetches
    a little more than any one screen uses; the alternative is four
    near-copies that drift, and these are small selects on an admin page.
    """
    db = get_db()
    pages = db.execute("SELECT * FROM pages ORDER BY nav_order, title").fetchall()
    templates = db.execute("SELECT * FROM templates ORDER BY is_builtin DESC, name").fetchall()
    active_tpl = next((t for t in templates if t["is_active"]), None)
    has_sidebar_content = False
    if active_tpl:
        has_sidebar_content = bool(db.execute(
            "SELECT 1 FROM sections WHERE template_id = ? AND zone IN ('sidebar', 'sidebar_right') LIMIT 1",
            (active_tpl["id"],),
        ).fetchone())

    # Every template can optionally carry content now (see CLAUDE.md's
    # Template Packages section) — active_content is the single "Load
    # Content" action, scoped to whichever template is active right now,
    # and activate_conflict_map tells each "Use This Look" button whether
    # it needs to confirm before it's clicked (see template-panel.js) —
    # activating now loads both look and content in one step.
    activate_conflict_map, active_content = dashboard_template_maps(db, current_app.static_folder, templates)

    return dict(
        pages=pages,
        #  With how many posts in each, because the delete has to be able
        #  to say what it is about to destroy rather than "are you sure".
        #  Each blog with the posts that belong to it, because the
        #  Dashboard shows them as the tree they are. Drafts included and
        #  marked: a post you have not published is exactly the one you
        #  are most likely to be looking for.
        blogs=[dict(b,
                    posts=db.execute(
                        "SELECT COUNT(*) AS n FROM blog_posts WHERE blog_id = ?", (b["id"],)
                    ).fetchone()["n"],
                    post_list=db.execute(
                        "SELECT id, title, slug, published_at FROM blog_posts WHERE blog_id = ? "
                        "ORDER BY COALESCE(published_at, '9999') DESC, id DESC", (b["id"],)
                    ).fetchall())
               for b in blog_service.list_blogs(db)],
        templates=templates,
        color_presets=color_scheme_choices(db),
        layout_settings=get_layout_settings(db),
        site_settings=get_site_settings(db),
        #  Which template is in use, so a page's own row can say whether
        #  the one it arrived with is still it. This replaced a whole card
        #  that listed "pages from templates you are not using" and
        #  offered to remove them: the same pages are already in Your
        #  Pages with a Delete beside each, and a page is removed from the
        #  row that names it, not from a second box holding opinions about
        #  which pages count.
        active_template_slug=(db.execute(
            "SELECT slug FROM templates WHERE is_active = 1"
        ).fetchone() or {"slug": ""})["slug"],
        #  A page records the SLUG of the template it came with; a person
        #  reading the Dashboard knows it by name.
        template_names={row["slug"]: row["name"] for row in db.execute(
            "SELECT slug, name FROM templates").fetchall()},
        site_base=site.public_base(db),
        detected_base=site.normalize(request.host_url),
        site_is_public=site.is_public_host(site.public_base(db, request.host_url)),
        favicon_emoji_choices=FAVICON_EMOJI_CHOICES,
        nav_layouts=NAV_LAYOUTS,
        nav_layout=get_nav_layout(db),
        sidebar_layout_presets=SIDEBAR_LAYOUT_PRESETS,
        footer_layout_presets=FOOTER_LAYOUT_PRESETS,
        #  The Layout screen's sidebar and footer pickers are gated on
        #  this, and it was computed here and never passed -- so those two
        #  pickers had never rendered at all, on the old Dashboard or the
        #  new screen. Reported as "layout only has menu items", which is
        #  exactly what it was.
        active_tpl=active_tpl,
        has_sidebar_content=has_sidebar_content,
        active_content=active_content,
        activate_conflict_map=activate_conflict_map,
    )


@bp.route("/")
@login_required
def dashboard():
    """What is left of it: where you are, what still needs doing, and the
    way to everything else."""
    return render_template("admin/dashboard.html", **_screen_context(get_db()))


@bp.route("/blogs")
@login_required
def blogs_screen():
    """Your blogs and their posts. A list of things you write is not a
    setting, so it is not on the Settings row -- it has a button of its
    own."""
    return render_template("admin/blogs.html", **_screen_context(get_db()))


@bp.route("/design/pages")
@login_required
def pages_screen():
    return render_template("admin/design_pages.html", **_screen_context(get_db()))


@bp.route("/design/templates")
@login_required
def templates_screen():
    return render_template("admin/design_templates.html", **_screen_context(get_db()))


@bp.route("/design/layout")
@login_required
def layout_screen():
    return render_template("admin/design_layout.html", **_screen_context(get_db()))


@bp.route("/help")
@login_required
def help():
    return render_template("admin/help.html")


@bp.route("/theme-generator", methods=["GET", "POST"])
@login_required
def theme_generator():
    db = get_db()
    pages = db.execute("SELECT * FROM pages ORDER BY nav_order, title").fetchall()
    if request.method == "POST":
        page_id = request.form.get("page_id", type=int)
        layout_key = request.form.get("layout", "landing")
        fill_scope = request.form.get("fill_scope", "all")
        use_ai_images = request.form.get("use_ai_images") == "1"
        color_preset = request.form.get("color_preset", "")
        brief = (request.form.get("brief") or "").strip()

        page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        if not page:
            flash("Pick a page to generate into.", "error")
            return redirect(url_for("admin.theme_generator"))

        try:
            chunks = theme_generator_mod.generate_layout_chunks(db, layout_key, brief, fill_scope, use_ai_images)
        except theme_generator_mod.ThemeGenError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.theme_generator"))

        _insert_layout_chunks(db, page_id, chunks)
        db.commit()

        color_note = ""
        if color_preset and color_preset in COLOR_PRESETS:
            tpl = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
            if tpl and tpl["palette_json"]:
                preset = COLOR_PRESETS[color_preset]
                palette = json.loads(tpl["palette_json"])
                roles = _match_palette_roles(palette)
                overrides = json.loads(tpl["color_overrides"]) if tpl["color_overrides"] else {}
                for role, slug in roles.items():
                    if preset.get(role):
                        overrides[slug] = preset[role]
                db.execute("UPDATE templates SET color_overrides = ? WHERE id = ?", (json.dumps(overrides), tpl["id"]))
                db.commit()
            else:
                color_note = " (Your active look doesn't support color presets, so colors were left as-is — try it from the 🎨 Colors panel instead.)"

        flash("Generated! Review and edit anything below — nothing here is final." + color_note, "success")
        return redirect(url_for("admin.page_edit", page_id=page_id))

    return render_template(
        "admin/theme_generator.html",
        pages=pages,
        layouts=theme_generator_mod.LAYOUTS,
        color_presets=color_scheme_choices(db),
        ai_configured=assistant.is_configured(db),
        image_gen_configured=ai_image.is_configured(db),
    )




