import json
import re
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
    """One blog at a time: choose it, write in it, see what is in it.

    The same three things in the same order as the Newsletters screen --
    the tool, what has been made, the times things go out -- with the
    blogs themselves first, because a post belongs to one and everything
    below follows whichever is current.

    Everything happens HERE. Deleting a post used to leave you on the
    blog's own manage page, which is a different screen that cannot show
    you the delete worked; renaming a blog left you on the Dashboard.
    Three actions in a row was three screens.
    """
    db = get_db()
    from ...services import blog as blogs, scheduling
    context = _screen_context(db)
    every = blogs.list_blogs(db)

    #  The blog everything else is about. Asked for in the address so it
    #  survives an action and a redirect -- which is what makes "delete
    #  this post" able to come back to the list it was deleted from.
    current = request.args.get("blog", type=int)
    if not any(b["id"] == current for b in every):
        current = every[0]["id"] if every else None

    post = _tool_post(db, request.args.get("post", type=int), current)
    waiting = {row["target_id"]: row for row in scheduling.recent(db, limit=200)
               if row["kind"] == "publish" and not row["claimed_at"]}
    context.update(
        current_blog=current,
        current_blog_row=next((b for b in every if b["id"] == current), None),
        post=post,
        #  This blog's posts. It was every post from every blog in one
        #  table, which reads as a site-wide list and then offers actions
        #  that only make sense inside one blog.
        post_rows=[row for row in blogs.everything(db, waiting)
                   if current is None or row["row"]["blog_id"] == current],
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


@bp.route("/blogs/write", methods=["POST"])
@login_required
def blog_post_start():
    """Start a post in the current blog, and stay here.

    A deliberate act, which is the whole point. The screen used to make a
    blank draft on every visit if there were no drafts -- so deleting the
    only draft and coming back produced another one, and the delete read
    as having done nothing. It had worked; the screen had simply made a
    replacement before anybody could see.
    """
    db = get_db()
    from ...services import blog as blogs
    blog_id = request.form.get("blog", type=int)
    if not blogs.get_blog(db, blog_id):
        first = blogs.list_blogs(db)
        if not first:
            flash("Start a blog first — a post has to live in one.", "error")
            return redirect(url_for("admin.blogs_screen"))
        blog_id = first[0]["id"]
    made = blogs.create_post(db, blog_id, "", published_at="")
    db.commit()
    return redirect(url_for("admin.blogs_screen", blog=blog_id, post=made) + "#cms-post-tool")


def _tool_post(db, wanted=None, blog_id=None):
    """Which post the creation tool is holding.

    The one asked for, or the newest draft in this blog, or nothing --
    and nothing is a real answer, drawn as "start one". It used to CREATE
    a draft here when there were none, which meant the screen wrote to
    the database on a GET, and deleting your only draft and returning
    made another one.
    """
    from ...services import blog as blogs
    if wanted:
        row = blogs.post_with_blog(db, wanted)
        if row:
            return row
    if not blog_id:
        return None
    draft = db.execute(
        "SELECT id FROM blog_posts WHERE blog_id = ? "
        "AND (published_at IS NULL OR published_at = '') "
        "ORDER BY id DESC LIMIT 1", (blog_id,)).fetchone()
    return blogs.post_with_blog(db, draft["id"]) if draft else None


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
    """Describe the business; the look is worked out from that.

    It used to ask an owner to pick a "front page shape" from three named
    skeletons and colours from a list beginning "the standard colours" --
    internal vocabulary, and neither a question somebody opening this for
    the first time can answer. What they CAN describe is their business,
    so that is what it asks, and the design is derived from it.

    Two steps, still. "Show me the plan" works out the LOOK -- one
    request -- and shows the colours, the typefaces, the shapes and why,
    before a word of content is written. Only the second press writes
    anything.
    """
    db = get_db()
    if request.method == "POST":
        #  Pages and pictures somebody likes the look of. STYLE only --
        #  see services/style_extract.py, which cannot return prose at
        #  all.
        #
        #  A page is READ here, by this app, with no AI involved: the
        #  colours, the typefaces, the corners and the depth come out of
        #  its CSS. A picture is different -- there is nothing to parse,
        #  and reading a photograph needs a model that can see, which not
        #  every provider has. So a picture's colours are sampled in the
        #  BROWSER and arrive as plain hex values. That works whatever
        #  the provider can do, and the picture never leaves the machine
        #  it was chosen on.
        signals, ref_notes = None, []
        seen_colours = []
        for reference in request.form.getlist("reference_url"):
            reference = (reference or "").strip()
            if not reference:
                continue
            try:
                got = style_extract.signals(reference)
            except style_extract.RefusedError as e:
                ref_notes.append("%s \u2014 %s" % (reference, e))
                continue
            except Exception:                                 # noqa: BLE001
                ref_notes.append("%s could not be read \u2014 check the address."
                                 % reference)
                continue
            seen_colours.extend(got["colours"])
            #  The first page that answered sets the shape and the type;
            #  the rest add their colours. Merging two sites' typefaces
            #  would be choosing neither.
            signals = signals or got
        #  Colours sampled from pictures, in the browser.
        seen_colours.extend([c for c in request.form.getlist("ref_colour")
                             if re.match(r"^#[0-9a-fA-F]{6}$", c or "")])
        for note in ref_notes[:3]:
            flash(note, "warning")

        kit = theme_generator_mod.brand_kit(
            brief=(request.form.get("brief") or "").strip(),
            tone=request.form.get("tone", "warm"),
            voice=request.form.get("voice", "we"),
            reading=request.form.get("reading", "normal"),
            language=request.form.get("language", "English"),
            colour_note=(request.form.get("colour_note") or "").strip(),
            banner_per_page=request.form.get("banner_per_page") == "1",
            palette=_chosen_palette(request.form),
            fonts=request.form.get("fonts", ""),
            shape=request.form.get("shape", ""),
            shadow=request.form.get("shadow", ""),
            image_budget=request.form.get("image_budget", "1"),
            ref_colours=seen_colours or None,
        )
        if signals:
            kit["shape"] = kit["shape"] or signals["shape"]
            kit["shadow"] = kit["shadow"] or signals["shadow"]

        name = (request.form.get("name") or "").strip()
        mode = request.form.get("mode", "scratch")
        if mode not in dict(theme_generator_mod.MODES):
            mode = "scratch"
        wanted = theme_generator_mod.page_list(request.form.get("pages", "")) or ["Home"]

        #  The look, decided once. Carried across the two presses in the
        #  form, so the run cannot come out different from the plan --
        #  and so it is not paid for twice.
        looked = _carried_look(request.form)
        if looked is None and mode == "scratch":
            looked = theme_generator_mod.design(db, kit, wanted)
        kit = theme_generator_mod.with_design(kit, looked or {})

        if request.form.get("preview"):
            try:
                shown = theme_generator_mod.plan(
                    db, kit, name, mode=mode, pages_wanted=wanted, looked=looked,
                    use_ai_images=request.form.get("use_ai_images") == "1",
                    fill_scope=theme_generator_mod.fill_scope_for(mode))
            except theme_generator_mod.ThemeGenError as e:
                flash(str(e), "error")
                return redirect(url_for("admin.theme_generator"))
            return render_template("admin/theme_generator.html",
                                   plan=shown, form=request.form,
                                   signals=signals, kit=kit, looked=looked,
                                   **_theme_generator_context(db))

        try:
            slug = theme_generator_mod.generate(
                db, current_app.static_folder, name=name, kit=kit,
                fill_scope=theme_generator_mod.fill_scope_for(mode),
                use_ai_images=request.form.get("use_ai_images") == "1",
                mode=mode, pages_wanted=wanted, looked=looked)
        except theme_generator_mod.ThemeGenError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.theme_generator"))
        db.commit()
        made = db.execute("SELECT name FROM templates WHERE slug = ?", (slug,)).fetchone()
        flash("Made \u201c%s\u201d. Nothing on your site has changed \u2014 look at "
              "it first, and use it when you are ready."
              % (made["name"] if made else slug), "success")
        return redirect(url_for("admin.templates_screen"))

    return render_template("admin/theme_generator.html",
                           **_theme_generator_context(db))


def _carried_look(form):
    """The design worked out for the plan, carried to the run.

    Passed through the form as hidden fields rather than worked out
    again: asking twice costs a second request and can come back
    different, and "Make it" would then make something other than what
    was shown.
    """
    shapes = [s for s in form.getlist("look_page") if s]
    if not shapes:
        return None
    return {
        "colours": [c for c in form.getlist("look_colour") if c],
        "fonts": form.get("look_fonts", ""),
        "shape": form.get("look_shape", ""),
        "shadow": form.get("look_shadow", ""),
        "pages": shapes,
        "why": form.get("look_why", ""),
        "asked": True,
    }


def _chosen_palette(form):
    """Three colours somebody picked, or nothing.

    It was a dropdown of colour SCHEMES -- every installed template's
    palette, offered here. Which is a strange thing to want: if you
    wanted that template's colours you would use that template. What a
    person actually wants is either to describe the colours in words, or
    to set them exactly, so those are the two things offered.
    """
    if form.get("set_colours") != "1":
        return None
    picked = []
    for role in ("primary", "secondary", "accent"):
        value = (form.get("colour_" + role) or "").strip()
        if re.match(r"^#[0-9a-fA-F]{6}$", value):
            picked.append({"slug": role, "name": role.title(), "color": value.lower()})
    return picked or None


def _theme_generator_context(db):
    """Everything the screen offers, in one place so the two ways in --
    first visit and coming back with a plan -- cannot drift."""
    return dict(
        layouts=theme_generator_mod.LAYOUTS,
        modes=theme_generator_mod.MODES,
        #  Which rows each answer needs, decided here and read by the
        #  form, so the two cannot disagree about what applies.
        mode_needs=theme_generator_mod.MODE_NEEDS,
        #  No colour-scheme list any more: it offered every installed
        #  template's palette, which is a strange thing to want -- if you
        #  wanted that template's colours you would use that template.
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




