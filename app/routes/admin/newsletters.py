"""
The Newsletters screen: the list of newsletter pages, and sending one.

A newsletter is a page, so nothing here authors anything — the writing
happens in the normal editor, on the page itself. This is only the two
things a page cannot do for itself: turn into an email, and remember that
it went out.
"""
from flask import request, flash, redirect, url_for, render_template, current_app

from . import bp, get_email_settings, get_site_settings
from ..auth import login_required
from ...db import get_db
from ... import mailer
import json

from . import FONT_PAIRINGS
from ...services import (blog as blog_service, email_layouts, legal, newsletter, palette, site,
                         subscribers)


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
        composed=newsletter.list_composed(db),
        composed_sends={row["id"]: newsletter.last_send(db, "newsletter", row["id"])
                        for row in newsletter.list_composed(db)},
        layout_choices=email_layouts.choices(),
        #  Each shape shown filled in, not merely named: what a layout
        #  looks like is the whole basis on which one is chosen.
        layout_samples={key: email_layouts.sample(key, _look(db))
                        for key, _n, _b in email_layouts.choices()},
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


#  ---- A newsletter of its own ----
#
#  A layout with named slots, rather than a page written with tools that
#  do not survive an inbox. The send path below is shared with pages and
#  posts unchanged: a layout's body is one HTML section, which is what
#  `sections` has always been.
def _composed_sections(db, row):
    body = email_layouts.render(row["layout"], newsletter.composed_values(row), _look(db))
    return [{"type": "html", "title": "", "content": body}]


@bp.route("/newsletters/issue/new", methods=["POST"])
@login_required
def newsletter_issue_new():
    db = get_db()
    layout = (request.form.get("layout") or "letter").strip()
    if layout not in email_layouts.LAYOUTS:
        layout = "letter"
    new_id = newsletter.create_composed(db, layout)
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
        fields = email_layouts.fields_for(row["layout"])
        values = {f["key"]: (request.form.get(f["key"]) or "").strip() for f in fields}
        newsletter.save_composed(db, newsletter_id, (request.form.get("subject") or "").strip(), values)
        db.commit()
        flash("Saved.", "success")
        return redirect(url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id))

    line, has_address = newsletter.sender_line(
        legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))
    return render_template(
        "admin/newsletter_issue_edit.html",
        item=row,
        layout=email_layouts.LAYOUTS[row["layout"]],
        fields=email_layouts.fields_for(row["layout"]),
        values=newsletter.composed_values(row),
        missing=email_layouts.missing(row["layout"], newsletter.composed_values(row)),
        audiences=subscribers.AUDIENCES,
        audience_counts={key: subscribers.audience_count(db, key)
                         for key, _label in subscribers.AUDIENCES},
        last=newsletter.last_send(db, "newsletter", newsletter_id),
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
        typed = {f["key"]: (request.form.get(f["key"]) or "")
                 for f in email_layouts.fields_for(row["layout"])}
        row = dict(row, subject=request.form.get("subject") or row["subject"],
                   values_json=json.dumps(typed))
    site_title = (get_site_settings(db) or {}).get("site_title") or "Our newsletter"
    line, _ = newsletter.sender_line(legal.settings_for(db), site_title)
    intro, outro = _wrapped(db, row["subject"], None)
    return newsletter.to_email_html(
        _composed_sections(db, row), site_title, "#unsubscribe-link", line,
        None, look=_look(db), intro=intro, outro=outro)


@bp.route("/newsletters/issue/<int:newsletter_id>/send", methods=["POST"])
@login_required
def newsletter_issue_send(newsletter_id):
    db = get_db()
    row = newsletter.get_composed(db, newsletter_id)
    back = url_for("admin.newsletter_issue_edit", newsletter_id=newsletter_id)
    if not row:
        return redirect(url_for("admin.newsletters"))
    still_missing = email_layouts.missing(row["layout"], newsletter.composed_values(row))
    if still_missing or not (row["subject"] or "").strip():
        #  Named, so the refusal says what to do rather than that
        #  something is wrong.
        wanted = (["a subject"] if not (row["subject"] or "").strip() else []) + still_missing
        flash("Fill in %s first." % ", ".join(wanted), "error")
        return redirect(back)
    return _send_it(db, "newsletter", newsletter_id, _composed_sections(db, row),
                    row["subject"], None, back)


@bp.route("/newsletters/issue/<int:newsletter_id>/delete", methods=["POST"])
@login_required
def newsletter_issue_delete(newsletter_id):
    db = get_db()
    newsletter.delete_composed(db, newsletter_id)
    db.commit()
    flash("Newsletter deleted. What was already sent is still recorded.", "success")
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
    if not mailer.is_configured(email_settings):
        flash("Email isn't set up yet, so there is nothing to send with.", "error")
        return redirect(url_for("admin.settings_email"))
    if not sections:
        flash("There's nothing in this to send — write it first.", "error")
        return redirect(back)

    audience = request.form.get("audience") or "all"
    if audience not in dict(subscribers.AUDIENCES):
        audience = "all"
    #  Confirmed only. An address that was typed into the form and never
    #  answered its confirmation mail is on the table so it can be shown
    #  and so a second attempt does not make a second row -- it is not a
    #  subscriber, and sending to it is the exact thing double opt-in
    #  exists to prevent.
    people = subscribers.listing(db, confirmed_only=True, audience=audience)
    if not people:
        counts = subscribers.counts(db)
        if audience == "customers":
            flash("Nobody on the list has bought anything yet, so there are no customers to "
                  "send to. You can flag somebody as a customer by hand on the Email list "
                  "screen.", "error")
        else:
            flash("Nobody has confirmed yet." if counts["pending"]
                  else "Nobody is on the list yet.", "error")
        return redirect(back)

    site_settings = get_site_settings(db) or {}
    site_title = site_settings.get("site_title") or "Our newsletter"
    line, has_address = newsletter.sender_line(legal.settings_for(db), site_title)
    if not has_address:
        #  Refused rather than warned: a commercial email without a postal
        #  identity is unlawful in most places this will be used, and the
        #  address is two minutes of typing on a screen that already
        #  exists.
        flash("Add your postal address on the Legal pages screen first — an email to a list has "
              "to carry it, and it takes a minute.", "error")
        return redirect(url_for("admin.legal_pages"))

    intro, outro = _wrapped(db, subject, view_url)
    html = newsletter.to_email_html(sections, site_title, "{{UNSUBSCRIBE}}", line, view_url,
                                    look=_look(db), intro=intro, outro=outro)
    text = newsletter.plain_text(sections, "{{UNSUBSCRIBE}}", line,
                                 intro=intro, outro=outro)
    sent, failed = newsletter.send_to_list(
        db, mailer, email_settings, people, subject, html, text, site_title,
        lambda token: site.absolute(db, url_for("public.unsubscribe", token=token), request.host_url),
    )
    newsletter.record_send(db, kind, target_id, subject, sent, failed, audience)
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
