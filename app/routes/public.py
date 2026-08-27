import os
import re
import json
import datetime
from html import escape as html_escape, unescape as html_unescape
from flask import Blueprint, render_template, abort, url_for, session, request, redirect, current_app, jsonify, flash, send_file, Response

from ..db import get_db, TOOL_CATEGORIES
from .. import assistant
from .. import mailer
from .. import icons
from ..services.sections import (
    MEDIA_IMAGE_EXTS,
    SECTION_TYPES,
    read_contact_tool, read_contact_layout, read_contact_icon_size, is_contact_tool_block,
    CONTACT_LAYOUTS, CONTACT_ICON_MIN, CONTACT_ICON_MAX, CONTACT_ICON_DEFAULT, MAX_CONTACT_ROWS,
    accordion_settings, buy_button_settings, faq_settings, shop_settings, table_settings,
    search_settings, SEARCH_STYLES, FAQ_VIEWS,
    faq_sources, resolve_faq_mirror, faq_mirror_items, MAX_FAQ_ITEMS, FAQ_RULES,
    faq_editor_html,
    FAQ_FORMATTING_HELP,
    _list_media,
    video_gallery_settings, youtube_id,
)
from ..services.palette import (
    _match_palette_roles, _darken_hex, tint_shade_ramp, readable_on, neutral_ramp, ramp,
    color_scheme_choices,
)
from ..services import palette as palette_service
from ..services.menu import _parse_menu_meta, _page_href
from ..services import blog as blog_service
from ..services import (blocks, captcha, cart as cart_service, commerce, downloads,
                        integrations, legal, newsletter, site, subscribers)
from .admin import (
    _list_tools, get_email_settings, get_layout_settings, get_site_settings, COLOR_PRESETS,
    NAV_LAYOUTS, get_nav_layout, SIDEBAR_LAYOUT_PRESETS, FOOTER_LAYOUT_PRESETS,
    FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS, SHADE_SPREADS, GOOGLE_FONT_CHOICES,
    _google_fonts_stylesheet_url,
)
from .admin.templates import dashboard_template_maps

bp = Blueprint("public", __name__)

SITE_TITLE = "My Site"

#  How far ahead a buyer can book. Long enough to be useful, short
#  enough that the slot list stays readable on a phone.
BOOKING_WINDOW_DAYS = 14


def _public_url(endpoint, **values):
    """An address that works from somewhere other than this machine.

    Never `url_for(_external=True)` for anything that leaves the site —
    see services/site.py: that builds from whichever host this request
    arrived on, which is the admin's localhost as often as the real one.
    """
    return site.absolute(get_db(), url_for(endpoint, **values), request.host_url)


def _dressed(db, text_body, subject):
    """(html, text) for a transactional message.

    The words are the plain text already written for it -- one wording to
    keep true, and the text half of the mail is those same words rather
    than a second draft that can drift. See
    newsletter.to_transactional_html for why the footer is not the
    newsletter's.
    """
    site_title = (get_site_settings(db) or {}).get("site_title") or "our website"
    line, _has = newsletter.sender_line(legal.settings_for(db), site_title)
    template = _active_template(db)
    look = newsletter.look_from(
        _role_color_ramps(template) if template else None,
        FONT_PAIRINGS.get((get_site_settings(db) or {}).get("font_pairing")))
    return newsletter.to_transactional_html(text_body, site_title, line, look), text_body


def _send_order_email(db, order_id):
    """Emails the buyer their way back in. Best-effort by design: an
    order is already paid and recorded by the time this runs, so a mail
    server having a bad afternoon must never turn a completed purchase
    into an error. A failure is logged, and the owner can resend."""
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order or not order["customer_id"]:
        return False
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
    settings = get_email_settings(db)
    if not customer or not mailer.is_configured(settings):
        return False
    try:
        token, _ = commerce.get_or_create_token(db, customer["id"])
        db.commit()
        #  An emailed link has to work on a device that is not this one.
        #  url_for(_external=True) builds from whichever host THIS request
        #  arrived on — so a resend triggered from localhost bakes
        #  "localhost" into a link the buyer opens on their phone. The
        #  configured site address wins whenever it is set.
        url = _public_url("public.my_account", token=token)
        site = (get_site_settings(db) or {}).get("site_title") or "our website"
        subject = f"Your order from {site}"
        html, text = _dressed(db, commerce.order_email_body(db, order, url, site), subject)
        mailer.send_html(settings, customer["email"], subject, html, text, from_name=site)
        #  And tell the owner. Separate message, separate address: the
        #  buyer's email is their way back in and says nothing about what
        #  needs doing; this one is a job list and carries no link.
        #  Wrapped on its own so a failure here cannot cost the buyer
        #  theirs, which has already been sent by this point.
        try:
            seller = (settings.get("to_email") or settings.get("from_email") or "").strip()
            #  Sent even when the owner IS the buyer. The two messages say
            #  different things -- one is a way back to what was bought,
            #  the other is a job list -- so suppressing the second
            #  because the addresses match hides the sale notice from
            #  every owner testing their own shop, which is everyone on
            #  their first day.
            if seller:
                subject = ("Sale: %.2f %s — %s"
                           % ((order["amount_total"] or 0) / 100,
                              (order["currency"] or "").upper(), site))
                html, text = _dressed(db, commerce.sale_notice_body(db, order, site), subject)
                mailer.send_html(settings, seller, subject, html, text, from_name=site)
        except Exception as e:  # noqa: BLE001
            current_app.logger.warning("Sale notice could not be sent: %s", e)
        return True
    except Exception as e:  # noqa: BLE001 - see docstring: never fail the order
        current_app.logger.warning("Order email could not be sent: %s", e)
        return False


@bp.route("/my/<token>")
def my_account(token):
    """Everything a buyer has bought, reached by a link from their email.

    No password, no account, no session cookie — the token in the URL is
    the whole credential, which is why it is stored only as a hash and
    expires. This is what "guest checkout" has to mean for anything that
    is not consumed the instant it is paid for.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return render_template("public/my_account.html", customer=None, token=token), 404
    db.commit()
    #  A buyer who locked this page has to say so before it opens. The
    #  link alone is still what identifies them; this is the second thing.
    if customer["page_password_hash"] and not _page_unlocked(customer["id"]):
        return render_template("public/my_account_locked.html",
                               token=token, error=request.args.get("error")), 200
    calcom_ready = integrations.is_configured(db, "calcom")
    #  A session that leaves the calendar — cancelled, or the entry
    #  deleted outright — has to come back to the person who paid for it.
    #  Cal.com can push a cancellation, but only to a publicly reachable
    #  address, which this site may not have, and it cannot report a
    #  booking that no longer exists at all. So we ask, here, at the one
    #  moment it actually matters to the person looking.
    if calcom_ready and commerce.bookings_for(db, customer["id"]):
        commerce.sync_bookings(db, integrations)
        db.commit()
    entitlements = commerce.entitlements_for(db, customer["id"])
    credits = [e for e in entitlements if e["kind"] == commerce.KIND_CREDIT and e["used"] < e["granted"]]
    tz = request.args.get("tz") or "UTC"
    calendar, slot_error, booking_for = ([], None, None)
    if credits and calcom_ready:
        #  Only the first unspent credit's calendar is offered. Someone
        #  with sessions against two different meetings picks one at a
        #  time, which keeps the page a single clear question rather than
        #  a matrix.
        booking_for = credits[0]
        today = datetime.date.today()
        slots, slot_error = integrations.calcom_slots(
            db, booking_for["ref"], today.isoformat(),
            (today + datetime.timedelta(days=BOOKING_WINDOW_DAYS)).isoformat(), tz,
        )
        calendar = integrations.slots_calendar(slots, today, BOOKING_WINDOW_DAYS)
    #  Booking is never one click. The confirm step exists because a
    #  mis-click here spends something the visitor paid for — they get to
    #  read the day and time back before anything is taken.
    #  A booked time only offers Cancel while it is still ahead. Past
    #  ones stay on the page as history — a receipt of what was used.
    upcoming, past = [], []
    for row in commerce.bookings_for(db, customer["id"]):
        item = {
            "uid": row["provider_uid"],
            "when": integrations.describe_slot(row["starts_at"], row["timezone"]),
        }
        (upcoming if commerce.starts_in_future(row["starts_at"]) else past).append(item)

    confirm = (request.args.get("confirm") or "").strip() or None
    #  Same reasoning in reverse: giving up a booked time is also worth
    #  reading back before it happens.
    cancel_uid = (request.args.get("cancel") or "").strip()
    cancelling = None
    if cancel_uid:
        cancelling = db.execute(
            "SELECT * FROM bookings WHERE provider_uid = ? AND customer_id = ? AND status != 'cancelled'",
            (cancel_uid, customer["id"]),
        ).fetchone()
    return render_template(
        "public/my_account.html",
        customer=customer,
        token=token,
        entitlements=entitlements,
        orders=commerce.orders_for(db, customer["id"]),
        credits=sum(e["granted"] - e["used"] for e in entitlements if e["kind"] == "credit"),
        calendar=calendar,
        weekdays=integrations.WEEKDAY_LABELS,
        slot_error=slot_error,
        booking_for=booking_for,
        bookings=upcoming,
        past_bookings=past,
        tz=tz,
        confirm=confirm,
        cancelling=cancelling,
        confirm_label=integrations.describe_slot(confirm, tz) if confirm else None,
        booked=request.args.get("booked"),
        booked_label=integrations.describe_slot(request.args.get("booked"), tz) if request.args.get("booked") else None,
        booking_error=request.args.get("error"),
        note=request.args.get("note"),
        cancelled=request.args.get("cancelled"),
    )


UNLOCK_ATTEMPT_LIMIT = 10
UNLOCK_WINDOW_MINUTES = 15


def _client_ip():
    #  ProxyFix has already rewritten this from X-Forwarded-For when a
    #  proxy in front is trusted, so it is the real caller either way.
    return request.remote_addr or "unknown"


def record_failed_unlock(db, ip):
    db.execute("INSERT INTO login_attempts (ip, kind) VALUES (?, 'page')", (ip,))
    db.execute("DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-1 hour')")
    db.commit()


def unlock_rate_limited(db, ip):
    row = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND kind = 'page' "
        "AND attempted_at > datetime('now', ?)",
        (ip, f"-{UNLOCK_WINDOW_MINUTES} minutes"),
    ).fetchone()
    return row["n"] >= UNLOCK_ATTEMPT_LIMIT


def _page_unlocked(customer_id):
    """Whether this browser has already answered this page's password.

    Kept in the session rather than in another token, so it lasts as long
    as the browser is open and travels nowhere near the URL -- a password
    in a link would be worse than no password at all.
    """
    return customer_id in (session.get("unlocked_pages") or [])


def _remember_unlocked(customer_id):
    open_ones = list(session.get("unlocked_pages") or [])
    if customer_id not in open_ones:
        open_ones.append(customer_id)
        session["unlocked_pages"] = open_ones


@bp.route("/my/<token>/lock", methods=["POST"])
def my_account_lock(token):
    """Sets, changes or clears the buyer's own password on their page.

    Offered once, on a page they reached with a link that is already a
    credential -- so this is opt-in hardening, not a sign-up. Changing or
    clearing it requires the page to be open, which means the current
    password has already been given.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return redirect(url_for("public.home"))
    if customer["page_password_hash"] and not _page_unlocked(customer["id"]):
        return redirect(url_for("public.my_account", token=token))
    if request.form.get("decline"):
        commerce.decline_page_password(db, customer["id"])
        db.commit()
        return redirect(url_for("public.my_account", token=token))
    password = request.form.get("password") or ""
    if password and len(password) < 8:
        return redirect(url_for("public.my_account", token=token,
                                error="Please use at least 8 characters."))
    commerce.set_page_password(db, customer["id"], password)
    db.commit()
    _remember_unlocked(customer["id"])
    return redirect(url_for("public.my_account", token=token,
                            note="Locked. You'll be asked for this next time."
                            if password else "The password has been removed."))


