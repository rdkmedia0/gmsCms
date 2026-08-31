"""
The Newsletters screen: the list of newsletter pages, and sending one.

A newsletter is a page, so nothing here authors anything — the writing
happens in the normal editor, on the page itself. This is only the two
things a page cannot do for itself: turn into an email, and remember that
it went out.
"""
from flask import (request, flash, redirect, url_for, render_template,
                   current_app, jsonify)

from . import bp, get_email_settings, get_site_settings, wants_json
from ..auth import login_required
from ...db import get_db
from ... import mailer
from ... import assistant
import json

from . import FONT_PAIRINGS
from ...services import (blog as blog_service, commerce, email_layouts, legal,
                         newsletter, newsletter_ai, palette, scheduling, site,
                         site_emails, subscribers)


#  Two settings and nothing else. The greeting and the sign-off are the
#  owner's; the sender line and the unsubscribe link are not, and are
#  appended by the code below whatever these say -- an owner must not be
#  able to delete the legal footing by editing a template.
WRAPPER_KEYS = ("newsletter_intro", "newsletter_outro")


def _wrapper(db):
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?)", WRAPPER_KEYS
    ).fetchall()
    found = {r["key"]: r["value"] or "" for r in rows}
    return found.get("newsletter_intro", ""), found.get("newsletter_outro", "")


def _look(db):
    """The active template's own colours and fonts, as the email's look."""
    template = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    fonts = None
    if template and template["font_overrides"]:
        try:
            fonts = FONT_PAIRINGS.get(json.loads(template["font_overrides"]).get("preset", ""))
        except (ValueError, TypeError, AttributeError):
            fonts = None
    return newsletter.look_from(palette.role_ramps(template) if template else {}, fonts)


def _wrapped(db, subject, view_url, blocks=None):
    """The greeting and the sign-off, with their two placeholders filled.

    Skipped entirely for a newsletter that carries its OWN opening or
    sign-off, which every newly written one now does: those are blocks in
    the newsletter, written where they will be read, rather than two
    settings applied invisibly to everything.

    A newsletter written before that -- and a page or a post, which have
    no blocks to hold an opening -- still gets the site-wide pair. That
    is what lets this change cost nobody their words without rewriting
    anybody's drafts underneath them.
    """
    if blocks is not None and email_layouts.has_own_wrapper(blocks):
        return "", ""
    intro, outro = _wrapper(db)
    return (newsletter.wrapper_html(intro, subject, view_url or ""),
            newsletter.wrapper_html(outro, subject, view_url or ""))


def _pages(db):
    return db.execute(
        "SELECT * FROM pages WHERE page_type = 'newsletter' ORDER BY id DESC"
    ).fetchall()


def _page_sections(db, page_id):
    return db.execute(
        "SELECT id, type, title, content, updated_at, changed_seq FROM sections "
        "WHERE page_id = ? ORDER BY position", (page_id,)
    ).fetchall()


@bp.route("/newsletters")
@login_required
def newsletters():
    db = get_db()
    pages = _pages(db)
    email_settings = get_email_settings(db)
    line, has_address = newsletter.sender_line(legal.settings_for(db),
                                               (get_site_settings(db) or {}).get("site_title"))
    #  The creation tool is the top of this page now, so the page always
    #  has a newsletter in it: the one asked for, the newest draft, or a
    #  fresh one.
    current = _tool_newsletter(db, request.args.get("issue", type=int))
    return render_template(
        "admin/newsletters.html",
        **_editor_context(db, current),
        pages=pages,
        #  One row per newsletter, whatever point of its life it is at.
        #  Yours / Going out on its own / What has gone out were three
        #  views of one thing, so a newsletter moved between cards as it
        #  aged and "where is the autumn one" depended on remembering
        #  whether it had gone yet.
        rows=newsletter.overview(db, scheduling, subscribers.AUDIENCES),
        schedule_templates=[
            {"row": t, "says": scheduling.describe_template(t)}
            for t in scheduling.templates(db)],
        weekdays=scheduling.WEEKDAYS,
        repeats=scheduling.REPEATS,
        month_days=scheduling.MONTH_DAYS,
        #  The newsletters built for the job, newest first, and the
        #  layouts one can be started from.
        #  Everything on the clock, in one place: a schedule was only
        #  visible from inside whatever it belonged to, so "what is going
        #  out this week" meant opening each one.
        on_the_clock=scheduling.recent(db),
        post_scheduled={row["target_id"]: row for row in scheduling.recent(db, limit=100)
                        if row["kind"] == "post" and not row["claimed_at"]},
        composed=newsletter.list_composed(db),
        composed_sends={row["id"]: newsletter.last_send(db, "newsletter", row["id"])
                        for row in newsletter.list_composed(db)},
        layout_names={key: email_layouts.LAYOUTS[key]["name"] for key in email_layouts.LAYOUTS},
        sends={p["id"]: newsletter.last_send(db, "page", p["id"]) for p in pages},
        #  Every post, newest first, grouped by the blog it belongs to --
        #  the thing an owner actually reaches for when they think "send
        #  the newsletter". A post is already an issue: a title, a date,
        #  a permanent address, and an online copy to link to.
        blogs=[{"blog": b, "posts": blog_service.posts_for(db, b["id"], published_only=False,
                                                           limit=10)}
               for b in blog_service.list_blogs(db)],
        post_sends={post["id"]: newsletter.last_send(db, "post", post["id"])
                    for b in blog_service.list_blogs(db)
                    for post in blog_service.posts_for(db, b["id"], published_only=False, limit=10)},
        wrapper=dict(zip(WRAPPER_KEYS, _wrapper(db))),
        wrapper_sender_line=newsletter.sender_line(
            legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))[0],
        #  Each page's own send menu, so "section 3" means section 3 of
        #  THAT page rather than of some notional newsletter.
        send_choices={p["id"]: newsletter.choices_for(_page_sections(db, p["id"]))
                      for p in pages},
        #  Still passed, because "(24)" beside "Everyone on the list" at
        #  the moment of CHOOSING who gets it is useful. What was removed
        #  is the card that stated the same two numbers as a heading --
        #  the Email list screen's subject, repeated here, which is how
        #  two places come to disagree.
        history=newsletter.history(db),
        counts=subscribers.counts(db),
    )


#  ---- What the site says when it writes on its own ----


#  The endpoint is named explicitly because the FUNCTION cannot be:
#  `site_emails` is the service this module imports, and a view of that
#  name would shadow it for everything below.
def _post_resolver(db):
    """Fills a Blog-posts block with the real latest posts.

    Passed INTO email_layouts.render rather than reached for inside it:
    that module renders an email and knows nothing about blogs, which is
    what keeps it callable from a template, a checker and a scheduled
    send alike.
    """
    def link_for(blog, post):
        return site.absolute(db, url_for("public.blog_post", slug=blog["slug"],
                                         post_slug=post["slug"]))

    def resolve(blog_id, count):
        return newsletter.post_rows_for(db, blog_service, blog_id, count, link_for)
    return resolve


