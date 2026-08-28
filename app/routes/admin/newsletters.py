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
import json

from . import FONT_PAIRINGS
from ...services import (blog as blog_service, email_layouts, legal, newsletter, palette,
                         scheduling, site, site_emails, subscribers)


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


def _wrapped(db, subject, view_url):
    """The greeting and the sign-off, with their two placeholders filled."""
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
    return render_template(
        "admin/newsletters.html",
        pages=pages,
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
        audiences=subscribers.AUDIENCES,
        wrapper=dict(zip(WRAPPER_KEYS, _wrapper(db))),
        wrapper_sender_line=newsletter.sender_line(
            legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))[0],
        audience_counts={key: subscribers.audience_count(db, key)
                         for key, _label in subscribers.AUDIENCES},
        #  Each page's own send menu, so "section 3" means section 3 of
        #  THAT page rather than of some notional newsletter.
        send_choices={p["id"]: newsletter.choices_for(_page_sections(db, p["id"]))
                      for p in pages},
        history=newsletter.history(db),
        counts=subscribers.counts(db),
        email_ready=mailer.is_configured(email_settings),
        sender_line=line,
        has_address=has_address,
    )


#  ---- What the site says when it writes on its own ----


#  The endpoint is named explicitly because the FUNCTION cannot be:
#  `site_emails` is the service this module imports, and a view of that
#  name would shadow it for everything below.
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
    return render_template(
        "admin/site_emails.html",
        messages=site_emails.MESSAGES,
        order=site_emails.ORDER,
        appended=site_emails.APPENDED,
        needs_unsubscribe=site_emails.NEEDS_UNSUBSCRIBE,
        #  What the owner has, verbatim, to write into.
        wording={key: site_emails.body(db, key) for key in site_emails.ORDER},
        #  ...and the same words with the placeholders filled in, which
        #  is the only way to see whether a sentence with `{{total}}` in
        #  the middle of it actually reads.
        previews={key: email_layouts.rich(site_emails.preview(db, key), look)
                  for key in site_emails.ORDER},
        block_styles=email_layouts.block_styles(look),
        look=look,
        sender_line=line,
        sample=site_emails.SAMPLE,
        email_ready=mailer.is_configured(get_email_settings(db)),
    )


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
    body = email_layouts.render(newsletter.composed_blocks(row), _look(db))
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
    newsletter.save_blocks(db, new_id, "", email_layouts.starting_blocks(layout, db))
    db.commit()
    return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=new_id))


@bp.route("/newsletters/issue/<int:newsletter_id>", methods=["GET", "POST"])
@login_required
def newsletter_issue_edit(newsletter_id):
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))
    if request.method == "POST":
        newsletter.save_blocks(
            db, newsletter_id,
            (request.form.get("subject") or "").strip(),
            _blocks_from_form(request.form),
            layout=(request.form.get("layout") or "").strip() or None)
        db.commit()
        flash("Saved.", "success")
        return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id))

    line, has_address = newsletter.sender_line(
        legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))
    look = _look(db)
    return render_template(
        "admin/newsletter_issue_edit.html",
        item=row,
        #  The email itself, with its slots opened up. This IS the editor:
        #  what is written into is what is sent.
        canvas=email_layouts.render(newsletter.composed_blocks(row), look, edit=True),
        #  What the sent email writes onto each block, so the editor can
        #  write the same thing onto a block the toolbar has just made.
        block_styles=email_layouts.block_styles(look),
        look=look,
        layout=email_layouts.LAYOUTS[row["layout"]],
        layout_choices=email_layouts.choices(db),
        #  What each template would lay out, so changing the dropdown can
        #  show the new arrangement without a round trip to ask what it
        #  is. Data, not logic: the arrangements are still decided in one
        #  place, here.
        layout_starts={key: email_layouts.starting_blocks(key, db)
                       for key, _n, _b in email_layouts.choices(db)},
        blocks=newsletter.composed_blocks(row),
        block_types=email_layouts.BLOCK_TYPES,
        block_order=email_layouts.BLOCK_ORDER,
        email_fonts=email_layouts.EMAIL_FONTS,
        alignments=email_layouts.ALIGNMENTS,
        missing=email_layouts.missing(newsletter.composed_blocks(row)),
        audiences=subscribers.AUDIENCES,
        audience_counts={key: subscribers.audience_count(db, key)
                         for key, _label in subscribers.AUDIENCES},
        last=newsletter.last_send(db, "newsletter", newsletter_id),
        #  What is on the clock for this one, so the screen can show it
        #  rather than the owner having to remember.
        scheduled=scheduling.pending_for(db, "newsletter", newsletter_id),
        email_ready=mailer.is_configured(get_email_settings(db)),
        sender_line=line,
        has_address=has_address,
    )


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
    intro, outro = _wrapped(db, row["subject"], None)
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
            intro, outro = _wrapped(db, subject, view_url)
            sent, failed = newsletter.deliver(
                db, mailer, email_settings, verdict, sections, subject, view_url,
                _look(db), intro, outro, row["audience"], row["kind"], row["target_id"],
                lambda token: site.absolute(db, url_for("public.unsubscribe", token=token)))
            scheduling.finish(db, row["id"], sent, failed)
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


def _put_on_clock(db, kind, target_id, subject, sections, back):
    """The refusals a schedule makes, and the booking if it makes none.

    Every one of these is a refusal a SEND would make. Made now rather
    than in the middle of the night with nobody watching: a schedule that
    was always going to fail is worse than a refusal, because it looks
    like it worked.
    """
    when = scheduling.to_utc(request.form.get("send_at"), request.form.get("tz_offset"))
    if not when:
        flash("Choose a date and time to send it.", "error")
        return redirect(back)
    if when <= scheduling.utcnow():
        flash("That time has already passed — pick one in the future, or press Send now.",
              "error")
        return redirect(back)
    if not subject:
        flash("Give it a subject first — that is the line people decide on.", "error")
        return redirect(back)

    site_title = (get_site_settings(db) or {}).get("site_title") or "Our newsletter"
    audience = request.form.get("audience") or "all"
    verdict = newsletter.preflight(
        db, mailer, subscribers, legal, sections, audience,
        get_email_settings(db), legal.settings_for(db), site_title)
    if isinstance(verdict, newsletter.Blocked):
        flash(verdict.message, "error")
        return redirect(url_for(verdict.where) if verdict.where else back)
    if not site.public_base(db):
        flash("This site does not know its own web address yet, and a scheduled send needs "
              "one to build the unsubscribe link. Set it on the Sending email screen.", "error")
        return redirect(url_for("admin.settings_email"))

    scheduling.schedule(db, kind, target_id, subject, audience, when)
    db.commit()
    arm_scheduler(current_app._get_current_object())
    flash("Scheduled. It goes out on its own — you do not have to be here.", "success")
    return redirect(back)


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
                    row["subject"], None, back)


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


def _send_it(db, kind, target_id, sections, subject, view_url, back):
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
    intro, outro = _wrapped(db, subject, view_url)
    sent, failed = newsletter.deliver(
        db, mailer, email_settings, verdict, sections, subject, view_url,
        _look(db), intro, outro, audience, kind, target_id,
        lambda token: site.absolute(db, url_for("public.unsubscribe", token=token),
                                    request.host_url))
    db.commit()

    who = "customers" if audience == "customers" else "the list"
    if failed:
        flash(f"Sent to {sent} of {who}. {failed} didn't go through — usually an address that no "
              "longer exists.", "warning")
    else:
        flash(f"Sent to {sent} {'person' if sent == 1 else 'people'} on {who}.", "success")
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