@bp.route("/my/<token>/unlock", methods=["POST"])
def my_account_unlock(token):
    """Answers the password on a locked page.

    Rate limited by address, like the admin login: guessing this needs the
    link as well, which is 32 bytes of randomness, but a lock that never
    tires is not much of one.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return redirect(url_for("public.home"))
    if unlock_rate_limited(db, _client_ip()):
        return redirect(url_for("public.my_account", token=token,
                                error="Too many tries. Wait a few minutes and try again."))
    if commerce.page_password_ok(db, customer["id"], request.form.get("password")):
        _remember_unlocked(customer["id"])
        return redirect(url_for("public.my_account", token=token))
    record_failed_unlock(db, _client_ip())
    return redirect(url_for("public.my_account", token=token,
                            error="That password didn't match."))


@bp.route("/my/<token>/book", methods=["POST"])
def my_account_book(token):
    """Spends one session and books it.

    The order matters: the credit is checked and taken FIRST, then the
    booking is made, and the credit is handed back if Cal.com refuses.
    Booking first would leave a window where two tabs could each book
    against the same last session.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return redirect(url_for("public.my_account", token=token))
    start = (request.form.get("start") or "").strip()
    tz = (request.form.get("tz") or "UTC").strip()
    entitlement_id = request.form.get("entitlement_id", type=int)
    if not start or not entitlement_id:
        return redirect(url_for("public.my_account", token=token, error="Pick a time first."))

    taken = commerce.spend_credit(db, entitlement_id, customer["id"])
    if not taken:
        db.commit()
        return redirect(url_for("public.my_account", token=token,
                                error="Those sessions are all used up."))
    db.commit()

    entitlement = db.execute("SELECT * FROM entitlements WHERE id = ?", (entitlement_id,)).fetchone()
    booking, error = integrations.calcom_create_booking(
        db, entitlement["ref"], start, customer["name"], customer["email"], tz
    )
    if error:
        commerce.refund_credit(db, entitlement_id)
        db.commit()
        current_app.logger.warning("Booking failed, session returned: %s", error)
        return redirect(url_for("public.my_account", token=token,
                                error="That time was just taken. Please pick another."))

    #  The booking's own id is the only thing that can later tie a
    #  cancellation back to the session it should return. Discarding it
    #  here would mean a cancelled meeting leaves the buyer permanently
    #  one session short.
    payload = (booking or {}).get("data", booking) or {}
    uid = payload.get("uid") or payload.get("id")
    if uid:
        commerce.record_booking(db, str(uid), customer["id"], entitlement_id,
                                entitlement["ref"], start, tz)
        db.commit()
    return redirect(url_for("public.my_account", token=token, booked=start, tz=tz))