def _wording_values(db):
    """What each placeholder is worth ON THIS INSTALL, for the preview.

    The preview used believable INVENTED data throughout -- "Your site",
    "Your Business GmbH", a made-up address -- on the reasoning that
    showing `{{site}}` back to somebody tells them nothing about how the
    sentence reads. That half is right and stands.

    The other half was wrong, and an owner spotted it: this install knows
    its own name. Showing "Your site" where the real message will say
    "Flour & Salt" makes the preview a worse guide than the thing it is
    previewing -- and it is exactly the field somebody checks the wording
    against. So anything that can be READ is read, and sample data is
    kept only for what genuinely does not exist yet: an order that has
    not happened has no total, and there is no real access token to put
    in a link that anybody may screenshot.

    A real ORDER is used when the shop has one, because then every one of
    those values is true as well.
    """
    values = dict(site_emails.SAMPLE)
    settings = get_site_settings(db) or {}
    legal_settings = legal.settings_for(db)
    site_title = settings.get("site_title") or ""
    if site_title:
        values["site"] = site_title

    #  The real host, with a sample token. The address is the half that
    #  is knowable and the half somebody is checking; the token is not
    #  ours to show, and a live one in a screenshot is a live one.
    try:
        values["link"] = site.absolute(
            db, url_for("public.my_account", token="example-link"))
    except Exception:  # noqa: BLE001 - a preview must not 500 the screen
        pass

    #  What the sign-up form on this site actually says, since that is
    #  what a confirmation quotes back.
    consent = (db.execute(
        "SELECT consent_text FROM subscribers WHERE consent_text IS NOT NULL "
        "AND consent_text != '' ORDER BY id DESC LIMIT 1").fetchone() or {})
    if consent and consent["consent_text"]:
        values["consent"] = consent["consent_text"]

    #  A real order makes every commerce value true at once. The most
    #  recent one, because it is the one whose email the owner most
    #  likely still has open in another tab.
    order = db.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT 1").fetchone()
    if order:
        real = commerce.order_values(
            db, order, site_title or "your site",
            token_url=values["link"], legal_settings=legal_settings)
        for key, value in real.items():
            #  Only what is actually there. An order with nothing to post
            #  has no action, and an empty real value is worse than a
            #  sample one for judging how a sentence reads.
            if str(value or "").strip():
                values[key] = value
        buyer = db.execute("SELECT email FROM customers WHERE id = ?",
                           (order["customer_id"],)).fetchone() if order["customer_id"] else None
        if buyer and buyer["email"]:
            values["buyer"] = buyer["email"]
    elif legal_settings.get("business"):
        #  No order to read, but the seller's own details are known and
        #  they are half of what an invoice says.
        values["invoice"] = values["invoice"].replace(
            "Your Business GmbH", legal_settings["business"])
        if legal_settings.get("address"):
            values["invoice"] = values["invoice"].replace(
                "1 Example Street, 8001 Zurich",
                legal_settings["address"].replace(chr(10), ", "))
    return values


@bp.route("/emails", endpoint="site_emails")
@login_required
def site_emails_screen():
    """The wording of the four messages nobody presses Send on.

    The message as it will ARRIVE, not a description of it -- the same
    canvas the newsletter editor uses, because these are the same kind of
    thing and reading them should not mean learning a second screen.

    The whole body is the owner's now, so there is no greyed middle any
    more: what is greyed is only what the code adds BELOW the message,
    which is the sender line and, on a list message, the unsubscribe
    link. Both are shown rather than merely described, so nobody writes
    their own and the reader gets two.
    """
    db = get_db()
    look = _look(db)
    site_title = (get_site_settings(db) or {}).get("site_title") or "Your site"
    line, _has = newsletter.sender_line(legal.settings_for(db), site_title)
    values = _wording_values(db)
    #  Said, because a preview that mixes real and invented values is
    #  only trustworthy if it says which is which.
    note = ("This is your own site's details, and your most recent order."
            if db.execute("SELECT 1 FROM orders LIMIT 1").fetchone()
            else "Your own site's details. The order figures are an example, "
                 "because there are no orders yet.")
    return render_template(
        "admin/site_emails.html",
        messages=site_emails.MESSAGES,
        order=site_emails.ORDER,
        appended=site_emails.APPENDED,
        needs_unsubscribe=site_emails.NEEDS_UNSUBSCRIBE,
        #  What the owner has, verbatim -- the stored form, which is
        #  what a save writes back and what the server renders from.
        wording={key: site_emails.body(db, key) for key in site_emails.ORDER},
        #  ...and the same words RENDERED, which is what is written into.
        #  The canvas was the stored text in a div, so `## Thank you for
        #  your order` was shown with its markers still in it and every
        #  blank line collapsed -- the whole message arrived on screen as
        #  one run-on paragraph that looked nothing like what is sent.
        #  The thing being written into is the thing that gets sent, the
        #  same rule the newsletter canvas follows. The placeholders stay
        #  visible because they are not filled here; Preview is what
        #  fills them.
        written={key: email_layouts.rich(site_emails.body(db, key), look)
                 for key in site_emails.ORDER},
        #  ...and the same words with the placeholders filled in, which
        #  is the only way to see whether a sentence with `{{total}}` in
        #  the middle of it actually reads.
        previews={key: email_layouts.rich(
            site_emails.fill(site_emails.body(db, key), values), look)
            for key in site_emails.ORDER},
        sample_note=note,
        block_styles=email_layouts.block_styles(look),
        look=look,
        sender_line=line,
        sample=values,
        email_ready=mailer.is_configured(get_email_settings(db)),
    )


@bp.route("/emails/<message>/preview")
@login_required
def site_email_preview(message):
    """The message as it actually arrives, in its own tab.

    Not the canvas. The canvas shows the WORDS -- which is what somebody
    is writing -- and this shows the email: the same wrapper, the same
    card, the same sender line the send puts round it. A preview of
    something else is not a preview, which is the rule the newsletter
    preview already follows.
    """
    db = get_db()
    if message not in site_emails.MESSAGES:
        return redirect(url_for("admin.site_emails"))
    site_title = (get_site_settings(db) or {}).get("site_title") or "Our site"
    line, _has = newsletter.sender_line(legal.settings_for(db), site_title)
    body = site_emails.wrap(db, message, None, _wording_values(db))
    html = newsletter.to_transactional_html(body, site_title, line, _look(db))
    #  Served as a page rather than downloaded: it is a preview, and the
    #  point is to look at it.
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@bp.route("/emails/<message>", methods=["POST"])
@login_required
def site_email_save(message):
    db = get_db()
    if request.form.get("reset"):
        site_emails.reset(db, message)
        db.commit()
        flash("Put back to the standard wording.", "success")
        return redirect(url_for("admin.site_emails"))
    saved, error = site_emails.save(db, message, request.form.get("body"))
    if error:
        flash(error, "error")
    else:
        db.commit()
        flash("Saved. The next message of that kind uses these words.", "success")
    return redirect(url_for("admin.site_emails"))


