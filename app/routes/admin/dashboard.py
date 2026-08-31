import json
from flask import request, flash, redirect, url_for, render_template, current_app

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import blog as blog_service
from ... import assistant, ai_image
from ...services import theme_generator as theme_generator_mod
from ...services import style_extract
from ...services.design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
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
    """Writing a post, everything written, and the times you publish at.

    The same three things in the same order as the Newsletters screen,
    and deliberately: an owner who has written a newsletter has learnt
    this screen. It was a tree of blogs with a pencil beside each post,
    which is a file manager -- it told you what existed and gave you
    nowhere to write.

    A post and a newsletter are the same act with a different ending, so
    they get the same shape: the tool at the top, what has been made in
    the middle, and the schedules underneath.
    """
    db = get_db()
    from ...services import blog as blogs, scheduling
    context = _screen_context(db)
    post = _tool_post(db, request.args.get("post", type=int))
    waiting = {row["target_id"]: row for row in scheduling.recent(db, limit=200)
               if row["kind"] == "publish" and not row["claimed_at"]}
    context.update(
        post=post,
        #  Every post, from every blog, in one table. They were one list
        #  per blog, which reads as several small screens and hides the
        #  only question anybody asks of this page: what have I written,
        #  and what is still a draft.
        post_rows=blogs.everything(db, waiting),
        post_scheduled=waiting.get(post["id"]) if post else None,
        post_layouts=blogs.layout_choices(),
        post_layout_html={key: blogs.starting_html(key)
                          for key, _n, _b in blogs.layout_choices()},
        schedule_choices=[
            {"name": t["name"], "says": scheduling.describe_template(t),
             "dates": [{"utc": d.strftime("%Y-%m-%d %H:%M:%S")}
                       for d in scheduling.upcoming(t, scheduling.utcnow(), 8)]}
            for t in scheduling.templates(db)],
        schedule_templates=[
            {"row": t, "says": scheduling.describe_template(t)}
            for t in scheduling.templates(db)],
        weekdays=scheduling.WEEKDAYS,
        repeats=scheduling.REPEATS,
        month_days=scheduling.MONTH_DAYS,
    )
    return render_template("admin/blogs.html", **context)