@bp.route("/my/<token>/cancel", methods=["POST"])
def my_account_cancel(token):
    """Cancels a booking the buyer made, and hands the session back.

    This exists because the cancellation has to reach Cal.com. Deleting
    the meeting from whatever calendar it was mirrored into does not — the
    sync writes one way — so a buyer who tidies it out of their own
    calendar would lose the session AND still have the seller expecting
    them.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return redirect(url_for("public.my_account", token=token))
    uid = (request.form.get("uid") or "").strip()
    ok, error = commerce.cancel_booking(db, integrations, uid, customer["id"],
                                        reason="Cancelled by the customer")
    db.commit()
    if not ok:
        current_app.logger.warning("Cancel failed: %s", error)
        return redirect(url_for("public.my_account", token=token,
                                error="We couldn't cancel that just now. Please get in touch."))
    return redirect(url_for("public.my_account", token=token, cancelled=1))


@bp.route("/my/<token>/download/<int:entitlement_id>")
def my_account_download(token, entitlement_id):
    """Streams a paid file, once the entitlement has been checked and spent.

    The file has no URL of its own — this route IS the only way to it, so
    every copy handed out has been counted against something somebody
    bought. Sent as an attachment with sniffing turned off, so nothing
    here can be coaxed into rendering as a page on this origin.
    """
    db = get_db()
    customer = commerce.customer_for_token(db, token)
    if not customer:
        return redirect(url_for("public.my_account", token=token))
    row, error = downloads.claim(db, entitlement_id, customer["id"])
    db.commit()
    if error:
        return redirect(url_for("public.my_account", token=token, error=error))
    response = send_file(
        downloads.path_for(row),
        as_attachment=True,
        download_name=row["original_name"],
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/newsletters")
def newsletter_archive():
    """Every newsletter that actually went out, oldest habits included.

    Only sent ones: a draft sitting in the admin is not something a
    visitor should stumble into, and "we send these, here they are" is a
    better argument for signing up than any amount of persuading.
    """
    db = get_db()
    #  Pages and posts alike: being SENT is what makes an issue an issue,
    #  not what it was written on. The URL is built here because that is
    #  the routing layer's job, and the query is in the service because
    #  "what can still be read" is not.
    issues = [
        {"title": row["title"], "blurb": row["blurb"], "first_sent": row["first_sent"],
         "url": (url_for("public.blog_post", slug=row["blog_slug"], post_slug=row["post_slug"])
                 if row["target_kind"] == "post"
                 else url_for("public.page", slug=row["page_slug"]))}
        for row in newsletter.sent_issues(db)
    ]
    return render_template("public/newsletter_archive.html", issues=issues)


#  What a sign-up can say, in one place. These words were written into
#  public/page.html and had to be repeated by anything else that answers
#  the same form -- so the page and the fetch below would have drifted the
#  first time one of them was reworded. `ok` is whether it went well, which
#  is all the styling needs to know.
SIGNUP_MESSAGES = {
    "check": ("Nearly done — open the email we've just sent and follow the link in it. "
              "You won't hear from us again until you do.", True),
    "already": ("You're already on the list.", True),
    "bad": ("That doesn't look like an email address — have another go.", False),
    "unavailable": ("Sign-ups aren't working just now, so nothing was saved. "
                    "Please try again later.", False),
    "consent": ("Tick the box to say yes, and we'll sign you up.", False),
    "ok": ("Thank you — you're on the list.", True),
}


@bp.app_context_processor
def _signup_message_words():
    return {"signup_messages": SIGNUP_MESSAGES}


def _signup_answer(back, key):
    """The same answer, in whichever form the asker can use.

    The form posts itself with fetch when the browser can, so the reply
    lands in the box the person is looking at rather than throwing the
    whole page away and putting a line at the top of it -- which, on a
    sign-up near the foot of a long page, meant a reload, a jump to the
    top, and no visible sign that anything had happened. Without script
    it still redirects, exactly as before.
    """
    message, ok = SIGNUP_MESSAGES[key]
    if request.headers.get("X-Requested-With") == "cms-subscribe":
        return jsonify({"status": key, "message": message, "ok": ok})
    return redirect(f"{back}?subscribed={key}")


@bp.route("/subscribe", methods=["POST"])
def subscribe():
    """Takes an email address for the Email sign-up block.

    Sending the form is the consent. Its only purpose is subscribing and
    the button says Sign up, so a separate tick box was asking for the
    same act a second time. What consent actually needs is that the person
    was told what they were agreeing to, and that it can be evidenced:
    the wording is shown on the form and stored with the row rather than
    looked up later, because the block will be edited and the promise made
    to somebody last spring is the one that has to be evidenced.
    """
    db = get_db()
    back = request.referrer or url_for("public.home")
    #  Sending this form IS the consent: its only purpose is subscribing,
    #  and the button says so. There was a required tick box asking the
    #  same person to agree to the thing they had just pressed a button to
    #  do; it is gone, and what matters is kept -- the wording is shown on
    #  the form and stored with the row below.
    #
    #  A page saved before that still renders the box, so if the field is
    #  SENT it still has to be true. Absent means the new markup; false
    #  means somebody posted an old form around its own required
    #  attribute.
    if "consent" in request.form and not request.form.get("consent"):
        return _signup_answer(back, "consent")

    #  Same ledger and the same reasoning as the contact form: one
    #  visitor should not be able to fill the list with rubbish.
    ip = "subscribe:" + (request.remote_addr or "unknown")
    recent = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? "
        "AND attempted_at > datetime('now', '-1 hour')", (ip,)
    ).fetchone()["n"]
    if recent >= 5:
        #  Answered as though it worked. Telling somebody hammering the
        #  form that they have been stopped only tells them how to stop
        #  being stopped.
        return _signup_answer(back, "check")
    db.execute("INSERT INTO login_attempts (ip) VALUES (?)", (ip,))

    consent_text = (request.form.get("consent_text") or "").strip() or \
        "Agreed to receive occasional updates."
    status, confirm_token = subscribers.add(
        db, request.form.get("email"), consent_text,
        source=(request.referrer or ""), ip=request.remote_addr,
    )
    if status == "refused":
        db.commit()
        return _signup_answer(back, "bad")
    if status == "already":
        db.commit()
        return _signup_answer(back, "already")

    #  Nothing is on the list until this mail is answered. Switzerland
    #  wants the person who receives advertising to have asked for it, and
    #  the way that is shown is double opt-in: one mail, one link, and no
    #  other message ever sent to an address that has not followed it.
    email_settings = get_email_settings(db)
    site_settings = get_site_settings(db) or {}
    site_title = site_settings.get("site_title") or "this site"
    line, has_address = newsletter.sender_line(legal.settings_for(db), site_title)
    if not mailer.is_configured(email_settings) or not has_address:
        #  Said plainly rather than pretending. Without a way to send the
        #  mail there is no way to confirm, so the address is not on any
        #  list -- and the owner needs to know, because from a visitor's
        #  side this looks like the site swallowing their sign-up.
        db.rollback()
        current_app.logger.warning(
            "Sign-up from %s could not be confirmed: %s",
            request.remote_addr,
            "email is not set up" if not mailer.is_configured(email_settings)
            else "no postal address on the Legal pages screen",
        )
        return _signup_answer(back, "unavailable")

    confirm_url = site.absolute(db, url_for("public.subscribe_confirm", token=confirm_token))
    try:
        subject = f"Confirm your subscription to {site_title}"
        #  Not a list message yet -- they have not confirmed -- so it
        #  carries no unsubscribe, which is also why it is dressed with
        #  the transactional shell rather than the newsletter's.
        html, text = _dressed(db, render_template(
            "emails/confirm_subscription.txt", site_title=site_title,
            confirm_url=confirm_url, consent_text=consent_text, sender_line=line), subject)
        mailer.send_html(email_settings, request.form.get("email"), subject, html, text,
                         from_name=site_title)
    except Exception:  # noqa: BLE001 - a bad address must not 500 the page
        db.rollback()
        current_app.logger.exception("Could not send the confirmation email")
        return _signup_answer(back, "unavailable")
    #  Stamped after the server took it, so the record says what happened
    #  rather than what was attempted.
    subscribers.mark_confirmation_sent(db, request.form.get("email"))
    db.commit()
    return _signup_answer(back, "check")


@bp.route("/subscribe/confirm/<token>")
def subscribe_confirm(token):
    """The link in that mail. Following it is what puts somebody on the list.

    A GET, because it is a link in an email and nothing else can be. It is
    idempotent -- following it twice, or a mail client fetching it before a
    person sees it, must not read as a failure to somebody who did what was
    asked.
    """
    db = get_db()
    row = subscribers.confirm(db, token, ip=request.remote_addr)
    db.commit()
    #  `row` is how the row looked BEFORE this request, so a blank
    #  confirmed_at means this click is the one that did it -- and the
    #  welcome goes out once, not every time somebody reopens the link.
    if row is not None and not row["confirmed_at"]:
        _send_welcome(db, row)
    return render_template("public/subscribed.html", ok=row is not None,
                           email=(row["email"] if row else ""))


def _send_welcome(db, row):
    """The first real message: you are on the list, and here is the way off.

    Every message after subscription has to carry an unsubscribe link, and
    this is the first message after subscription. It is also the only one
    the site sends by itself, so without it somebody could confirm, hear
    nothing for six months, and have been given no way out in the
    meantime.

    A failure here is logged and swallowed. The person did what was asked
    and is on the list; showing them an error because the site could not
    manage a courtesy would be answering their success with our problem.
    """
    email_settings = get_email_settings(db)
    if not mailer.is_configured(email_settings):
        return
    site_title = (get_site_settings(db) or {}).get("site_title") or "this site"
    sender_line, has_address = newsletter.sender_line(legal.settings_for(db), site_title)
    if not has_address:
        return
    unsubscribe_url = site.absolute(db, url_for("public.unsubscribe", token=row["token"]))
    try:
        subject = f"You're subscribed to {site_title}"
        #  This one IS a list message, so the unsubscribe link stays --
        #  it is already in the words, and the headers go with it. The
        #  shell only dresses what is written.
        html, text = _dressed(db, render_template(
            "emails/subscribed.txt", site_title=site_title,
            consent_text=row["consent_text"], unsubscribe_url=unsubscribe_url,
            sender_line=sender_line), subject)
        mailer.send_html(email_settings, row["email"], subject, html, text,
                         from_name=site_title,
                         headers=unsubscribe_headers(unsubscribe_url))
    except Exception:  # noqa: BLE001 - they are subscribed either way
        current_app.logger.exception("Could not send the welcome email")


def unsubscribe_headers(unsubscribe_url):
    """What a mail program needs to offer its own unsubscribe button.

    List-Unsubscribe-Post turns that button into one press instead of a
    trip to a web page, which is why the route below also answers POST.
    Worth doing for its own sake, and worth doing because the alternative
    somebody reaches for is the spam button, which costs the sender far
    more than an unsubscribe does.
    """
    return {"List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    """No login, no password: the link in the email is the whole thing.

    Which is why the token is random rather than made from the address —
    a guessable one would let anybody unsubscribe anybody.
    """
    db = get_db()
    ok = subscribers.unsubscribe(db, token)
    db.commit()
    return render_template("public/unsubscribed.html", ok=ok)


@bp.route("/cart")
def cart():
    """The basket. Prices are read from Stripe on every view, so nothing
    a visitor can edit decides what anything costs."""
    db = get_db()
    lines, currency, subtotal, problems = cart_service.lines(db, integrations)
    shipping = cart_service.shipping_for(db, integrations, lines, subtotal, currency)
    return render_template(
        "public/cart.html",
        lines=lines,
        currency=currency,
        subtotal=subtotal,
        shipping=shipping,
        total=subtotal + (shipping["amount"] if shipping else 0),
        problems=problems,
        stripe_ready=integrations.is_configured(db, "stripe"),
    )


@bp.route("/cart/add", methods=["POST"])
def cart_add():
    """Puts something in the basket and leaves the shopper where they are.

    It used to go straight to the basket "the way a market stall works".
    On a page of four products that means being taken away from the shop
    after each one and having to find your way back, which is how a
    second purchase stops happening.

    So: add it, say so, stay put. The basket is a link in the header with
    a count on it, and it is there whenever they want it.

    Answers JSON when asked, so the page can update its count without a
    reload, and redirects back to where the shopper was when it is not --
    the form works either way, and the header count is honest feedback
    even with no script running.
    """
    db = get_db()
    wants_json = "application/json" in (request.headers.get("Accept") or "")
    back = request.referrer or url_for("public.home")
    price_id = (request.form.get("price_id") or "").strip()
    if not price_id:
        return jsonify({"ok": False, "message": "Nothing to add."}) if wants_json else redirect(back)

    left = cart_service.stock_for(db, price_id)
    if left == 0:
        #  A public page renders no flashes, so this has to travel in the
        #  answer itself or the shopper is told nothing at all.
        if wants_json:
            return jsonify({"ok": False, "message": "Sorry — that's just sold out."})
        return redirect(back)

    cart_service.add(price_id, request.form.get("quantity", type=int) or 1)
    if wants_json:
        return jsonify({"ok": True, "count": cart_service.count(),
                        "message": "Added to your basket"})
    return redirect(back)


@bp.route("/cart/update", methods=["POST"])
def cart_update():
    price_id = (request.form.get("price_id") or "").strip()
    if price_id:
        cart_service.set_quantity(price_id, request.form.get("quantity", type=int) or 0)
    return redirect(url_for("public.cart"))


@bp.route("/checkout", methods=["POST"])
def checkout():
    """Hands the buyer to Stripe's own checkout page.

    The form carries only price ids — never an amount, because an amount
    in the page is a number a visitor can edit before it is charged.
    Stripe is the sole authority on what anything costs.

    One route for both ways of buying: a Buy button posts a single price,
    the basket posts nothing and is read from the session. Stock is
    checked again here even though it was checked going in, because a
    basket can sit open for a day.
    """
    db = get_db()
    if not integrations.is_configured(db, "stripe"):
        flash("This site can't take payments yet.", "error")
        return redirect(request.referrer or url_for("public.home"))

    price_id = (request.form.get("price_id") or "").strip()
    shipping = None
    if price_id:
        items = [(price_id, request.form.get("quantity", type=int) or 1)]
    else:
        lines, currency, subtotal, problems = cart_service.lines(db, integrations)
        if problems:
            for problem in problems:
                flash(problem, "error")
            return redirect(url_for("public.cart"))
        if not lines:
            return redirect(url_for("public.cart"))
        items = [(line["price_id"], line["quantity"]) for line in lines]
        shipping = cart_service.shipping_for(db, integrations, lines, subtotal, currency)

    url, error = integrations.stripe_checkout_session(
        db,
        items,
        #  Where Stripe sends the buyer back to. Their browser follows
        #  this from Stripe's own domain, so it has to be an address that
        #  works from outside — not whichever host this request came in on.
        success_url=_public_url("public.checkout_thanks") + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=_public_url("public.cart" if not price_id else "public.home"),
        shipping=shipping,
    )
    if error:
        current_app.logger.warning("Checkout could not start: %s", error)
        flash("Sorry — checkout couldn't start. Please try again.", "error")
        return redirect(request.referrer or url_for("public.home"))
    return redirect(url, code=303)


@bp.route("/checkout/thanks")
def checkout_thanks():
    """Reports what the webhook recorded — it never records anything
    itself. A visitor can reach this page without paying, so the only
    honest thing it can do is look up the session and say what Stripe
    says, and admit when confirmation hasn't arrived yet."""
    db = get_db()
    session_id = (request.args.get("session_id") or "").strip()
    state = {"paid": False, "pending": False, "email": None, "order": None,
             "link": None, "credits": 0, "downloads": 0}
    if session_id and integrations.is_configured(db, "stripe"):
        data, error = integrations.stripe_call(db, f"/checkout/sessions/{session_id}")
        if not error and data:
            state["paid"] = data.get("payment_status") == "paid"
            if state["paid"]:
                #  Emptied only once Stripe says it was paid for — not
                #  when checkout started, because a visitor who backs out
                #  of the payment page should find their basket as they
                #  left it.
                cart_service.clear()
            state["email"] = (data.get("customer_details") or {}).get("email")
            order = commerce.order_by_ref(db, session_id)
            if state["paid"] and order is None:
                #  No webhook has recorded this yet — possibly because
                #  none is configured at all (no public address in
                #  development). The buyer is standing right here with a
                #  paid session, so record it from what Stripe itself
                #  just told us. record_checkout is keyed on the session
                #  id, so a webhook arriving later changes nothing.
                items, items_error = integrations.stripe_call(
                    db, f"/checkout/sessions/{session_id}/line_items?limit=50"
                )
                new_order_id, created = commerce.record_checkout(
                    db, data, (items or {}).get("data", []) if not items_error else [],
                    credit_expiry_at=_credit_expiry_at(db),
                )
                db.commit()
                if created:
                    _send_order_email(db, new_order_id)
                order = commerce.order_by_ref(db, session_id)
            state["order"] = order["id"] if order else None
            #  Give the buyer their way in right here, not only by email.
            #  A mistyped address, a mail server having a bad day, or a
            #  spam folder would otherwise leave someone who has just paid
            #  with no route to what they bought.
            if order and order["customer_id"]:
                token, _ = commerce.get_or_create_token(db, order["customer_id"])
                db.commit()
                ents = commerce.entitlements_for(db, order["customer_id"])
                state["link"] = _public_url("public.my_account", token=token)
                state["credits"] = sum(
                    e["granted"] - e["used"] for e in ents if e["kind"] == commerce.KIND_CREDIT
                )
                state["downloads"] = sum(
                    1 for e in ents if e["kind"] == commerce.KIND_DOWNLOAD and e["used"] < e["granted"]
                )
            #  Paid on Stripe's side but no order here yet means the
            #  webhook is still in flight — normal for a second or two,
            #  and worth saying rather than showing a bare success.
            state["pending"] = state["paid"] and order is None
    return render_template("public/checkout_thanks.html", state=state, session_id=session_id)


@bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Where an order actually becomes real.

    Deliberately not behind @login_required (Stripe has no session) and
    exempt from the Origin/Referer CSRF check (Stripe is not a browser and
    sends neither) — it proves itself with a signature instead, verified
    before any field of the payload is trusted. See csrf.py's
    SIGNATURE_VERIFIED_ENDPOINTS.

    Always answers 200 once a payload is verified, even for events it does
    not act on: a non-2xx makes Stripe retry, and retrying an event we
    understood but ignored achieves nothing but noise.
    """
    db = get_db()
    secret = integrations.get_provider_settings(db, "stripe").get("webhook_secret")
    try:
        event = commerce.verify_stripe_signature(
            request.get_data(), request.headers.get("Stripe-Signature"), secret
        )
    except commerce.WebhookError as e:
        #  400, not 403: this is a malformed or unverifiable delivery, and
        #  Stripe's dashboard shows the reason back to the site owner.
        current_app.logger.warning("Stripe webhook rejected: %s", e)
        return jsonify({"error": str(e)}), 400

    event_id = event.get("id")
    event_type = event.get("type") or ""
    if commerce.already_processed(db, "stripe", event_id):
        return jsonify({"ok": True, "duplicate": True})

    obj = (event.get("data") or {}).get("object") or {}
    handled = None
    if event_type == "checkout.session.completed":
        line_items = _stripe_line_items(db, obj)
        expiry = _credit_expiry_at(db)
        order_id, created = commerce.record_checkout(db, obj, line_items, credit_expiry_at=expiry)
        if created:
            db.commit()
            _send_order_email(db, order_id)
        handled = f"order {order_id}" + ("" if created else " (already recorded)")
    elif event_type in ("charge.refunded", "checkout.session.async_payment_failed"):
        ref = obj.get("payment_intent") or obj.get("id")
        order = commerce.order_by_ref(db, ref) if ref else None
        if order:
            commerce.revoke_unused_for_order(db, order["id"])
            handled = f"order {order['id']} refunded"

    commerce.record_event(db, "stripe", event_id, event_type)
    db.commit()
    return jsonify({"ok": True, "handled": handled})


def _stripe_line_items(db, session):
    """What was bought. Checkout sessions do not include their line items
    unless asked, so they are fetched separately — and a failure here must
    not lose the order, only the detail of what it contained."""
    items = (session.get("line_items") or {}).get("data")
    if items:
        return items
    session_id = session.get("id")
    if not session_id:
        return []
    data, error = integrations.stripe_call(db, f"/checkout/sessions/{session_id}/line_items?limit=50")
    if error:
        current_app.logger.warning("Could not read line items for %s: %s", session_id, error)
        return []
    return data.get("data", [])


def _credit_expiry_at(db):
    """Session credits do not expire unless the owner turns it on, in
    which case the default term is twelve months."""
    row = db.execute("SELECT value FROM settings WHERE key = 'commerce_credit_expiry_months'").fetchone()
    months = int(row["value"]) if row and (row["value"] or "").isdigit() else 0
    if months <= 0:
        return None
    return (datetime.datetime.utcnow() + datetime.timedelta(days=30 * months)).strftime("%Y-%m-%d %H:%M:%S")


@bp.context_processor
def inject_layout_settings():
    return get_layout_settings(get_db())


@bp.route("/healthz")
def healthz():
    """Is this container actually able to serve? -- for Docker's own
    HEALTHCHECK, a load balancer, or an uptime monitor.

    It touches the database, because a process that is running and a site
    that works are different claims: the interesting failure is a data
    volume that did not mount, which a check on the port alone reports as
    healthy. Deliberately says nothing else -- no version, no counts, no
    settings -- since it answers to anyone who can reach the port.
    """
    try:
        get_db().execute("SELECT 1 FROM settings LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001 - the point is to answer, not to raise
        return Response("unhealthy\n", status=503, mimetype="text/plain")
    return Response("ok\n", status=200, mimetype="text/plain",
                    headers={"Cache-Control": "no-store"})


@bp.context_processor
def inject_site_settings():
    return {"site_settings": get_site_settings(get_db())}


@bp.context_processor
def inject_nav_layout():
    return {"nav_layout": get_nav_layout(get_db())}


def _pickable_images(template):
    """Everything an owner can put on a page.

    Their own uploads first — those are theirs, and newest-first is how
    they were left — then the pictures of every INSTALLED template, not
    only the active one. A site that has been through three templates has
    the pictures of all three sitting on disk and served; offering just
    the current one's meant the picture already on a section could be
    missing from the list of pictures to choose, which reads as the list
    being broken. The active template's come first among those, since
    they are the ones that match what is on screen.
    """
    items = [{"url": m["url"], "name": m["filename"]} for m in _list_media(image_only=True)]
    themes = os.path.join(current_app.static_folder, "themes")
    if not os.path.isdir(themes):
        return items
    active = (template["slug"] if template else "") or ""
    slugs = sorted(os.listdir(themes), key=lambda d: (d != active, d))
    for slug in slugs:
        folder = os.path.join(themes, slug, "media")
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder)):
            if os.path.splitext(filename)[1].lower() in MEDIA_IMAGE_EXTS:
                items.append({"url": f"/static/themes/{slug}/media/{filename}",
                              "name": filename})
    return items


def _column(row, name, default=None):
    """A column that may not exist yet on an older row."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return default


def _active_template(db):
    tpl = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    if not tpl:
        tpl = db.execute("SELECT * FROM templates LIMIT 1").fetchone()
    return tpl


def _nav_pages(db):
    #  Every page a visitor can actually reach, newsletters included.
    #  They used to be excluded by their KIND, on the reasoning that a
    #  year of issues would fill the navigation -- but nothing has to be
    #  in the navigation to begin with: a Menu is a list somebody ticks,
    #  so an issue appears there only if it was chosen. What does belong
    #  here is the one question that decides whether a link can work at
    #  all, which is whether the page is on the site.
    return db.execute(
        "SELECT * FROM pages WHERE is_public = 1 ORDER BY nav_order, title"
    ).fetchall()


def _link_choices(nav_pages):
    """The pages a link field can point at, as {url, title}.

    Built here rather than in the template: working out that the home page
    is "/" and everything else is "/<slug>" is logic, and templates in
    this project hold structure only. It is also the same rule the Menu
    tool already follows, so a link picked here and a link picked there
    lead to the same place.
    """
    return [{"url": _page_href(p), "title": p["title"]} for p in nav_pages]


def _build_nav_html(nav_pages, editing=False):
    """
    Builds the site nav as an HTML string so the exact same markup can be
    dropped into both our own default header AND an imported theme's header
    (which only has a %%CMS_NAV%% text placeholder to substitute into).
    Pages are managed exclusively from the Dashboard now — this is a plain,
    read-only list of links even while editing; no add/delete controls here.
    """
    parts = []
    for p in nav_pages:
        href = url_for("public.home") if p["is_home"] else url_for("public.page", slug=p["slug"])
        label = html_escape(p["title"])
        parts.append(f'<a href="{href}">{label}</a>')
    return "\n".join(parts)


def _build_breadcrumb_html(page, current_title=None, current_url=None):
    """
    Home > ... > Current. Shown on every page, including Home itself (as a
    single, clickable "Home" self-link) — for consistency, since a
    breadcrumb block placed in the header is the same block on every page
    and shouldn't just vanish on one of them. Every entry is a clickable
    link, including the current page (a self-link) — some breadcrumb
    conventions leave the current page unlinked, but this site wants it
    clickable too. `page` is the trail's middle link; pass
    `current_title`/`current_url` when the actual current page is something
    below it — e.g. a blog post, where `page` is the blog listing and the
    post is the final entry, linking to itself. Without them, `page` is the
    final entry.
    """
    if not page:
        return ""
    home_url = url_for("public.home")
    if page["is_home"]:
        return f'<a href="{home_url}" class="cms-breadcrumb-current">Home</a>'
    page_url = url_for("public.page", slug=page["slug"])
    parts = [f'<a href="{home_url}">Home</a>']
    parts.append('<span class="cms-breadcrumb-sep">/</span>')
    parts.append(f'<a href="{page_url}" class="cms-breadcrumb-current">{html_escape(page["title"])}</a>')
    if current_title:
        parts.append('<span class="cms-breadcrumb-sep">/</span>')
        parts.append(f'<a href="{current_url}" class="cms-breadcrumb-current">{html_escape(current_title)}</a>')
    return "".join(parts)


def _apply_placeholders(html_text, nav_html, breadcrumb_html=""):
    if not html_text:
        return html_text
    html_text = html_text.replace("%%CMS_SITE_TITLE%%", html_escape(SITE_TITLE))
    html_text = html_text.replace("%%CMS_NAV%%", nav_html)
    html_text = html_text.replace("%%CMS_BREADCRUMB%%", breadcrumb_html)
    return html_text


PLACEHOLDER_RE = re.compile(r"%%CMS_[A-Z_]+%%")


def _zone_sections(db, template, zone, nav_html, breadcrumb_html="", section_type_labels=None):
    """Header/footer site chrome, unified into the exact same `sections`
    table and tool architecture body pages use (Divide, Rows, per-cell
    tools, all of it) — scoped by template_id+zone instead of page_id. Used
    to be a separate JSON-blob-on-the-template system (see git history);
    that's what the now-removed _chunk_list/chunk_* routes worked with."""
    if not template:
        return []
    rows = db.execute(
        "SELECT * FROM sections WHERE template_id = ? AND zone = ? ORDER BY position",
        (template["id"], zone),
    ).fetchall()
    return _prepare_sections(rows, section_type_labels, nav_html, breadcrumb_html)


@bp.route("/")
def home():
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE is_home = 1").fetchone()
    if not page:
        page = db.execute("SELECT * FROM pages ORDER BY nav_order LIMIT 1").fetchone()
    if not page:
        abort(404)
    return _render_page(db, page)


@bp.route("/page/<slug>")
def page_legacy_redirect(slug):
    """Old /page/<slug> links (bookmarks, anything indexed before human-
    readable URLs shipped) still resolve — 301 to the short canonical
    form at /<slug> rather than 404ing or serving duplicate content at
    two URLs (bad for SEO either way)."""
    return redirect(url_for("public.page", slug=slug), code=301)


@bp.route("/<slug>")
def page(slug):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
    if not page:
        abort(404)
    #  Not on the site means not on the site. The owner still sees it --
    #  they have to be able to write it -- and a signed-in admin looking
    #  at a private page is told so by the bar at the top rather than by
    #  the page pretending to be public.
    if not page["is_public"] and not session.get("user_id"):
        abort(404)
    if page["is_home"]:
        # The home page also has a real slug (e.g. "home"), but it's only
        # ever meant to live at "/" — without this, it'd be reachable at
        # both URLs with identical content, which is both confusing and
        # bad for SEO (split ranking signals, "duplicate content" flags).
        return redirect(url_for("public.home"), code=301)
    return _render_page(db, page)


