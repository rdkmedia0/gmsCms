import json
import re
from flask import request, flash, redirect, url_for, render_template, current_app

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import blog as blog_service
from ... import assistant, ai_image
from ...services import theme_generator as theme_generator_mod
from ...services import look_from_picture
from ...services.design import COMPOSITION_PRESETS, FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
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
    activate_conflict_map, active_content, template_covers = dashboard_template_maps(
        db, current_app.static_folder, templates)

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
        template_covers=template_covers,
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


@bp.route("/activity")
@login_required
def activity():
    """Everything this site has told the owner, newest first.

    The other half of collapsing the message stack to one line. A
    confirmation used to exist for exactly one page load -- "Removed
    Notes, Writing, The library" appeared above whatever you opened next
    and was gone on the click after that, which is no use at all when
    you want to know WHICH pages it removed twenty minutes later.

    Read-only, and deliberately without a filter or a search box: five
    hundred lines is the whole of it (see the trim in admin_notes), and
    a control nobody needs is a control in the way.
    """
    db = get_db()
    notes = db.execute(
        "SELECT said_at, category, message FROM admin_notes "
        "ORDER BY id DESC LIMIT 500").fetchall()
    return render_template("admin/activity.html", notes=notes)


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
        #  Anything the owner pasted, plus anything they opened. A
        #  file that cannot be read stops here with a sentence about
        #  that file: proceeding on the paste alone would make the
        #  site quietly miss half its content.
        content_given, content_problem = _content_given(request)
        if content_problem:
            flash(content_problem, "error")
            return redirect(url_for("admin.theme_generator"))
        #  Pictures somebody likes the look of. STYLE only, and nothing
        #  is fetched from anywhere.
        #
        #  There WAS a "paste a link" field here that fetched the page
        #  and read its CSS. It went for two reasons an install's owner
        #  cares about more than we do: a small site's server reaching
        #  out to third-party pages, repeatedly, from one address, is
        #  what a scraper looks like -- and being taken for one costs
        #  THEM their reachability. And it was refused by exactly the
        #  sites people most want to point at, because a bot check
        #  answers with a challenge page, and a challenge page has
        #  colours, so the reader "succeeded" and returned the wrong
        #  ones.
        #
        #  A screenshot has none of those problems. Its colours are
        #  worked out in the browser and arrive as hex values; the
        #  picture itself is sent only when the model can look at it,
        #  and only to name the things pixels cannot: the typeface feel,
        #  the corners, the depth.
        seen_colours = [c for c in request.form.getlist("ref_colour")
                        if re.match(r"^#[0-9a-fA-F]{6}$", c or "")]
        signals = _read_pictures(db, request)

        kit = theme_generator_mod.brand_kit(
            brief=(request.form.get("brief") or "").strip(),
            #  What the owner already has written. In "place" mode it is
            #  the source of every fact on the finished site.
            source_text=content_given,
            tone=request.form.get("tone", "warm"),
            voice=request.form.get("voice", "we"),
            reading=request.form.get("reading", "normal"),
            #  A list and a box: the box wins only when the list was
            #  told to stand aside, so the two cannot disagree.
            language=theme_generator_mod.language_from(
                request.form.get("language", ""),
                request.form.get("language_other", "")),
            colour_note=(request.form.get("colour_note") or "").strip(),
            banner_per_page=request.form.get("banner_per_page") == "1",
            palette=_chosen_palette(request.form),
            fonts=request.form.get("fonts", ""),
            shape=request.form.get("shape", ""),
            shadow=request.form.get("shadow", ""),
            image_budget=request.form.get("image_budget", "1"),
            ref_colours=seen_colours or None,
            ref_ink=(request.form.get("ref_ink") or "").strip(),
            ref_feel=(signals or {}).get("feel"),
        )
        if signals:
            #  Starting values, every one of them: what somebody chose by
            #  hand always beats what was read from a picture.
            kit["shape"] = kit["shape"] or signals.get("shape") or ""
            kit["shadow"] = kit["shadow"] or signals.get("shadow") or ""
            kit["fonts"] = kit["fonts"] or signals.get("fonts") or ""

        name = (request.form.get("name") or "").strip()
        mode = request.form.get("mode", "scratch")
        if mode not in dict(theme_generator_mod.MODES):
            mode = "scratch"
        #  AS GIVEN, which may be empty. An empty list is the signal
        #  that nobody named the pages and the content should decide --
        #  and filling it in here told the generator the owner had asked
        #  for exactly one page called Home, so the proposal and the
        #  document's own headings were never reached. That default has
        #  now been found in three places on one path; the service puts
        #  it back after the deciding, which is where it belongs.
        wanted = theme_generator_mod.page_list(request.form.get("pages", ""))

        #  The look, decided once. Carried across the two presses in the
        #  form, so the run cannot come out different from the plan --
        #  and so it is not paid for twice.
        looked = _carried_look(request.form)
        #  What showing the plan has already cost. It used to cost
        #  nothing, and the screen still said so long after that stopped
        #  being true: the look is decided HERE now, deliberately, so
        #  that what the plan shows is what gets made. Reading the
        #  picture is the other request. Neither writes a word or makes
        #  a picture, and neither touches the site -- which is the part
        #  worth promising, and the part that is still true.
        spent = 1 if signals else 0
        if looked is None and mode == "scratch":
            looked = theme_generator_mod.design(db, kit, wanted)
            spent += 1
        kit = theme_generator_mod.with_design(kit, looked or {})

        if request.form.get("preview"):
            try:
                shown = theme_generator_mod.plan(
                    db, kit, name, mode=mode, pages_wanted=wanted or ["Home"],
                    looked=looked,
                    use_ai_images=request.form.get("use_ai_images") == "1",
                    fill_scope=theme_generator_mod.fill_scope_for(mode))
            except theme_generator_mod.ThemeGenError as e:
                flash(str(e), "error")
                return redirect(url_for("admin.theme_generator"))
            return render_template("admin/theme_generator.html",
                                   plan=shown, form=request.form,
                                   carried_content=content_given,
                                   signals=signals, kit=kit, looked=looked,
                                   spent=spent, **_theme_generator_context(db))

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
        #  A run that half-worked says which half.
        if kit.get("unwritten"):
            flash("%d page%s came back without words and kept their starting text — "
                  "open the template and write those, or make it again."
                  % (len(kit["unwritten"]),
                     "" if len(kit["unwritten"]) == 1 else "s"), "warning")
        made = db.execute("SELECT name FROM templates WHERE slug = ?", (slug,)).fetchone()
        flash("Made \u201c%s\u201d. Nothing on your site has changed \u2014 look at "
              "it first, and use it when you are ready."
              % (made["name"] if made else slug), "success")
        #  Back to the screen they were standing on, not off to the
        #  template list. Finishing a job is not a request to be taken
        #  somewhere else: somebody who has just made one look very
        #  often wants to try a second, and the form they filled in is
        #  here. Where the new template can be found is said in words,
        #  with a link -- an offer rather than a move.
        return redirect(url_for("admin.theme_generator", made=slug))

    #  What was just made, if anything, so the screen can show it rather
    #  than announce it. Read back by slug from the redirect, because a
    #  run ends in a redirect (a refresh must not make a second one).
    made = None
    if request.args.get("made"):
        made = db.execute("SELECT id, name, slug FROM templates WHERE slug = ?",
                          (request.args["made"],)).fetchone()
    return render_template("admin/theme_generator.html", made=made,
                           **_theme_generator_context(db))