#  ---- A newsletter of its own ----
#
#  A layout with named slots, rather than a page written with tools that
#  do not survive an inbox. The send path below is shared with pages and
#  posts unchanged: a layout's body is one HTML section, which is what
#  `sections` has always been.
def _composed_sections(db, row):
    body = email_layouts.render(newsletter.composed_blocks(row), _look(db),
                                posts_for=_post_resolver(db))
    return [{"type": "html", "title": "", "content": body}]


def _blocks_from_form(form):
    """What the editor posted, as blocks.

    One field, because the canvas IS the form: newsletter-editor.js reads
    the whole arrangement out of the page and writes it here as JSON.
    Posting one named input per slot is what the old fixed-slot model
    did, and it is exactly what stopped a newsletter having two pictures.
    """
    try:
        return email_layouts.normalise(json.loads(form.get("blocks_json") or "[]"))
    except (ValueError, TypeError):
        return []


@bp.route("/newsletters/issue/new", methods=["POST"])
@login_required
def newsletter_issue_new():
    db = get_db()
    layout = (request.form.get("layout") or "letter").strip()
    if layout not in email_layouts.LAYOUTS:
        layout = "letter"
    new_id = newsletter.create_composed(db, layout)
    #  A new newsletter opens with its layout's arrangement already in
    #  it, because an empty canvas does not show what a template IS --
    #  which is the whole reason for choosing one.
    newsletter.save_blocks(db, new_id, "", email_layouts.starting_blocks(
        layout, db, newsletter.blocks_of))
    db.commit()
    return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=new_id))


def _editor_context(db, row):
    """Everything the creation tool needs to draw one newsletter.

    One function because there are two ways in: the Newsletters page
    carries the tool at its top, and a link straight to an issue still
    opens it. Two copies of this list is how the two come to differ in
    which controls they offer.
    """
    line, has_address = newsletter.sender_line(
        legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))
    look = _look(db)
    blocks = newsletter.composed_blocks(row)
    return dict(
        item=row,
        #  Each schedule, what it means in words, and the next few dates
        #  it produces -- offered rather than decided. Booking its next
        #  occurrence silently was the app choosing the date, and the
        #  date is the owner's: "the first Monday" might be tomorrow, and
        #  this issue might not be ready by tomorrow.
        schedule_choices=[
            {"name": t["name"], "says": scheduling.describe_template(t),
             "dates": [{"utc": d.strftime("%Y-%m-%d %H:%M:%S")}
                       for d in scheduling.upcoming(t, scheduling.utcnow(), 8)]}
            for t in scheduling.templates(db)],
        #  The email itself, with its slots opened up. This IS the
        #  editor: what is written into is what is sent.
        canvas=email_layouts.render(blocks, look, edit=True,
                                    posts_for=_post_resolver(db)),
        blogs_for_blocks=[{"id": b["id"], "name": b["name"]}
                          for b in blog_service.list_blogs(db)],
        #  Published only, and titles only: the editor needs enough to
        #  choose with, and the words are resolved at send time so a post
        #  edited afterwards goes out as it now reads.
        blog_posts={str(b["id"]): [{"id": p["id"], "title": p["title"] or "Untitled"}
                                   for p in blog_service.posts_for(
                                       db, b["id"], published_only=True, limit=50)]
                    for b in blog_service.list_blogs(db)},
        block_styles=email_layouts.block_styles(look),
        look=look,
        layout=email_layouts.LAYOUTS.get(row["layout"]) or email_layouts.LAYOUTS["letter"],
        layout_choices=email_layouts.choices(db, newsletter.sent_composed),
        layout_starts={key: email_layouts.starting_blocks(
                           key, db, newsletter.blocks_of)
                       for key, _n, _b in email_layouts.choices(
                           db, newsletter.sent_composed)},
        blocks=blocks,
        block_types=email_layouts.BLOCK_TYPES,
        block_order=email_layouts.BLOCK_ORDER,
        image_scales=email_layouts.IMAGE_SCALES,
        email_fonts=email_layouts.EMAIL_FONTS,
        alignments=email_layouts.ALIGNMENTS,
        missing=email_layouts.missing(blocks),
        audiences=subscribers.AUDIENCES,
        audience_counts={key: subscribers.audience_count(db, key)
                         for key, _label in subscribers.AUDIENCES},
        last=newsletter.last_send(db, "newsletter", row["id"]),
        scheduled=scheduling.pending_for(db, "newsletter", row["id"]),
        email_ready=mailer.is_configured(get_email_settings(db)),
        ai_ready=assistant.is_configured(db),
        sender_line=line,
        has_address=has_address,
    )


def _tool_newsletter(db, wanted=None):
    """Which newsletter the creation tool is holding.

    The one asked for, or the newest draft, or a fresh one. The page IS
    the tool now, so it always has something in it -- and a site with no
    drafts gets exactly one blank, which is the tool being ready rather
    than litter.
    """
    if wanted:
        row = newsletter.get_composed(db, wanted)
        if row:
            return row
    for row in newsletter.list_composed(db):
        if not newsletter.last_send(db, "newsletter", row["id"]):
            return row
    made = newsletter.create_composed(db, "letter", "")
    newsletter.save_blocks(db, made, "", email_layouts.starting_blocks("letter", db),
                           layout="letter")
    db.commit()
    return newsletter.get_composed(db, made)


@bp.route("/newsletters/issue/<int:newsletter_id>/canvas", methods=["POST"])
@login_required
def newsletter_issue_canvas(newsletter_id):
    """Save what is on the canvas, and hand the canvas back.

    Restyling a block used to submit the whole form and load the whole
    page again: the scroll position and the selection were carried
    across it, so it read as an update rather than a reload, but it was
    a reload -- and on anything slower than a local container you
    watched the screen go white to change one alignment.

    The rule it was obeying stands and is the reason this exists at all:
    **the canvas is rendered by the server, never rebuilt in
    JavaScript**. Two renderers would drift, and a preview that has
    drifted is worse than none. So this returns the SAME
    `email_layouts.render()` output the page load returns -- the same
    template that renders what is sent -- and the editor swaps it in.
    One renderer, no page load.

    It saves, because the blocks it renders are the blocks it was given,
    and leaving them unsaved would mean a refresh showing something
    older than the screen.
    """
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    if not row:
        return ("", 404)
    keep = (request.form.get("blog_id") or "").strip()
    blocks = _blocks_from_form(request.form)
    newsletter.save_blocks(
        db, newsletter_id,
        (request.form.get("subject") or "").strip(), blocks,
        layout=(request.form.get("layout") or "").strip() or None,
        blog_id=int(keep) if keep.isdigit() else None)
    db.commit()
    return email_layouts.render(blocks, _look(db), edit=True,
                                posts_for=_post_resolver(db))