@bp.route("/contact/<slug>/submit", methods=["POST"])
def contact_submit(slug):
    """Receives a message from a Contact Form tool.

    Addressed by the page the form was on rather than by a kind of page:
    the form is a tool now, so it can sit on any page, on more than one,
    or beside other things on the same one. The slug is only used to send
    the sender back where they came from.
    """
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
    if not page:
        abort(404)
    #  The page has to actually carry a form, or this is an open endpoint
    #  that any address on the site could be used to hammer.
    has_form = db.execute(
        "SELECT 1 FROM sections WHERE page_id = ? AND content LIKE '%cms-contact-form-tool%'",
        (page["id"],),
    ).fetchone()
    if not has_form:
        abort(404)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()
    back_url = url_for("public.home") if page["is_home"] else url_for("public.page", slug=slug)
    if not (name and email and message):
        return redirect(f"{back_url}?error=1")
    ok, reason = captcha.verify(
        request.form.get("captcha_token"),
        request.form.get("captcha_answer"),
        request.form.get(captcha.HONEYPOT_FIELD),
    )
    if not ok:
        current_app.logger.info("Contact form rejected: %s", reason)
        #  A person who got the sum wrong is told so and can try again.
        #  Everything else is a bot, and is thanked and ignored — telling
        #  it which trap it fell into is how it learns to avoid the trap.
        if reason == "wrong answer":
            return redirect(f"{back_url}?again=1")
        return redirect(f"{back_url}?sent=1")

    settings = get_email_settings(db)
    if not mailer.is_configured(settings):
        return redirect(f"{back_url}?error=1")
    #  Nothing stopped one visitor sending a thousand messages, and every
    #  one of them is a real email out of the owner's own mailbox — the
    #  cost of that is the mail account being suspended for spam, which
    #  takes order confirmations down with it. Same ledger the login form
    #  uses, tagged so the two cannot be confused for each other.
    ip = "contact:" + (request.remote_addr or "unknown")
    recent = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? "
        "AND attempted_at > datetime('now', '-1 hour')", (ip,)
    ).fetchone()["n"]
    if recent >= 5:
        #  Deliberately indistinguishable from success: telling a spammer
        #  which message got through is telling them how to tune the next
        #  run, and a real person who sent two messages in a hurry should
        #  not be made to feel accused.
        return redirect(f"{back_url}?sent=1")
    db.execute("INSERT INTO login_attempts (ip) VALUES (?)", (ip,))
    db.commit()

    try:
        mailer.send_contact_message(settings, name, email, message)
    except Exception:
        return redirect(f"{back_url}?error=1")
    return redirect(f"{back_url}?sent=1")


def _page_showing_blog(db, blog_id):
    """A page with a Blog tool pointed at this blog, if any.

    A post belongs to a blog, not to a page, so it needs somewhere to
    borrow a layout and a way back from. Whichever page shows the blog is
    the honest answer, and if two do, the first in navigation order is as
    good a choice as any. A blog nobody has put on a page yet still has
    readable posts — they fall back to the home page's layout rather than
    becoming unreachable, which is the point of separating the two.
    """
    row = db.execute(
        "SELECT p.* FROM sections s JOIN pages p ON p.id = s.page_id "
        "WHERE s.content LIKE ? ORDER BY p.nav_order, p.id LIMIT 1",
        (f'%data-blog-id="{int(blog_id)}"%',),
    ).fetchone()
    if row:
        return row
    return (db.execute("SELECT * FROM pages WHERE is_home = 1").fetchone()
            or db.execute("SELECT * FROM pages ORDER BY nav_order LIMIT 1").fetchone())


@bp.route("/blog/<slug>/<post_slug>")
def blog_post(slug, post_slug):
    db = get_db()
    #  Addressed by the blog's own slug, so a post keeps its URL however
    #  the site is rearranged around it — including being shown on a
    #  different page, on several, or on none.
    blog = blog_service.get_blog_by_slug(db, slug)
    if not blog:
        abort(404)
    post = db.execute(
        "SELECT * FROM blog_posts WHERE blog_id = ? AND slug = ?", (blog["id"], post_slug)
    ).fetchone()
    if not post:
        abort(404)
    page = _page_showing_blog(db, blog["id"])
    if not page:
        abort(404)
    logged_in = bool(session.get("user_id"))
    if not post["published_at"] and not logged_in:
        abort(404)
    #  Rendered through the ordinary page shell, with the post standing in
    #  for that page's own sections. Everything around it — header,
    #  sidebars, footer — is then exactly what a visitor sees elsewhere on
    #  the site, rather than a second rendering that has to be kept in step.
    return _render_page(db, page, post=post,
                        post_content=blog_service.post_html(post["content"]))


def _text_to_html(content):
    """Kept as the name this module already used; the work is in the blog
    service now, because the newsletter needs the same answer and one
    route may not reach into another."""
    return blog_service.post_html(content)


def _format_file_size(num_bytes):
    if not num_bytes:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


#  Both the Media Player tool and the Video Gallery tool turn a pasted
#  link into a video id; the one implementation lives in the service
#  layer so the gallery builder can share it (see services/sections.py).
_youtube_id = youtube_id


#  Marker CSS class in the section's own content -> a more specific label
#  than the generic "HTML / Embed" every BLOCK_LIBRARY/tool-built 'html'
#  section otherwise shares — checked in order, first match wins, so it
#  is clear at a glance which tool actually built a given section.
#  The declared blocks name themselves, so the tool menu and the editor
#  cannot drift apart: a Pricing section that announced itself as
#  "HTML / Embed" told the one person who most needed to know otherwise —
#  somebody who will never write HTML — that this was an embed and not
#  theirs to edit.
#  Every section type's own display name, once. A cell needs the same
#  answer a section gets (see _normalize_column_cell), and the request
#  path already builds this dict per render to pass down as an argument.
SECTION_TYPE_LABELS = dict(SECTION_TYPES)

_BLOCK_LABEL_MARKERS = tuple(
    (f"cms-block-{key}", spec["name"]) for key, spec in blocks.BLOCKS.items()
)

HTML_SECTION_LABEL_MARKERS = _BLOCK_LABEL_MARKERS + (
    #  cms-buy-style-, not cms-buy: the shorter string is a substring of
    #  cms-buy-btn, which other tools' markup carried -- an Email sign-up
    #  rendered one, and pages saved before that was fixed still do. It
    #  was only the block markers being tested FIRST that stopped a
    #  newsletter announcing itself as a Buy Button. This marker is
    #  written by build_buy_button and by nothing else.
    ("cms-buy-style-", "Buy Button"),
    #  Order matters: a reader's markup contains "cms-faq" too, so the
    #  more specific marker has to be tested first or every reader would
    #  announce itself as FAQ Content.
    ("cms-faq-mirror", "FAQ Reader"),
    ("cms-search-tool", "Search"),
    ("cms-blog", "Blog"),
    ("cms-basket", "Basket"),
    ("cms-contact-form-tool", "Contact Form"),
    ("cms-faq", "FAQ Content"),
    ("cms-table-plain", "Table (Layout)"),
    ("cms-table", "Table"),
    ("cms-banner", "Banner"),
    ("cms-card-shape", "Card"),
    ("cms-shop", "Shop"),
    ("cms-video-gallery", "Video Gallery"),
    ("cms-image-accordion", "Accordion"),
    ("cms-menu-dropdown", "Menu (Dropdown)"),
    ("cms-menu-buttons", "Menu (Buttons)"),
    ("cms-menu", "Menu"),
    ("cms-breadcrumb", "Breadcrumb"),
    ("cms-contact-tool", "Contact Info"),
    ("cms-content-divider", "Divider"),
)


def signup_blockers(db):
    """What stands between the Email sign-up block and working, in words.

    Sending is refused without a way to send and without a postal
    identity, both for good reasons -- an address is confirmed by email,
    and an email to a list has to say who sent it. But the refusal reached
    the VISITOR ("sign-ups aren't working just now") and never the owner,
    who is the only person who can do anything about it. This is what the
    tool says about itself while it is being edited.
    """
    from .. import mailer as _mailer
    from ..services import legal as _legal, newsletter as _newsletter
    from .admin import get_email_settings as _email_settings

    blockers = []
    if not _mailer.is_configured(_email_settings(db)):
        blockers.append(("this site cannot send email yet",
                         "admin.settings_email", "Set up email"))
    _line, has_address = _newsletter.sender_line(_legal.settings_for(db), "")
    if not has_address:
        blockers.append(("there is no postal address on file, and an email to a "
                         "list has to carry one",
                         "admin.settings_email", "Add your address"))
    return blockers


def _section_display_label(section_type, content, base_label):
    if section_type == "blank":
        return "Empty"
    if section_type == "banner":
        return "Banner"
    if section_type == "card":
        return "Card"
    if section_type == "html" and content:
        for marker, label in HTML_SECTION_LABEL_MARKERS:
            if marker in content:
                return label
    return base_label


def _faq_report_for_editing():
    """The last FAQ save's problems, with its rejected text ready to edit."""
    report = session.pop("faq_report", None)
    if report and report.get("draft"):
        report = dict(report, editor_html=faq_editor_html(report["draft"]))
    return report


def _is_editing():
    """Whether this request is an admin looking at their own site.

    A small reader rather than a passed-down flag: the section helpers
    below are called from several places, and threading one more argument
    through all of them to answer a question the session already knows
    would be noise. Drafts hang on this — a post with no published date is
    shown here and to nobody else.
    """
    return bool(session.get("user_id")) and session.get("view_mode", "editing") == "editing"