def _tool_post(db, wanted=None):
    """Which post the creation tool is holding.

    The one asked for, or the newest draft, or a fresh one. The same
    shape `_tool_newsletter` has, for the same reason: the page IS the
    tool, so it always has something in it -- and a site with no drafts
    gets exactly one blank, which is the tool being ready rather than
    litter.

    None only when there is no blog to write in, which the screen says
    rather than working around.
    """
    from ...services import blog as blogs
    every = blogs.list_blogs(db)
    if not every:
        return None
    if wanted:
        row = blogs.post_with_blog(db, wanted)
        if row:
            return row
    draft = db.execute(
        "SELECT id FROM blog_posts WHERE published_at IS NULL OR published_at = '' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    if draft:
        return blogs.post_with_blog(db, draft["id"])
    made = blogs.create_post(db, every[0]["id"], "", published_at="")
    db.commit()
    return blogs.post_with_blog(db, made)


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
    """Generate a look, and hand it back as a template to look at.

    Two steps on purpose. "Show me the plan" costs nothing and spends
    nothing: it says which sections will be made, how many pictures, and
    how many calls to the provider. Only the second press runs it. A
    generator that spends real money and minutes on a misunderstanding,
    and says so afterwards, gets used once.

    Thin, like every route here: parse the request, call one service
    function, say what happened.
    """
    db = get_db()
    if request.method == "POST":
        #  A page somebody likes the look of. STYLE only -- colours,
        #  typefaces, corners, depth. Never its words, its pictures or
        #  its markup: see services/style_extract.py, which cannot
        #  return prose at all.
        signals, ref_note = None, None
        reference = (request.form.get("reference_url") or "").strip()
        if reference:
            try:
                signals = style_extract.signals(reference)
            except style_extract.RefusedError as e:
                ref_note = str(e)
            except Exception:                                 # noqa: BLE001
                ref_note = "That page could not be read — check the address."

        kit = theme_generator_mod.brand_kit(
            brief=(request.form.get("brief") or "").strip(),
            tone=request.form.get("tone", "warm"),
            voice=request.form.get("voice", "we"),
            reading=request.form.get("reading", "normal"),
            language=request.form.get("language", "English"),
            palette=_preset_palette(request.form.get("color_preset", "")),
            fonts=request.form.get("fonts", ""),
            shape=request.form.get("shape", ""),
            shadow=request.form.get("shadow", ""),
            image_budget=request.form.get("image_budget", "1"),
            #  What was read from the reference is a STARTING value: a
            #  colour picked by hand always wins over one guessed from a
            #  URL, and every one of them is shown before anything runs.
            ref_colours=(signals or {}).get("colours"),
        )
        if signals:
            kit["shape"] = kit["shape"] or signals["shape"]
            kit["shadow"] = kit["shadow"] or signals["shadow"]
        if ref_note:
            flash(ref_note, "warning")
        name = (request.form.get("name") or "").strip()
        layout_key = request.form.get("layout", "landing")
        page_title = (request.form.get("page_title") or "Home").strip()
        mode = request.form.get("mode", "scratch")
        if mode not in dict(theme_generator_mod.MODES):
            mode = "scratch"
        wanted = theme_generator_mod.page_list(request.form.get("pages", ""))
        if not wanted:
            wanted = [page_title or "Home"]

        #  Looking is free. Everything below this line costs something.
        if request.form.get("preview"):
            try:
                shown = theme_generator_mod.plan(
                    db, kit, name, mode=mode, pages_wanted=wanted,
                    layout_key=layout_key, page_title=page_title,
                    use_ai_images=request.form.get("use_ai_images") == "1",
                    fill_scope=request.form.get("fill_scope", "all"))
            except theme_generator_mod.ThemeGenError as e:
                flash(str(e), "error")
                return redirect(url_for("admin.theme_generator"))
            return render_template("admin/theme_generator.html",
                                   plan=shown, form=request.form,
                                   signals=signals, kit=kit,
                                   **_theme_generator_context(db))

        try:
            slug = theme_generator_mod.generate(
                db, current_app.static_folder, name=name, kit=kit,
                fill_scope=request.form.get("fill_scope", "all"),
                use_ai_images=request.form.get("use_ai_images") == "1",
                mode=mode, pages_wanted=wanted,
                layout_key=layout_key, page_title=page_title)
        except theme_generator_mod.ThemeGenError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.theme_generator"))
        db.commit()
        made = db.execute("SELECT name FROM templates WHERE slug = ?", (slug,)).fetchone()
        flash("Made “%s”. Nothing on your site has changed — look at "
              "it first, and use it when you are ready."
              % (made["name"] if made else slug), "success")
        return redirect(url_for("admin.templates_screen"))

    return render_template("admin/theme_generator.html",
                           **_theme_generator_context(db))


def _preset_palette(preset):
    """A colour preset as a palette the package can carry.

    It used to be written over whatever look was active, which changed
    the live site as a side effect of generating something nobody had
    looked at yet.
    """
    if not preset or preset not in COLOR_PRESETS:
        return None
    chosen = COLOR_PRESETS[preset]
    return [{"slug": role, "name": role.title(), "color": value}
            for role, value in chosen.items() if value]


def _theme_generator_context(db):
    """Everything the screen offers, in one place so the two ways in --
    first visit and coming back with a plan -- cannot drift."""
    return dict(
        layouts=theme_generator_mod.LAYOUTS,
        modes=theme_generator_mod.MODES,
        color_presets=color_scheme_choices(db),
        tones=theme_generator_mod.TONES,
        voices=theme_generator_mod.VOICES,
        readings=theme_generator_mod.READING,
        image_budgets=theme_generator_mod.IMAGE_BUDGETS,
        font_pairings=FONT_PAIRINGS,
        shapes=SHAPE_PRESETS,
        shadows=SHADOW_PRESETS,
        ai_configured=assistant.is_configured(db),
        image_gen_configured=ai_image.is_configured(db),
        #  A provider that cannot make pictures AT ALL is not the same as
        #  one that is not configured, and needs different words.
        image_gen_reason=ai_image.unavailable_reason(db),
    )