def _apply_schedule_choice(db, newsletter_id, row):
    """Put this newsletter on the clock, or take it off, as the form says.

    `none` is the default and means "not scheduled": it cancels anything
    waiting, which is how the same control that books a send also takes
    one back. Anything else is a schedule to book -- and it books through
    the SAME guards a Schedule button did, because the refusals are the
    point of them: a schedule that was always going to fail is worse than
    a refusal, since it looks like it worked.

    Everything it says, it says by flashing. The caller has already saved
    and already said so.
    """
    wanted = (request.form.get("schedule_name") or "none").strip()
    waiting = scheduling.pending_for(db, "newsletter", newsletter_id)
    if wanted == "none":
        if waiting and scheduling.cancel(db, "newsletter", newsletter_id):
            db.commit()
            flash("Taken off the clock. It is a draft again.", "success")
        return

    still_missing = email_layouts.missing(newsletter.composed_blocks(row))
    if still_missing:
        flash("Saved, but not put on the clock: fill in %s first."
              % ", ".join(still_missing), "warning")
        return
    _put_on_clock(db, "newsletter", newsletter_id, (row["subject"] or "").strip(),
                  _composed_sections(db, row), None)


@bp.route("/newsletters/issue/<int:newsletter_id>", methods=["GET", "POST"])
@login_required
def newsletter_issue_edit(newsletter_id):
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))
    if request.method == "POST":
        #  Which blog keeps a copy. Empty is the answer as well as the
        #  absence of one -- unticking the box has to be able to turn it
        #  OFF, so this is always passed and never conditional on the
        #  field being present.
        keep = (request.form.get("blog_id") or "").strip()
        newsletter.save_blocks(
            db, newsletter_id,
            (request.form.get("subject") or "").strip(),
            _blocks_from_form(request.form),
            layout=(request.form.get("layout") or "").strip() or None,
            blog_id=int(keep) if keep.isdigit() else None)
        db.commit()
        flash("Saved.", "success")
        #  ...and what it is waiting on. There was a Schedule button
        #  beside Save and it was the only thing that booked anything, so
        #  choosing a schedule and pressing Save set a control and threw
        #  it away. Save does the work.
        #
        #  AFTER the commit above, deliberately: scheduling can refuse --
        #  no email set up, nobody on the list, no postal address -- and
        #  a refusal must never cost somebody the words they just wrote.
        #  Re-read, not the row from before the save. `row` is what this
        #  newsletter was when the request arrived, and scheduling asks
        #  it for its subject -- so naming a newsletter and scheduling it
        #  in one press was refused with "give it a subject first", about
        #  the subject that had just been typed.
        _apply_schedule_choice(db, newsletter_id,
                               newsletter.get_composed(db, newsletter_id) or row)
        #  Back where it was pressed. The tool is on two pages, and
        #  saving from one of them should not land somebody on the other.
        back = (request.form.get("next") or "").strip()
        if back.startswith("/admin/"):
            return redirect(back)
        return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id))

    return render_template("admin/newsletter_issue_edit.html",
                           **_editor_context(db, row))


@bp.route("/newsletters/issue/<int:newsletter_id>/preview", methods=["GET", "POST"])
@login_required
def newsletter_issue_preview(newsletter_id):
    """Exactly what will be sent, wrapper and all -- a preview of
    something else is not a preview.

    POSTed, it previews what is in the FORM rather than what was last
    saved, and saves nothing. That is what lets the editor show the email
    changing as somebody types: writing a newsletter blind and pressing
    Preview afterwards is guessing with an extra step.
    """
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))
    if request.method == "POST":
        row = dict(row, subject=request.form.get("subject") or row["subject"],
                   values_json=json.dumps({"blocks": _blocks_from_form(request.form)}))
    site_title = (get_site_settings(db) or {}).get("site_title") or "Our newsletter"
    line, _ = newsletter.sender_line(legal.settings_for(db), site_title)
    intro, outro = _wrapped(db, row["subject"], None,
                            newsletter.composed_blocks(row))
    return newsletter.to_email_html(
        _composed_sections(db, row), site_title, "#unsubscribe-link", line,
        None, look=_look(db), intro=intro, outro=outro)


#  ---- Sending it later ----
#
#  A scheduled send runs on a background thread with no request, so
#  everything it needs has to be worked out from the database alone. That
#  is why `_run_scheduled` takes an app and a row and nothing else, and
#  why the two guards below exist: without a public address there is
#  nowhere for an unsubscribe link to point, and `request.host_url` --
#  which a live send falls back on -- is not there to save it.


def _sections_for_schedule(db, row):
    """What a due job should actually send: (sections, subject, view_url).

    Looked up NOW rather than frozen when it was scheduled.

    Deliberate: somebody who schedules a newsletter and then fixes a typo
    in it expects the fixed one to go. The subject is stored on the job
    for the same reason it is shown on the list -- so a schedule can be
    read without opening what it points at -- but the CONTENT is always
    the current content.
    """
    if row["kind"] == "newsletter":
        item = newsletter.get_composed(db, row["target_id"])
        if not item:
            return None, "", None
        return _composed_sections(db, item), item["subject"] or "", None
    if row["kind"] == "post":
        post, blog = _post_and_blog(db, row["target_id"])
        if not post:
            return None, "", None
        #  A scheduled post publishes itself on the way out, the same way
        #  pressing Send does -- an email whose "read it online" link
        #  answers Not Found is worse than either. Done HERE rather than
        #  when the schedule was made, because scheduling a post is not
        #  publishing it either: it stays a draft until the moment it
        #  goes.
        if not post["published_at"]:
            db.execute("UPDATE blog_posts SET published_at = CURRENT_TIMESTAMP WHERE id = ?",
                       (row["target_id"],))
            db.commit()
            post = db.execute("SELECT * FROM blog_posts WHERE id = ?",
                              (row["target_id"],)).fetchone()
        return (newsletter.as_sections(post["title"], blog_service.post_html(post["content"])),
                post["title"], _post_view_url(db, blog, post))
    return None, "", None