def _normalize_column_cell(cell, nav_html="", breadcrumb_html=""):
    """Turns a raw cell value (a dict once a tool's been placed, a bare
    string for legacy content, or "" for never-touched) into the same
    fully-resolved shape _prepare_sections gives a full section, so the
    template can render a cell exactly like a mini section — its own type,
    its own display_content/raw/is_dynamic, its own tool_name for the
    per-cell header."""
    if isinstance(cell, dict):
        d = dict(cell)
    elif cell:
        d = {"type": "text", "content": cell, "tool_name": "Text"}
    else:
        d = {"type": "empty", "content": "", "tool_name": ""}
    d.setdefault("content", "")
    #  Every template writes its footer columns as bare strings, and a bare
    #  string normalises to Text — so a Contacts block in a footer column
    #  would be escaped as plain text and offered the Text ribbon. Decided
    #  here, before display_content is worked out, because by then the
    #  markup has already been escaped. is_contact_tool_block only says yes
    #  to blocks this tool actually built, so hand-written prose in a
    #  contact wrapper stays the Text it is.
    if d["type"] == "text" and is_contact_tool_block(d["content"]):
        d["type"] = "html"
        d["tool_name"] = "Contact Info"
    d.setdefault("tool_name", d.get("type", "").title())
    #  The same name the same tool answers to as a section. It used to be
    #  typed by hand into each of the twenty-two cell branches in
    #  public/page.html, and two of them had drifted: an Embed called
    #  itself "HTML / Embed" as a section and "Embed" as a cell, and the
    #  Media Player "Media Player (Audio / Video / YouTube)" against
    #  "Media Player". Nobody chose that -- it is what twenty-two literals
    #  do over time. One computation, one answer, both places.
    d["display_label"] = _section_display_label(
        d["type"], d["content"], SECTION_TYPE_LABELS.get(d["type"], d.get("tool_name") or d["type"])
    )
    d["raw"] = d["content"]
    d["is_dynamic"] = d["type"] == "html" and bool(PLACEHOLDER_RE.search(d["content"] or ""))
    if d["type"] == "text":
        d["display_content"] = _text_to_html(d["content"])
    elif d["is_dynamic"]:
        d["display_content"] = _apply_placeholders(d["content"], nav_html, breadcrumb_html)
    else:
        d["display_content"] = d["content"]
    d["width_class"] = f'cms-img-{d.get("width") or "normal"}'
    d["animation_class"] = f'cms-anim-{d["animation"]}' if d.get("animation") and d["animation"] != "none" else ""
    d["file_size_display"] = _format_file_size(d.get("file_size"))
    if d["type"] == "media" and d.get("media_type") == "youtube":
        d["youtube_id"] = _youtube_id(d.get("content", ""))
    if d["type"] == "html" and "cms-menu" in d["content"]:
        d["is_menu"] = True
        (d["menu_items"], d["menu_style"], d["menu_size"], d["menu_align"], d["menu_highlight_current"],
         d["menu_bg_color"], d["menu_text_color"], d["menu_link_style"], d["menu_font"], d["menu_button_style"],
         d["menu_submenu_style"], d["menu_direction"]) = _parse_menu_meta(d["content"])
    if d["type"] == "html" and "cms-breadcrumb" in d["content"]:
        d["is_breadcrumb"] = True
    if d["type"] == "html" and "cms-content-divider" in d["content"]:
        d["is_divider"] = True
        m = re.search(r'border-color:\s*(#[0-9a-fA-F]{6})', d["content"])
        d["divider_color"] = m.group(1) if m else ""
    if d["type"] == "html" and "cms-image-accordion" in d["content"]:
        d["is_image_accordion"] = True
        d["accordion_captions"] = [
            html_unescape(c) for c in
            re.findall(r'<span class="cms-accordion-caption">(.*?)</span>', d["content"] or "")
        ]
        d["accordion"] = accordion_settings(d["content"])
    #  cms-buy-style-, not cms-buy. The short string is a substring of
    #  cms-buy-btn, which the Email sign-up's own submit button carried --
    #  so an Email sign-up was detected as a Buy Button and handed the Buy
    #  Button's panel: a price id, a "Buy now" label, a product name and a
    #  price. The class it renders has its own name now, but every page
    #  saved before that still holds the old one, so the TEST has to be
    #  the precise thing rather than a prefix that another tool can grow.
    #  cms-buy-style- is written by build_buy_button and by nothing else.
    if d["type"] == "html" and "cms-buy-style-" in d["content"]:
        d["is_buy_button"] = True
        d["buy"] = buy_button_settings(d["content"])
    if d["type"] == "html" and "cms-block" in (d["content"] or ""):
        #  One branch for all eight declared blocks; which one it is
        #  comes back from the markup itself.
        key, values = blocks.parse_block(d["content"])
        if key:
            d["is_block"] = True
            d["block_key"] = key
            d["block_values"] = values
            d["block_spec"] = blocks.BLOCKS[key]
            d["block_counts"] = blocks.group_counts(key, values)
    if d["type"] == "html" and "cms-shop" in d["content"]:
        #  Read live rather than stored: a storefront saved as markup
        #  would go on advertising prices that have since changed.
        d["is_shop"] = True
        d["shop"] = shop_settings(d["content"])
        d["products"], d["shop_error"] = cart_service.shop_products(get_db(), integrations, editing=_is_editing())
    if d["type"] == "html" and "cms-basket" in (d["content"] or ""):
        d["is_basket"] = True
        d["basket"] = cart_service.basket_settings(d["content"])
        #  Per request: the count belongs to whoever is looking, not to
        #  the page, so it can never be stored or cached with it.
        d["display_content"] = cart_service.render_basket(
            d["content"], url_for("public.cart"), editing=_is_editing())
    if d["type"] == "html" and "cms-contact-form-tool" in (d["content"] or ""):
        d["is_contact_form"] = True
    if d["type"] == "html" and is_contact_tool_block(d["content"]):
        d["is_contact_info"] = True
        d["contact"] = read_contact_tool(d["content"])
        d["contact_layout"] = read_contact_layout(d["content"])
        d["contact_icon_size"] = read_contact_icon_size(d["content"])
    if d["type"] == "html" and "cms-blog" in (d["content"] or ""):
        d["is_blog"] = True
        d["blog"] = blog_service.blog_settings(d["content"])
        #  Worked out at render time, never stored: posts change, and a
        #  copy frozen into a section would go on showing last month's.
        d["display_content"] = blog_service.render_blog(
            get_db(), d["content"], editing=_is_editing(),
            post_url=lambda blog_slug, post_slug: url_for(
                "public.blog_post", slug=blog_slug, post_slug=post_slug),
            #  While editing, a card opens the post's editor and comes
            #  back to this page when it is saved.
            edit_url=lambda post_id: url_for(
                "admin.blog_post_edit", blog_id=d["blog"]["blog_id"],
                post_id=post_id, next=request.path),
        )
    if d["type"] == "html" and "cms-search-tool" in (d["content"] or ""):
        d["is_search"] = True
        d["search"] = search_settings(d["content"])
    if d["type"] == "html" and "cms-faq" in d["content"]:
        d["faq"] = faq_settings(d["content"])
        #  Two tools, two toolbars: one writes questions, the other picks
        #  which already-written ones to show.
        d["is_faq_reader"] = d["faq"]["is_reader"]
        d["is_faq"] = not d["faq"]["is_reader"]
        if d["faq"]["is_reader"]:
            #  Shown, not stored: the questions belong to the page they
            #  were written on, and this block only says which ones.
            d["display_content"] = resolve_faq_mirror(get_db(), d["content"])
            d["faq"]["mirror_ids"] = [i["id"] for i in (faq_mirror_items(get_db(), d["content"]) or [])]
    if d["type"] == "html" and "cms-video-gallery" in d["content"]:
        d["is_video_gallery"] = True
        d["video_gallery"] = video_gallery_settings(d["content"])
    if d["type"] == "html" and (d["content"] or "").strip().startswith("<table"):
        d["is_table"] = True
        d["table"] = table_settings(d["content"])
    if d["type"] == "rows":
        d["rows_list"] = [_normalize_column_cell(r, nav_html, breadcrumb_html) for r in d.get("rows", [])] or [_normalize_column_cell("", nav_html, breadcrumb_html)]
    return d


def _prepare_sections(sections, section_type_labels=None, nav_html="", breadcrumb_html=""):
    """Body sections go through the same dynamic-placeholder handling as
    header/footer sections (see _zone_sections) — a Breadcrumb or Menu tool
    dropped into a body section behaves identically to one dropped into the
    header: `raw` (placeholder-preserving, used by the raw-HTML editor) is
    kept separate from `display_content` (resolved, used for display), and
    `is_dynamic` disables the WYSIWYG contenteditable on it for the same
    reason it does on chunks — saving resolved HTML back as raw content
    would destroy the placeholder."""
    section_type_labels = section_type_labels or {}
    prepared = []
    for s in sections:
        d = dict(s)
        d["raw"] = d["content"]
        d["is_dynamic"] = d["type"] == "html" and bool(PLACEHOLDER_RE.search(d["content"] or ""))
        if d["type"] == "text":
            d["display_content"] = _text_to_html(d["content"])
        elif d["is_dynamic"]:
            d["display_content"] = _apply_placeholders(d["content"], nav_html, breadcrumb_html)
        else:
            d["display_content"] = d["content"]
        d["width_class"] = f'cms-img-{d["width"] or "normal"}'
        d["animation_class"] = f'cms-anim-{d["animation"]}' if d.get("animation") and d["animation"] != "none" else ""
        d["file_size_display"] = _format_file_size(d.get("file_size"))
        if d["type"] == "media" and d.get("media_type") == "youtube":
            d["youtube_id"] = _youtube_id(d["content"])
        if d["type"] == "html" and "cms-menu" in (d["content"] or ""):
            d["is_menu"] = True
            (d["menu_items"], d["menu_style"], d["menu_size"], d["menu_align"], d["menu_highlight_current"],
             d["menu_bg_color"], d["menu_text_color"], d["menu_link_style"], d["menu_font"], d["menu_button_style"],
             d["menu_submenu_style"], d["menu_direction"]) = _parse_menu_meta(d["content"])
        if d["type"] == "html" and "cms-breadcrumb" in (d["content"] or ""):
            d["is_breadcrumb"] = True
        if d["type"] == "html" and "cms-content-divider" in (d["content"] or ""):
            d["is_divider"] = True
            m = re.search(r'border-color:\s*(#[0-9a-fA-F]{6})', d["content"])
            d["divider_color"] = m.group(1) if m else ""
        if d["type"] == "html" and "cms-image-accordion" in (d["content"] or ""):
            d["is_image_accordion"] = True
            d["accordion_captions"] = [
                html_unescape(c) for c in
                re.findall(r'<span class="cms-accordion-caption">(.*?)</span>', d["content"] or "")
            ]
            d["accordion"] = accordion_settings(d["content"])
        #  The same precision as the cell path above, for the same reason.
        if d["type"] == "html" and "cms-buy-style-" in (d["content"] or ""):
            d["is_buy_button"] = True
            d["buy"] = buy_button_settings(d["content"])
        if d["type"] == "html" and "cms-block" in (d["content"] or ""):
            #  One branch for all eight declared blocks; which one it is
            #  comes back from the markup itself.
            key, values = blocks.parse_block(d["content"])
            if key:
                d["is_block"] = True
                d["block_key"] = key
                d["block_values"] = values
                d["block_spec"] = blocks.BLOCKS[key]
                d["block_counts"] = blocks.group_counts(key, values)
        if d["type"] == "html" and "cms-shop" in (d["content"] or ""):
            d["is_shop"] = True
            d["shop"] = shop_settings(d["content"] or "")
            d["products"], d["shop_error"] = cart_service.shop_products(get_db(), integrations, editing=_is_editing())
        if d["type"] == "html" and "cms-basket" in (d["content"] or ""):
            d["is_basket"] = True
            d["basket"] = cart_service.basket_settings(d["content"])
            d["display_content"] = cart_service.render_basket(
                d["content"], url_for("public.cart"), editing=_is_editing())
        if d["type"] == "html" and "cms-contact-form-tool" in (d["content"] or ""):
            d["is_contact_form"] = True
        if d["type"] == "html" and is_contact_tool_block(d["content"]):
            d["is_contact_info"] = True
            d["contact"] = read_contact_tool(d["content"])
            d["contact_layout"] = read_contact_layout(d["content"])
            d["contact_icon_size"] = read_contact_icon_size(d["content"])
        if d["type"] == "html" and "cms-blog" in (d["content"] or ""):
            d["is_blog"] = True
            d["blog"] = blog_service.blog_settings(d["content"])
            d["display_content"] = blog_service.render_blog(
                get_db(), d["content"], editing=_is_editing(),
                post_url=lambda blog_slug, post_slug: url_for(
                    "public.blog_post", slug=blog_slug, post_slug=post_slug),
                edit_url=lambda post_id: url_for(
                    "admin.blog_post_edit", blog_id=d["blog"]["blog_id"],
                    post_id=post_id, next=request.path),
            )
        if d["type"] == "html" and "cms-search-tool" in (d["content"] or ""):
            d["is_search"] = True
            d["search"] = search_settings(d["content"])
        if d["type"] == "html" and "cms-faq" in (d["content"] or ""):
            d["faq"] = faq_settings(d["content"])
            d["is_faq_reader"] = d["faq"]["is_reader"]
            d["is_faq"] = not d["faq"]["is_reader"]
            if d["faq"]["is_reader"]:
                d["display_content"] = resolve_faq_mirror(get_db(), d["content"])
                d["faq"]["mirror_ids"] = [i["id"] for i in (faq_mirror_items(get_db(), d["content"]) or [])]
        if d["type"] == "html" and "cms-video-gallery" in (d["content"] or ""):
            d["is_video_gallery"] = True
            d["video_gallery"] = video_gallery_settings(d["content"])
        if d["type"] == "html" and (d["content"] or "").strip().startswith("<table"):
            d["is_table"] = True
            d["table"] = table_settings(d["content"])
        if d["type"] == "columns":
            try:
                cols = json.loads(d["content"]).get("columns", [])
            except (ValueError, AttributeError):
                cols = []
            cols = cols or [""]
            d["columns_list"] = [_normalize_column_cell(c, nav_html, breadcrumb_html) for c in cols]
        d["display_label"] = _section_display_label(
            d["type"], d["content"], section_type_labels.get(d["type"], d["type"])
        )
        prepared.append(d)
    return prepared