def _content_given(request):
    """What the owner pasted, plus what they opened, in that order.

    BOTH, not one or the other. A file that silently replaced a paste
    would throw away what somebody typed, and a paste that silently
    ignored a file would leave them wondering why the upload did
    nothing. Nobody normally does both, and joining loses neither.

    A file that cannot be read stops the run with a sentence about that
    file -- rather than proceeding on the paste alone, which would make
    the site quietly miss half its content.
    """
    from ...services import documents

    pasted = (request.form.get("source_text") or "").strip()
    #  What a previous press already read out of a file. A file input
    #  cannot be re-filled by the server, so without this the content
    #  disappeared between "show me the plan" and "make it".
    carried = (request.form.get("source_carried") or "").strip()
    if carried and carried not in pasted:
        pasted = (pasted + chr(10) + chr(10) + carried).strip() if pasted else carried
    upload = request.files.get("source_file")
    if not upload or not (upload.filename or "").strip():
        return pasted, ""
    try:
        from_file = documents.text_from(upload.filename, upload.read())
    except documents.DocumentError as e:
        #  RETURNED, not raised. The kit is built before the route's own
        #  try/except, so raising here would leave a 500 where a
        #  sentence about the file belongs -- and the sentence is the
        #  whole value of refusing at all.
        return "", str(e)
    joined = (pasted + chr(10) + chr(10) + from_file).strip() if pasted else from_file
    return joined, ""


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
        #  Carried like everything else in the look. It was not, and the
        #  consequence was silent and total: the model chose a
        #  composition, the plan was built with it, and pressing Make it
        #  dropped it -- so what got made was the flat default, every
        #  time, no matter what was decided.
        "composition": form.get("look_composition", ""),
        "pages": shapes,
        #  The titles too. Without these a run made after a plan lost the
        #  pages the plan had worked out from the content, and fell back
        #  to one page called Home -- with a five-section CV attached.
        "page_titles": [t for t in form.getlist("look_title") if t],
        "why": form.get("look_why", ""),
        "asked": True,
    }