def _run_scheduled(app, row):
    """One due job, start to finish. Never raises: the poller has to
    survive a job that cannot go.

    It runs inside a REQUEST context, made from the site's own address,
    which is not a trick: `url_for` cannot build a link without knowing
    what host to build it for, and a thread has no request to borrow one
    from. The site's public address is the correct answer -- it is the
    address the unsubscribe link has to work at -- and reading it first
    is also the check that there IS one. Without it the job is refused
    rather than sent with a link to nowhere, which would be worse than
    not sending.
    """
    from ...services import scheduling
    with app.app_context():
        base = site.public_base(get_db())
    if not base:
        with app.app_context():
            scheduling.finish(get_db(), row["id"], 0, 0,
                              "This site does not know its own web address yet, so an "
                              "unsubscribe link could not be built. Set it on the Sending "
                              "email screen, then schedule it again.")
        return

    with app.test_request_context(base_url=base):
        db = get_db()
        try:
            #  Publishing is not sending, and it is the only due job that
            #  needs no email at all: no list, no postal address, no
            #  wrapper. Answered first, so none of the checks below --
            #  every one of which is about an inbox -- can refuse a post
            #  going public for a reason that has nothing to do with it.
            if row["kind"] == "publish":
                made = blog_service.publish(db, row["target_id"])
                scheduling.finish(db, row["id"], 0, 0,
                                  None if made else "That post no longer exists.")
                db.commit()
                return
            sections, subject, view_url = _sections_for_schedule(db, row)
            if not sections:
                scheduling.finish(db, row["id"], 0, 0,
                                  "There is nothing to send — it may have been deleted.")
                return
            subject = (row["subject"] or subject or "").strip()
            email_settings = get_email_settings(db)
            site_title = (get_site_settings(db) or {}).get("site_title") or "Our newsletter"
            verdict = newsletter.preflight(
                db, mailer, subscribers, legal, sections, row["audience"],
                email_settings, legal.settings_for(db), site_title)
            if isinstance(verdict, newsletter.Blocked):
                scheduling.finish(db, row["id"], 0, 0, verdict.message)
                return
            #  A scheduled send of a composed newsletter reads its own
            #  blocks, so one carrying its own opening is not given a
            #  second one an hour after it was written.
            intro, outro = _wrapped(
                db, subject, view_url,
                newsletter.composed_blocks(newsletter.get_composed(db, row["target_id"]))
                if row["kind"] == "newsletter"
                and newsletter.get_composed(db, row["target_id"]) else None)
            sent, failed = newsletter.deliver(
                db, mailer, email_settings, verdict, sections, subject, view_url,
                _look(db), intro, outro, row["audience"], row["kind"], row["target_id"],
                lambda token: site.absolute(db, url_for("public.unsubscribe", token=token)))
            scheduling.finish(db, row["id"], sent, failed)
            #  The same act as the button's, through the same function --
            #  "on the same schedule the email is published" is exactly
            #  what this is for, so the entry is dated the day it went.
            if sent:
                _keep_a_copy(db, row["kind"], row["target_id"])
            db.commit()
        except Exception as e:                      # noqa: BLE001
            app.logger.exception("scheduled send %s failed", row["id"])
            try:
                scheduling.finish(db, row["id"], 0, 0, str(e)[:300])
            except Exception:                       # noqa: BLE001
                pass


def arm_scheduler(app):
    """Start this process's poller. Called on the first request (see
    services/scheduling.py for why it cannot be at import time)."""
    return scheduling.start(app, _run_scheduled)


@bp.route("/newsletters/post/<int:post_id>/schedule", methods=["POST"])
@login_required
def newsletter_post_schedule(post_id):
    """A blog post, on the clock.

    It goes through the same routine as a newsletter -- the guards, the
    claim, the poller -- because it is the same act. What differs is only
    what gets looked up when it becomes due, and that lives in
    `_sections_for_schedule`. A post is NOT published by scheduling it:
    scheduling is not publishing, and it stays a draft until the moment
    it actually goes.
    """
    db = get_db()
    post, blog = _post_and_blog(db, post_id)
    back = _back_to(None)
    if not post:
        flash("That post doesn't exist.", "error")
        return redirect(url_for("admin.newsletters"))
    if request.form.get("cancel"):
        scheduling.cancel(db, "post", post_id)
        db.commit()
        flash("That send is off the clock.", "success")
        return redirect(back)
    subject = (request.form.get("subject") or post["title"]).strip()
    sections = newsletter.as_sections(post["title"],
                                      blog_service.post_html(post["content"]))
    return _put_on_clock(db, "post", post_id, subject, sections, back)


def _when_from_form(db):
    """The moment a form is asking for: (when, schedule name, refusal).

    One reader, because there are two things that can be put on a clock
    now -- a newsletter to send, and a post to publish -- and a second
    copy of this is how the two would come to disagree about what "the
    first Monday" means, or about whether a date in the past is allowed.

    A named schedule, or a moment somebody typed. The named one is the
    point of having them: it says WHEN in words the owner chose, and the
    next occurrence is worked out rather than retyped.
    """
    picked = (request.form.get("schedule_name") or "").strip()
    template = scheduling.template(db, picked) if picked else None
    if picked and not template:
        return None, None, "That schedule no longer exists."
    if template is not None:
        #  The date they chose from that schedule's own list -- checked
        #  against it, so a stale page cannot book a time the schedule
        #  does not produce. It happens ONCE, at that moment: a schedule
        #  says when the next one goes, it does not keep going.
        offered = scheduling.upcoming(template, scheduling.utcnow(), 8)
        wanted = (request.form.get("schedule_date") or "").strip()
        allowed = {d.strftime("%Y-%m-%d %H:%M:%S"): d for d in offered}
        when = allowed.get(wanted) or (offered[0] if offered else None)
        if not when:
            return None, None, "That schedule has no next date in it."
    else:
        when = scheduling.to_utc(request.form.get("send_at"),
                                 request.form.get("tz_offset"))
    if not when:
        return None, None, "Choose a schedule, or a date and time."
    if when <= scheduling.utcnow():
        return None, None, ("That time has already passed — pick one in the "
                            "future, or do it now.")
    return when, picked or None, None


def _go(where):
    """Redirect, or don't. A caller that is mid-request and going
    somewhere of its own passes None and gets None: nothing here decides
    where anybody lands except by being asked to."""
    return redirect(where) if where else None



def _put_on_clock(db, kind, target_id, subject, sections, back):
    """The refusals a schedule makes, and the booking if it makes none.

    Every one of these is a refusal a SEND would make. Made now rather
    than in the middle of the night with nobody watching: a schedule that
    was always going to fail is worse than a refusal, because it looks
    like it worked.

    `back` is where to go afterwards, or None when the caller is already
    on its way somewhere -- Save applies the schedule and then redirects
    itself. Everything this function has to say, it says by flashing, so
    it is the same routine either way.
    """
    when, named, refusal = _when_from_form(db)
    if refusal:
        flash(refusal, "error")
        return _go(back)
    if not subject:
        flash("Give it a subject first — that is the line people decide on.", "error")
        return _go(back)

    site_title = (get_site_settings(db) or {}).get("site_title") or "Our newsletter"
    audience = request.form.get("audience") or "all"
    verdict = newsletter.preflight(
        db, mailer, subscribers, legal, sections, audience,
        get_email_settings(db), legal.settings_for(db), site_title)
    if isinstance(verdict, newsletter.Blocked):
        flash(verdict.message, "error")
        return _go(url_for(verdict.where) if verdict.where else back)
    if not site.public_base(db):
        flash("This site does not know its own web address yet, and a scheduled send needs "
              "one to build the unsubscribe link. Set it on the Sending email screen.", "error")
        return _go(url_for("admin.settings_email"))

    scheduling.schedule(db, kind, target_id, subject, audience, when,
                        template_name=named)
    if named:
        scheduling.mark_used(db, named, scheduling.utcnow())
    db.commit()
    arm_scheduler(current_app._get_current_object())
    flash("Scheduled. It goes out on its own — you do not have to be here.", "success")
    return _go(back)