def _shade_previews(template):
    """Each Shades setting drawn in the SITE'S OWN primary, as real hex.

    The picker used to paint its three tiles from var(--primary-100) and
    friends — the live ramp — which is whichever setting is already
    active. So all three tiles showed the current setting at three
    different steps, and every option looked like every other one. A
    picker has to show what a choice WOULD do, so each tile is drawn from
    that setting's own ramp, worked out here rather than in CSS, which can
    only ever see the setting that won.
    """
    if not template or not template["palette_json"]:
        return {}
    try:
        palette = json.loads(template["palette_json"])
    except (ValueError, TypeError):
        return {}
    overrides = {}
    if template["color_overrides"]:
        try:
            overrides = json.loads(template["color_overrides"])
        except (ValueError, TypeError):
            overrides = {}
    slug = _match_palette_roles(palette).get("primary")
    color = overrides.get(slug) or next(
        (c["color"] for c in palette if c["slug"] == slug), None
    )
    if not color or not re.match(r"^#[0-9a-fA-F]{6}$", color):
        return {}
    out = {}
    for key, cfg in SHADE_SPREADS.items():
        shades = ramp(color, cfg["spread"], cfg["sat_ease"], cfg.get("curve", 1.0),
                      cfg.get("light_spread"), cfg.get("dark_curve"))
        #  A light fill, the colour itself, and a dark — the three places
        #  the settings differ most.
        out[key] = [shades[100], shades[500], shades[800]]
    return out


def _theme_override_css(template):
    """Inline :root override, output after the theme's own stylesheet link
    so it wins the cascade (same specificity, later in source order). Four
    kinds of admin customization, all layered on top of a template's own
    theme.css the same way: present a curated preset (or a plain color
    picker), write the resolved value here, never touch the template's
    own file.

    1. Colors — re-emit any admin color overrides as the theme's own
       --wp--preset--color--* custom properties (what an imported theme's
       own markup, e.g. .has-primary-background-color, actually reads),
       and ALWAYS bridge each resolved role color — override if there is
       one, otherwise just the theme's own default — into --primary/
       --primary-dark, --secondary/--secondary-dark, --accent/
       --accent-dark, plus a fuller tint/shade ramp per role
       (--{role}-lightest/-light/-dark/-darker/-darkest — see
       services/palette.py's tint_shade_ramp) so each of the 3 role colors
       has real depth to draw on, not just a flat base+dark pair. Those
       are the vars the CMS's own generic chrome
       (Menu buttons, Card/Banner accents, table headers, dividers, the
       breadcrumb's current-page pill, ... — see site-base.css) reads,
       and none of that is theme markup, so it never sees
       --wp--preset--* on its own. Without this bridge those tools stay
       on their hardcoded fallback colors forever, regardless of the
       theme or any override. A well-considered complementary palette
       (see packages.DEFAULT_PALETTE/COLOR_PRESETS) only actually reads
       as one once secondary/accent reach real elements too, not just
       primary everywhere — that's the whole point of having 3 roles
       instead of 1. Runs even with zero color overrides, since the
       bridge needs to reflect the theme's own defaults too.
    2. Fonts — font_overrides (FONT_PAIRINGS, see routes/admin/__init__.py)
       re-declares --site-heading-font-family/--site-font-family, the same
       two vars every theme.css sets in its own :root block, so a picked
       pairing fully replaces the theme's own without editing its file.
    3. Shape — shape_override (SHAPE_PRESETS) sets --site-radius, which
       site-base.css's generic .cms-card-shape/.block-html/.cms-banner/
       .cms-blog-card read via var(--site-radius, <theme's own value>) —
       see _effective_google_fonts_url for the matching font-stylesheet
       resolution this pairs with.
    4. Zones — zone_style_overrides (set per header/footer/sidebar/
       sidebar_right via template_zone_style) sets --site-<zone>-bg/
       --site-<zone>-border, which each theme's own .site-header/
       .site-footer rules (and site-base.css's zone-agnostic .site-sidebar
       ones, since no theme customizes the sidebar's own background) read
       the same var(..., <theme's own value>) way. A zone's background has
       always been tied to the theme's own hardcoded color (sometimes to
       --primary) with nothing in between that and recoloring the whole
       palette — this is that missing single-zone override."""
    if not template:
        return None
    lines = []
    extra_rules = []  # whole rules, emitted after the :root block
    #  How colourful the derived shades are — the admin's Shades choice.
    #  NULL is "balanced", which is what every site had before the control
    #  existed, so an untouched template renders byte-identical CSS.
    spread_key = None
    try:
        spread_key = template["shade_spread"]
    except (IndexError, KeyError):
        pass
    _shades = SHADE_SPREADS.get(spread_key or "balanced", SHADE_SPREADS["balanced"])
    spread, sat_ease = _shades["spread"], _shades["sat_ease"]
    curve = _shades.get("curve", 1.0)
    light_spread = _shades.get("light_spread")
    dark_curve = _shades.get("dark_curve")

    if template["palette_json"]:
        try:
            palette = json.loads(template["palette_json"])
        except (ValueError, TypeError):
            palette = None
        if palette:
            overrides = json.loads(template["color_overrides"]) if template["color_overrides"] else {}
            hex_re = re.compile(r"^#[0-9a-fA-F]{3,8}$")
            lines += [f"--wp--preset--color--{slug}: {color};" for slug, color in overrides.items() if hex_re.match(color)]
            roles = _match_palette_roles(palette)
            for role_name in ("primary", "secondary", "accent"):
                role_slug = roles.get(role_name)
                if not role_slug:
                    continue
                color = overrides.get(role_slug) or next(
                    (c["color"] for c in palette if c["slug"] == role_slug), None
                )
                if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
                    lines.append(f"--{role_name}: {color};")
                    lines.append(f"--{role_name}-dark: {_darken_hex(color)};")
                    #  What can be read ON this colour — see readable_on.
                    lines.append(f"--{role_name}-on: {readable_on(color)};")
                    for suffix, shade in tint_shade_ramp(color, spread, sat_ease, curve, light_spread, dark_curve).items():
                        if suffix == "dark":
                            continue  # already emitted above, same amount/name
                        lines.append(f"--{role_name}-{suffix}: {shade};")
                    #  The palette's own greys, from the primary's hue — a
                    #  warm brand gets warm neutrals. Emitted once, off
                    #  whichever colour is playing primary, so a template
                    #  never has to hardcode a ground colour again.
                    if role_name == "primary":
                        for step, shade in neutral_ramp(color, sat_ease).items():
                            lines.append(f"--neutral-{step}: {shade};")
    if template["font_overrides"]:
        try:
            fonts = json.loads(template["font_overrides"])
        except (ValueError, TypeError):
            fonts = {}
        if fonts.get("heading_font_family"):
            lines.append(f"--site-heading-font-family: {fonts['heading_font_family']};")
        if fonts.get("body_font_family"):
            lines.append(f"--site-font-family: {fonts['body_font_family']};")
        if fonts.get("footer_font_family"):
            lines.append(f"--site-footer-font-family: {fonts['footer_font_family']};")
    #  The owner's choice if they have made one, otherwise whatever the
    #  template ships. "Auto" is read as "this template's own look", which
    #  is what it says -- it used to mean "none at all", so choosing it
    #  silently discarded the shape the template was designed with.
    shape_key = template["shape_override"] or _column(template, "shape_default")
    if shape_key:
        shape = SHAPE_PRESETS.get(shape_key)
        if shape:
            lines.append(f"--site-radius: {shape['radius']};")
            #  The strongly-curved shapes reach into their own box, so
            #  content has to be inset to clear the curve (see
            #  SHAPE_PRESETS for where the numbers come from). It rides
            #  along as a second variable rather than a rule of its own,
            #  because a section's own corner override needs exactly the
            #  same inset and gets it from the same place — see the
            #  [data-corner-style] block in site-base.css.
            if shape.get("content_padding"):
                lines.append(f"--site-radius-pad: {shape['content_padding']};")

    shadow_key = template["shadow_override"] or _column(template, "shadow_default")
    if shadow_key:
        shadow = SHADOW_PRESETS.get(shadow_key)
        if shadow:
            lines.append(f"--site-shadow: {shadow['shadow']};")
            #  ...and re-state the rule that READS it after the :root
            #  block. A theme.css may hard-code its own box-shadow on a
            #  card or banner, and site-base.css's var-reading rule loses
            #  to it on source order — the coffee-shop theme does exactly
            #  that, so picking a Depth appeared to do nothing on cards.
            #  This block is emitted AFTER the theme stylesheet, so the
            #  identical rule wins. It still reads the variable rather
            #  than hard-coding a value, which is what lets a per-section
            #  Depth (which redefines the variable) sit on top of it.
            extra_rules.append(
                ".cms-card-shape, .cms-banner, .block-image .cms-managed-image,"
                " .cms-file-card { box-shadow: var(--site-shadow, none); }"
            )
    if template["zone_style_overrides"]:
        try:
            zone_styles = json.loads(template["zone_style_overrides"])
        except (ValueError, TypeError):
            zone_styles = {}
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for zone, style in zone_styles.items():
            if zone not in ("header", "footer", "sidebar", "sidebar_right", "body"):
                continue
            bg = style.get("bg")
            if bg and hex_re.match(bg):
                lines.append(f"--site-{zone}-bg: {bg};")
            border = style.get("border")
            if border and hex_re.match(border):
                lines.append(f"--site-{zone}-border: 3px solid {border};")
    if not lines and not extra_rules:
        return None
    root = ":root {\n  " + "\n  ".join(lines) + "\n}" if lines else ""
    return "\n".join([root] + extra_rules) if extra_rules else root