def _read_pictures(db, request):
    """What the pictures say about a look, beyond their colours.

    The colours are already worked out, in the browser, and arrive as hex
    values -- arithmetic does that better than a model and needs no
    provider at all. This is the other half: the typeface feel, the
    corner style and the depth, which pixels cannot name.

    Carried across the two presses as hidden fields, because a file
    cannot be: "Show me the plan" reads the picture, and "Make it" must
    use what was shown rather than reading it again.
    """
    carried = {k: (request.form.get("ref_" + k) or "")
               for k in ("fonts", "shape", "shadow", "feel")}
    if any(carried.values()):
        return carried

    #  The FIRST picture only. Three screenshots do not average into a
    #  typeface, and asking three times costs three requests for one
    #  answer. The others still contribute their colours.
    sent = next((p for p in request.form.getlist("ref_picture") if p), "")
    seeing, why = look_from_picture.can_see(db)
    if not seeing:
        #  Said whether or not a picture was chosen: somebody who has
        #  just uploaded one is owed the reason before they wait for a
        #  reading that is not coming.
        if why and request.form.getlist("ref_colour"):
            flash(why, "warning")
        return None
    if not sent:
        return None

    from ...services.design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
    vocab = ([(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
             list(SHAPE_PRESETS), list(SHADOW_PRESETS))
    try:
        mime, data = look_from_picture.accept(sent)
    except look_from_picture.PictureError as e:
        flash(str(e), "warning")
        return None
    if not data:
        return None
    read = look_from_picture.read_with_model(db, mime, data, vocab)
    if not read:
        flash("The model could not tell me anything about that picture's style, "
              "so its colours are used and the rest is worked out from your "
              "description.", "warning")
        return None
    return read


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
    _sees_pictures = look_from_picture.can_see(db)
    return dict(
        layouts=theme_generator_mod.LAYOUTS,
        modes=theme_generator_mod.MODES,
        #  Which rows each answer needs, decided here and read by the
        #  form, so the two cannot disagree about what applies.
        mode_needs=theme_generator_mod.MODE_NEEDS,
        #  No colour-scheme list any more: it offered every installed
        #  template's palette, which is a strange thing to want -- if you
        #  wanted that template's colours you would use that template.
        languages=theme_generator_mod.LANGUAGES,
        #  What the list holds, so the screen can tell a typed language
        #  from a picked one and reopen the box on the one it typed.
        language_values=[v for v, _l in theme_generator_mod.LANGUAGES],
        tones=theme_generator_mod.TONES,
        voices=theme_generator_mod.VOICES,
        readings=theme_generator_mod.READING,
        image_budgets=theme_generator_mod.IMAGE_BUDGETS,
        font_pairings=FONT_PAIRINGS,
        compositions=COMPOSITION_PRESETS,
        shapes=SHAPE_PRESETS,
        shadows=SHADOW_PRESETS,
        ai_configured=assistant.is_configured(db),
        image_gen_configured=ai_image.is_configured(db),
        #  A provider that cannot make pictures AT ALL is not the same as
        #  one that is not configured, and needs different words.
        image_gen_reason=ai_image.unavailable_reason(db),
        #  Whether a picture can be read for more than its colours, said
        #  before somebody meets it rather than after. Asked ONCE: it is
        #  a request to the provider, and it was written as two.
        picture_vision=_sees_pictures[0],
        picture_vision_note=_sees_pictures[1],
    )