@bp.route("/newsletters/issue/<int:newsletter_id>/schedule", methods=["POST"])
@login_required
def newsletter_issue_schedule(newsletter_id):
    """Put it on the clock, or take it back off."""
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    back = url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))

    if request.form.get("cancel"):
        scheduling.cancel(db, "newsletter", newsletter_id)
        db.commit()
        flash("That send is off the clock.", "success")
        return redirect(back)

    #  A newsletter has one refusal a post does not: an empty block that
    #  would arrive broken.
    still_missing = email_layouts.missing(newsletter.composed_blocks(row))
    if still_missing:
        flash("Fill in %s first." % ", ".join(still_missing), "error")
        return redirect(back)
    return _put_on_clock(db, "newsletter", newsletter_id, (row["subject"] or "").strip(),
                         _composed_sections(db, row), back)


@bp.route("/newsletters/issue/<int:newsletter_id>/send", methods=["POST"])
@login_required
def newsletter_issue_send(newsletter_id):
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    back = url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))
    still_missing = email_layouts.missing(newsletter.composed_blocks(row))
    if still_missing or not (row["subject"] or "").strip():
        #  Named, so the refusal says what to do rather than that
        #  something is wrong.
        wanted = (["a subject"] if not (row["subject"] or "").strip() else []) + still_missing
        flash("Fill in %s first." % ", ".join(wanted), "error")
        return redirect(back)
    return _send_it(db, "newsletter", newsletter_id, _composed_sections(db, row),
                    row["subject"], None, back,
                    blocks=newsletter.composed_blocks(row))


@bp.route("/newsletters/issue/write", methods=["POST"])
@login_required
def newsletter_issue_write():
    """A first draft from a sentence about what the issue is for.

    It creates a newsletter and opens it, exactly as writing one by hand
    does. Nothing here sends anything: an AI writing to somebody else's
    mailing list over their name is the one place in this app where a
    plausible-sounding mistake reaches real people and cannot be taken
    back, so a person reads it and presses Send.
    """
    db = get_db()
    site_title = (get_site_settings(db) or {}).get("site_title") or ""
    try:
        subject, blocks = newsletter_ai.draft(
            db, request.form.get("brief"), site_title)
    except newsletter_ai.Refused as why:
        flash(str(why), "error")
        return redirect(url_for("admin.newsletters"))
    new_id = newsletter.create_composed(db, "letter", subject)
    newsletter.save_blocks(db, new_id, subject, blocks, layout="letter")
    db.commit()
    flash("Here is a first draft. Read it before you send it — nothing has "
          "gone anywhere yet.", "success")
    return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=new_id))


@bp.route("/newsletters/issue/<int:newsletter_id>/copy", methods=["POST"])
@login_required
def newsletter_issue_copy(newsletter_id):
    """Start this month's from last month's."""
    db = get_db()
    new_id = newsletter.copy_composed(db, newsletter_id)
    if not new_id:
        flash("That newsletter no longer exists.", "error")
        return redirect(url_for("admin.newsletters"))
    db.commit()
    flash("Copied. This is the copy — the original is untouched.", "success")
    return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=new_id))


@bp.route("/newsletters/issue/<int:newsletter_id>/send-now", methods=["POST"])
@login_required
def newsletter_issue_send_now(newsletter_id):
    """Send it from the list, without opening it first.

    The same send the editor does -- same checks, same refusals -- so
    there is one path a newsletter can leave by, not two that can
    disagree about whether it was ready.
    """
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    if not row:
        flash("That newsletter no longer exists.", "error")
        return redirect(url_for("admin.newsletters"))
    back = url_for("admin.newsletters")
    still_missing = email_layouts.missing(newsletter.composed_blocks(row))
    if still_missing or not (row["subject"] or "").strip():
        wanted = (["a subject"] if not (row["subject"] or "").strip() else []) \
            + still_missing
        flash("Fill in %s first." % ", ".join(wanted), "error")
        return redirect(url_for("admin.newsletter_issue_edit",
                                newsletter_id=newsletter_id))
    #  Sending by hand does NOT take it off the clock -- the job is still
    #  there and would send it again. Cancelled here, and said, because
    #  the alternative is the list getting it twice.
    was_waiting = scheduling.cancel(db, "newsletter", newsletter_id)
    if was_waiting:
        flash("This one was waiting on a schedule; that has been taken off "
              "so it does not go twice.", "success")
    return _send_it(db, "newsletter", newsletter_id, _composed_sections(db, row),
                    row["subject"], None, back,
                    blocks=newsletter.composed_blocks(row))


@bp.route("/newsletters/schedules/save", methods=["POST"])
@login_required
def newsletter_schedule_template_save():
    """Name a time, so it is defined once and assigned rather than
    retyped into a date box every month."""
    db = get_db()
    ok_, error = scheduling.save_template(
        db, request.form.get("name"), request.form.get("repeat_kind"),
        request.form.get("hour"), request.form.get("minute"),
        request.form.get("weekday") or None,
        request.form.get("monthday") or None,
        when=request.form.get("when") or None,
        #  The clock the hour was typed on. Without it "9am" is 9am UTC.
        tz_offset=request.form.get("tz_offset") or 0,
        #  The zone, not just the offset: only a zone knows when the
        #  clocks change, and an offset captured in summer is wrong all
        #  winter.
        tz_name=request.form.get("tz_name"),
        month_day=request.form.get("month_day") or "first")
    if error:
        flash(error, "error")
    else:
        db.commit()
        flash("Saved. You can pick it when you schedule a newsletter.", "success")
    return redirect(url_for("admin.newsletters"))


@bp.route("/newsletters/schedules/delete", methods=["POST"])
@login_required
def newsletter_schedule_template_delete():
    db = get_db()
    gone = scheduling.delete_template(db, request.form.get("name"))
    db.commit()
    flash("Removed." if gone else "That schedule no longer exists.",
          "success" if gone else "error")
    return redirect(url_for("admin.newsletters"))