def _role_color_ramps(template):
    """The Colors panel's depth preview. The work is in the palette
    service now: the newsletter needs the same answer -- what colour is
    this site, actually -- and a route may not reach into another."""
    return palette_service.role_ramps(template)


def _effective_google_fonts_url(template):
    """The <link> href for this page's webfonts — the template's own
    google_fonts_url, unless a font pairing override is set, in which case
    the override is the sole source of truth (including "" for the
    System Sans preset, which deliberately drops the theme's webfont
    entirely rather than falling back to it)."""
    if not template:
        return None
    if template["font_overrides"]:
        try:
            fonts = json.loads(template["font_overrides"])
        except (ValueError, TypeError):
            return template["google_fonts_url"]
        return fonts.get("google_fonts_url") or None
    return template["google_fonts_url"]


def _render_page(db, page, post=None, post_content=""):
    """Renders a page — or a post, on the page its blog is shown on.

    One shell for both, because there was a second one and it drifted. A
    post page printed each header/sidebar/footer section's stored content
    directly, which is only the same thing as its output for the simplest
    tools: a Columns section stores JSON, a Menu and a Blog store markers,
    and every declared block stores something the page turns into markup
    later. So a post lost its footer's contact details, and every section
    lost the wrapper carrying its width, background and spacing.

    Sharing the shell means a tool built next year appears on a post page
    for free, and cannot be quietly missing from one of the two.
    """
    template = _active_template(db)
    nav_pages = _nav_pages(db)
    logged_in = bool(session.get("user_id"))
    view_mode = session.get("view_mode", "editing")
    editing = logged_in and view_mode == "editing"
    #  ?preview=1 renders this ONE request as a visitor sees it, without
    #  touching the session -- which is what lets the responsive preview
    #  show the real page inside a frame while the editor stays open
    #  behind it. A visitor gains nothing by passing it: they were never
    #  editing.
    preview = request.args.get("preview") == "1"
    if preview:
        editing = False
        view_mode = "viewing"
        #  The admin bar is drawn for anybody logged in, not only while
        #  editing -- so a preview has to say "pretend I am not" or it
        #  shows a strip no visitor will ever see, at the top of a frame
        #  whose whole job is to be honest about what they see.
        logged_in = False
    nav_html = _build_nav_html(nav_pages, editing)
    #  A post is one level below the page its blog sits on, and the trail
    #  should say so rather than stopping at the page.
    breadcrumb_html = _build_breadcrumb_html(page) if not post else _build_breadcrumb_html(
        page, current_title=post["title"],
        current_url=url_for("public.blog_post",
                            slug=blog_service.get_blog(db, post["blog_id"])["slug"],
                            post_slug=post["slug"]),
    )
    #  A post replaces the page's own sections with the post itself: the
    #  page around it — header, sidebars, footer — is what it is borrowing.
    sections = [] if post else _prepare_sections(
        db.execute("SELECT * FROM sections WHERE page_id = ? ORDER BY position", (page["id"],)).fetchall(),
        dict(SECTION_TYPES), nav_html, breadcrumb_html,
    )
    blog_posts = []
    if page["page_type"] == "blog":
        logged_in_for_posts = bool(session.get("user_id"))
        if logged_in_for_posts:
            blog_posts = db.execute(
                "SELECT * FROM blog_posts WHERE page_id = ? ORDER BY position DESC, id DESC", (page["id"],)
            ).fetchall()
        else:
            blog_posts = db.execute(
                "SELECT * FROM blog_posts WHERE page_id = ? AND published_at != '' AND published_at IS NOT NULL "
                "ORDER BY published_at DESC, id DESC",
                (page["id"],),
            ).fetchall()
    header_sections = _zone_sections(db, template, "header", nav_html, breadcrumb_html, dict(SECTION_TYPES))
    sidebar_sections = [] if page["hide_sidebar"] else _zone_sections(db, template, "sidebar", nav_html, breadcrumb_html, dict(SECTION_TYPES))
    sidebar_right_sections = [] if page["hide_sidebar_right"] else _zone_sections(db, template, "sidebar_right", nav_html, breadcrumb_html, dict(SECTION_TYPES))
    footer_sections = [] if page["hide_footer"] else _zone_sections(db, template, "footer", nav_html, breadcrumb_html, dict(SECTION_TYPES))
    theme_css_vars = _theme_override_css(template)
    all_templates = db.execute("SELECT * FROM templates ORDER BY is_builtin DESC, name").fetchall() if editing else []
    activate_conflict_map, active_content = (
        dashboard_template_maps(db, current_app.static_folder, all_templates) if editing else ({}, None)
    )
    #  A fresh challenge per page load, so a token cannot be harvested
    #  once and replayed forever — it carries its own issue time.
    captcha_question, captcha_token = captcha.challenge()
    #  A newsletter page carries its own send controls while it is being
    #  edited, so it needs the few facts they turn on: who is on the list,
    #  whether there is anything to send with, and which parts of THIS
    #  page can be aimed at. Worked out only for a page that is one --
    #  every other page pays nothing for this.
    newsletter_send = None
    if editing and page["page_type"] == "newsletter":
        email_settings = get_email_settings(db)
        line, has_address = newsletter.sender_line(
            legal.settings_for(db), (get_site_settings(db) or {}).get("site_title"))
        newsletter_send = {
            "choices": newsletter.choices_for(sections),
            "counts": subscribers.counts(db),
            "audiences": subscribers.AUDIENCES,
            #  So the confirm can name the number it is actually about to
            #  reach, whichever way the send is aimed.
            "audience_counts": {key: subscribers.audience_count(db, key)
                                for key, _label in subscribers.AUDIENCES},
            "email_ready": mailer.is_configured(email_settings),
            "has_address": has_address,
            "sender_line": line,
            "last": newsletter.last_send(db, "page", page["id"]),
        }
    return render_template(
        "public/page.html",
        newsletter_send=newsletter_send,
        #  Picture fields inside block forms choose from the Image Library
        #  rather than offering an upload of their own: one place files
        #  live, one place to manage them.
        #  The owner's own uploads, plus the pictures the active template
        #  brought with it. Without the second half a fresh site offers an
        #  empty picker while its own footer is full of photographs — the
        #  template's media is installed and served, it simply was not in
        #  the one list that decides what can be chosen.
        media_images=(_pickable_images(template) if editing else []),
        captcha_question=captcha_question,
        captcha_token=captcha_token,
        captcha_field=captcha.HONEYPOT_FIELD,
        page=page,
        post=post,
        post_content=post_content,
        blog=(blog_service.get_blog(db, post["blog_id"]) if post else None),
        sections=sections,
        blog_posts=blog_posts,
        template=template,
        google_fonts_url=_effective_google_fonts_url(template),
        nav_pages=nav_pages,
        link_pages=_link_choices(nav_pages),
        faq_sources=(faq_sources(db) if editing else []),
        max_faq_items=MAX_FAQ_ITEMS,
        nav_html=nav_html,
        nav_layout=page["nav_layout_override"] or get_nav_layout(db),
        header_sections=header_sections,
        sidebar_sections=sidebar_sections,
        sidebar_right_sections=sidebar_right_sections,
        footer_sections=footer_sections,
        color_css=theme_css_vars,
        editing=editing,
        logged_in=logged_in,
        view_mode=view_mode,
        current_path=request.path,
        assistant_configured=assistant.is_configured(db) if logged_in else False,
        content_tools=_list_tools(db) if editing else [],
        tool_categories=TOOL_CATEGORIES,
        tool_category_labels=dict(TOOL_CATEGORIES),
        faq_formatting_help=FAQ_FORMATTING_HELP,
        max_contact_rows=MAX_CONTACT_ROWS,
        contact_layouts=CONTACT_LAYOUTS if editing else (),
        signup_blockers=(signup_blockers(db) if editing else []),
        contact_icon_min=CONTACT_ICON_MIN,
        contact_icon_max=CONTACT_ICON_MAX,
        contact_icon_default=CONTACT_ICON_DEFAULT,
        search_styles=SEARCH_STYLES,
        basket_styles=cart_service.BASKET_STYLES,
        basket_aligns=cart_service.BASKET_ALIGNS,
        basket_icons=cart_service.BASKET_ICONS,
        faq_views=FAQ_VIEWS,
        #  Read once and cleared: a report is about the save that just
        #  happened, and should not follow the admin around the site. A
        #  rejected document comes back as something to edit, not as text
        #  to retype — there is only one editing surface now.
        faq_report=_faq_report_for_editing() if editing else None,
        faq_rules=FAQ_RULES,
        blogs=(blog_service.list_blogs(db) if editing else []),
        blog_styles=blog_service.BLOG_STYLES,
        section_type_labels=dict(SECTION_TYPES),
        email_configured=mailer.is_configured(get_email_settings(db)),
        icon_choices=icons.icon_choices_for() if editing else [],
        color_presets=color_scheme_choices(db) if editing else {},
        role_color_ramps=_role_color_ramps(template) if editing else {},
        font_pairings=FONT_PAIRINGS if editing else {},
        shape_presets=SHAPE_PRESETS if editing else {},
        shadow_presets=SHADOW_PRESETS if editing else {},
        shade_spreads=SHADE_SPREADS if editing else {},
        shade_previews=_shade_previews(template) if editing else {},
        stripe_catalogue=(integrations.stripe_catalogue_cached(db)[0]
                          if editing and integrations.is_configured(db, "stripe") else []),
        stripe_connected=integrations.is_configured(db, "stripe") if editing else False,
        google_font_choices=GOOGLE_FONT_CHOICES if editing else (),
        google_fonts_preview_url=(
            _google_fonts_stylesheet_url([n for n, _ in GOOGLE_FONT_CHOICES]) if editing else None
        ),
        all_templates=all_templates,
        nav_layouts=NAV_LAYOUTS,
        sidebar_layout_presets=SIDEBAR_LAYOUT_PRESETS if editing else {},
        footer_layout_presets=FOOTER_LAYOUT_PRESETS if editing else {},
        has_sidebar_content=bool(sidebar_sections or sidebar_right_sections),
        active_content=active_content,
        activate_conflict_map=activate_conflict_map,
    )