@bp.route("/newsletters/layouts/save", methods=["POST"])
@login_required
def newsletter_layout_save():
    """Keep the arrangement in front of you, under a name, for next time.

    The blocks come from the canvas rather than from what was last saved,
    so this keeps what is ON SCREEN -- somebody who has just arranged
    something and likes it should not have to save the newsletter first
    to be able to save its shape.
    """
    db = get_db()
    try:
        blocks = json.loads(request.form.get("blocks_json") or "[]")
    except (ValueError, TypeError):
        blocks = []
    key, error = email_layouts.save_layout(db, request.form.get("name"), blocks)
    if error:
        if wants_json():
            return jsonify({"error": error}), 400
        flash(error, "error")
    else:
        db.commit()
        if wants_json():
            return jsonify({"ok": True, "key": key})
        flash("Saved. It is in the Template list now.", "success")
    return redirect(request.form.get("next") or url_for("admin.newsletters"))


@bp.route("/newsletters/layouts/delete", methods=["POST"])
@login_required
def newsletter_layout_delete():
    """Remove one of your own arrangements.

    Only your own: a shipped layout lives in the code and would be back
    on the next boot, so offering to delete one would be a button that
    lies. Nothing else refers to a layout once a newsletter has been laid
    out from it -- the blocks were copied, not linked -- so removing one
    cannot affect anything already written.
    """
    db = get_db()
    gone = email_layouts.delete_layout(db, request.form.get("key"))
    db.commit()
    if wants_json():
        return jsonify({"ok": bool(gone)})
    flash("Removed from the Template list." if gone
          else "That one is built in, so it cannot be removed.",
          "success" if gone else "error")
    return redirect(request.form.get("next") or url_for("admin.newsletters"))


@bp.route("/newsletters/issue/<int:newsletter_id>/delete", methods=["POST"])
@login_required
def newsletter_issue_delete(newsletter_id):
    db = get_db()
    #  Take it off the clock first. A scheduled job pointing at a deleted
    #  newsletter is not dangerous -- the poller finds nothing to send and
    #  says so -- but it leaves a row on the "going out on its own" table
    #  promising something that cannot arrive, which is worse than either
    #  sending or not.
    taken_off = scheduling.cancel(db, "newsletter", newsletter_id)
    newsletter.delete_composed(db, newsletter_id)
    db.commit()
    flash("Newsletter deleted. What was already sent is still recorded."
          + (" It was on the clock, and is no longer." if taken_off else ""),
          "success")
    return redirect(url_for("admin.newsletters"))


def _keep_a_copy(db, kind, target_id, blocks=None, when=None):
    """A sent newsletter, kept as a blog entry if it asked to be.

    One function, called by the button's path and by the scheduler,
    because "and also publish it" existing twice is how one of the two
    comes to be forgotten. Returns a sentence to show, or None -- and
    None is the ordinary answer, since most newsletters are only ever
    email.

    A page or a post being sent is already on the site; there is nothing
    to keep.
    """
    if kind != "newsletter":
        return None
    row = newsletter.get_composed(db, target_id)
    if not row:
        return None
    post_id = newsletter.keep_as_post(db, blog_service, row, blocks, when)
    if not post_id:
        return None
    blog = blog_service.get_blog(db, row["blog_id"])
    return "Also saved to %s as a blog entry." % (blog["name"] if blog else "the blog")


def _send_it(db, kind, target_id, sections, subject, view_url, back, blocks=None):
    """Everything a send has to be sure of, once, for a page or a post.

    Both callers used to be one route with the page baked into it. The
    checks are the interesting part and none of them is about pages: is
    there anything to send with, is there a postal address on file, is
    there anybody to send to once the audience is applied, and is there
    any content at all.
    """
    email_settings = get_email_settings(db)
    site_settings = get_site_settings(db) or {}
    site_title = site_settings.get("site_title") or "Our newsletter"
    audience = request.form.get("audience") or "all"
    if audience not in dict(subscribers.AUDIENCES):
        audience = "all"

    #  The same checks a SCHEDULED send makes, asked in one place so the
    #  two cannot drift. This route's job is only to say what the answer
    #  means to somebody looking at a screen.
    verdict = newsletter.preflight(
        db, mailer, subscribers, legal, sections, audience,
        email_settings, legal.settings_for(db), site_title)
    if isinstance(verdict, newsletter.Blocked):
        flash(verdict.message, "error")
        return redirect(url_for(verdict.where) if verdict.where else back)
    intro, outro = _wrapped(db, subject, view_url, blocks)
    sent, failed = newsletter.deliver(
        db, mailer, email_settings, verdict, sections, subject, view_url,
        _look(db), intro, outro, audience, kind, target_id,
        lambda token: site.absolute(db, url_for("public.unsubscribe", token=token),
                                    request.host_url))
    kept = _keep_a_copy(db, kind, target_id, blocks) if sent else None
    db.commit()

    who = "customers" if audience == "customers" else "the list"
    if failed:
        flash(f"Sent to {sent} of {who}. {failed} didn't go through — usually an address that no "
              "longer exists.", "warning")
    else:
        flash(f"Sent to {sent} {'person' if sent == 1 else 'people'} on {who}.", "success")
    if kept:
        flash(kept, "success")
    return redirect(back)


def _post_and_blog(db, post_id):
    post = db.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        return None, None
    return post, blog_service.get_blog(db, post["blog_id"])


def _post_view_url(db, blog, post):
    """Where to read it online — if there is anywhere. An unpublished post
    is visible only to its owner, so promising a link would be a link to
    Not Found."""
    if not post["published_at"] or not blog:
        return None
    return site.absolute(db, url_for("public.blog_post", slug=blog["slug"],
                                     post_slug=post["slug"]), request.host_url)


@bp.route("/newsletters/sent/<int:send_id>/delete", methods=["POST"])
@login_required
def newsletter_send_forget(send_id):
    """Takes one line off the record of what has gone out.

    Offered because it is the owner's record of their own site. Worth
    knowing what it costs, which the confirmation says: this line is how
    "you emailed me" is answered later, and nothing else keeps it.
    """
    db = get_db()
    newsletter.forget_send(db, send_id)
    db.commit()
    flash("Removed from the record. The people it went to are unaffected.", "success")
    return redirect(url_for("admin.newsletters"))


@bp.route("/newsletters/wrapper", methods=["POST"])
@login_required
def newsletter_wrapper():
    """Saves the greeting and the sign-off every send is wrapped in.

    Plain text, not HTML: blank lines make paragraphs, the same as a blog
    post typed in this admin. There is no raw-markup box anywhere in this
    app for something an owner writes, and this is not going to be the
    first one.
    """
    db = get_db()
    for key in WRAPPER_KEYS:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (key, (request.form.get(key) or "").strip()))
    db.commit()
    flash("Saved. Every newsletter from now on opens and closes this way.", "success")
    return redirect(url_for("admin.newsletters"))


@bp.route("/newsletters/post/<int:post_id>/send", methods=["POST"])
@login_required
def newsletter_send_post(post_id):
    """Emails a blog post to the list.

    A post is the natural shape for an issue and this app already had
    it: a title, a date, a permanent address built from its blog's slug,
    and an online copy to link to. What it did not have was a way to
    post it.

    A draft is published first. Sending is not publishing, but an email
    whose "read it online" link answers Not Found is worse than either --
    so Send says, in the confirm, that it will publish and then send.
    """
    db = get_db()
    post, blog = _post_and_blog(db, post_id)
    if not post:
        flash("That post doesn't exist.", "error")
        return redirect(url_for("admin.newsletters"))
    back = _back_to(None)
    if not post["published_at"]:
        db.execute("UPDATE blog_posts SET published_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
        db.commit()
        post = db.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,)).fetchone()
        flash(f'Published "{post["title"]}" so it can be read online.', "success")
    subject = (request.form.get("subject") or post["title"]).strip()
    sections = newsletter.as_sections(post["title"], blog_service.post_html(post["content"]))
    return _send_it(db, "post", post_id, sections, subject,
                    _post_view_url(db, blog, post), back)


@bp.route("/newsletters/post/<int:post_id>/preview")
@login_required
def newsletter_preview_post(post_id):
    """The email itself, in a browser, before anybody else sees it."""
    db = get_db()
    post, blog = _post_and_blog(db, post_id)
    if not post:
        return redirect(url_for("admin.newsletters"))
    site_settings = get_site_settings(db) or {}
    line, _ = newsletter.sender_line(legal.settings_for(db), site_settings.get("site_title"))
    view_url = _post_view_url(db, blog, post)
    intro, outro = _wrapped(db, post["title"], view_url)
    return newsletter.to_email_html(
        newsletter.as_sections(post["title"], blog_service.post_html(post["content"])),
        site_settings.get("site_title") or "Newsletter", "#",
        line or "Your business name and address goes here",
        view_url, look=_look(db), intro=intro, outro=outro,
    )


@bp.route("/newsletters/<int:page_id>/send", methods=["POST"])
@login_required
def newsletter_send(page_id):
    """Turns a page into an email and posts it to the list.

    Sent one message at a time rather than as one message with everybody
    hidden in the copy line: each person needs their own unsubscribe link,
    and a single message addressed to hundreds is both a privacy incident
    waiting to happen and the fastest way to have a mail account
    suspended.
    """
    db = get_db()
    page = db.execute(
        "SELECT * FROM pages WHERE id = ? AND page_type = 'newsletter'", (page_id,)
    ).fetchone()
    if not page:
        flash("That newsletter doesn't exist.", "error")
        return redirect(url_for("admin.newsletters"))

    sections = _page_sections(db, page_id)
    #  Which part of the page: everything, the latest, or one section.
    #  The only thing about a page send that a post send does not have.
    sections, _what = newsletter.sections_for(sections, request.form.get("parts") or "all")
    subject = (request.form.get("subject") or page["title"]).strip()
    #  A "read it online" link only if there is one. A page the owner has
    #  kept off the site has no online copy, so promising one in the email
    #  would be a link to a page that answers Not Found.
    view_url = (site.absolute(db, url_for("public.page", slug=page["slug"]), request.host_url)
                if page["is_public"] else None)
    return _send_it(db, "page", page_id, sections, subject, view_url, _back_to(page))


@bp.route("/newsletters/<int:page_id>/preview")
@login_required
def newsletter_preview(page_id):
    """The email itself, in a browser, before anyone else sees it.

    Worth having because the email is deliberately NOT the page: styling
    is inlined, and forms, video and anything else mail cannot do are
    dropped. Better to find that out here than in somebody's inbox.
    """
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if not page:
        return redirect(url_for("admin.newsletters"))
    #  Previewed the same way it will be sent, including which part of the
    #  page -- a preview of something else is not a preview.
    sections, _what = newsletter.sections_for(
        _page_sections(db, page_id), request.args.get("parts") or "all")
    site_settings = get_site_settings(db) or {}
    line, _ = newsletter.sender_line(legal.settings_for(db), site_settings.get("site_title"))
    view_url = (site.absolute(db, url_for("public.page", slug=page["slug"]), request.host_url)
                if page["is_public"] else None)
    intro, outro = _wrapped(db, page["title"], view_url)
    return newsletter.to_email_html(
        sections, site_settings.get("site_title") or "Newsletter",
        "#", line or "Your business name and address goes here",
        view_url, look=_look(db), intro=intro, outro=outro,
    )


def _back_to(page=None):
    """Where a send should land: the page it was sent from, if that is
    where the button was pressed."""
    where = (request.form.get("next") or "").strip()
    if where.startswith("/") and not where.startswith("//"):
        return where
    return url_for("admin.newsletters")


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/schedule", methods=["POST"])
@login_required
def blog_post_schedule(blog_id, post_id):
    """Publish this post by itself, later.

    The same machinery a scheduled send uses -- the same table, the same
    claim, the same poller -- because it is the same act with a different
    verb at the end of it. What differs is only what happens when it
    becomes due, and that is one branch in `_run_scheduled`.

    A post scheduled this way is NOT emailed. Publishing and sending are
    two decisions and were one control for as long as a post could only
    be put on a clock by being sent; an owner who writes weekly and mails
    monthly could not say so.
    """
    db = get_db()
    post = db.execute("SELECT * FROM blog_posts WHERE id = ? AND blog_id = ?",
                      (post_id, blog_id)).fetchone()
    back = (request.form.get("next") or "").strip()
    back = back if back.startswith("/admin/") else url_for("admin.blogs_screen")
    if not post:
        flash("That post no longer exists.", "error")
        return redirect(back)

    when, named, refusal = _when_from_form(db)
    if refusal:
        flash(refusal, "error")
        return redirect(back)
    scheduling.schedule(db, "publish", post_id, post["title"] or "", "all", when,
                        template_name=named)
    if named:
        scheduling.mark_used(db, named, scheduling.utcnow())
    db.commit()
    flash("It will be published by itself at the time you chose.", "success")
    return redirect(back)


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/schedule/cancel", methods=["POST"])
@login_required
def blog_post_schedule_cancel(blog_id, post_id):
    db = get_db()
    back = (request.form.get("next") or "").strip()
    back = back if back.startswith("/admin/") else url_for("admin.blogs_screen")
    if scheduling.cancel(db, "publish", post_id):
        db.commit()
        flash("Taken off the schedule. The post is as you left it.", "success")
    else:
        #  Not an error: a claimed job is already going out and cannot be
        #  recalled, and saying otherwise would be a lie.
        flash("That one is already on its way, so it cannot be taken back.", "warning")
    return redirect(back)
