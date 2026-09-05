import json
import os
import uuid
import urllib.parse
from flask import request, flash, redirect, url_for, jsonify, render_template, current_app, session
from werkzeug.security import generate_password_hash

from . import bp
from ..auth import login_required, save_google_settings
from ...db import get_db
from ... import assistant, ai_image, mailer
from ...services.sections import _save_card_image_file, _list_media
from ...services import integrations, commerce, downloads, cart, site, shipping
from ... import bootstrap
from ... import crypto
from . import wants_json, get_site_settings, _set_setting, EMAIL_SETTINGS_KEYS, get_email_settings

@bp.route("/settings/site", methods=["POST"])
@login_required
def settings_site():
    """Only touches a field that's actually present in the submitted form
    — the site-brand link on the live page autosaves just `site_title`
    on its own (see the [data-save-url][data-field] autosave wiring in
    inline-editor.js), and that single-field POST must never blank out
    the tagline it didn't include."""
    db = get_db()
    current = get_site_settings(db)
    if "site_title" in request.form:
        title = (request.form.get("site_title") or "").strip() or "My Site"
    else:
        title = current["site_title"]
    if "site_tagline" in request.form:
        tagline = (request.form.get("site_tagline") or "").strip()
    else:
        tagline = current["site_tagline"]
    for key, value in (("site_title", title), ("site_tagline", tagline)):
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    db.commit()
    if wants_json():
        return jsonify({"ok": True})
    flash("Site name saved.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/settings/maintenance", methods=["POST"])
@login_required
def settings_maintenance():
    """Turn the visitor-facing holding page on or off, and set its words.

    While it is on, visitors get the message and a 503; the owner, being
    signed in, keeps seeing the real site (see services/maintenance.py and
    the public maintenance gate). Blank message falls back to the default.
    """
    db = get_db()
    on = "1" if request.form.get("maintenance_mode") == "1" else "0"
    message = (request.form.get("maintenance_message") or "").strip()[:1000]
    _set_setting(db, "maintenance_mode", on)
    _set_setting(db, "maintenance_message", message)
    db.commit()
    if on == "1":
        flash("Maintenance mode is ON — visitors see your holding page. "
              "You still see the site while you're signed in.", "success")
    else:
        flash("Maintenance mode is off — the site is live again.", "success")
    return redirect(url_for("admin.dashboard"))


FAVICON_EMOJI_CHOICES = (
    "☕", "🍕", "🍔", "🍰", "🍺", "🌿", "🌸", "🏠", "🏡", "🏢", "🏋️", "🎨",
    "🎵", "🎬", "📷", "📚", "✂️", "🔧", "⚖️", "🩺", "🐾", "🚗", "✈️", "⛵",
    "🌍", "⭐", "❤️", "✨", "🔥", "💡", "🛒", "💼", "🎓", "🧵", "🌱", "🍷",
)


@bp.route("/settings/favicon/upload", methods=["POST"])
@login_required
def settings_favicon_upload():
    db = get_db()
    url, error = _save_card_image_file()
    if error:
        flash(error[0], "error")
        return redirect(url_for("admin.dashboard"))
    _set_setting(db, "favicon_url", url)
    db.commit()
    flash("Favicon updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/settings/favicon/library", methods=["POST"])
@login_required
def settings_favicon_library():
    """Use a picture already in the Media Library as the favicon.

    The URL arrives from the picker, but it is never trusted as a path: it
    is checked against what is actually IN the library (image files only)
    and the library's own value is used, not the string that was sent --
    the same rule the file/image tools follow."""
    db = get_db()
    picked = (request.form.get("url") or "").strip()
    known = {m["url"]: m for m in _list_media(image_only=True)}
    item = known.get(picked)
    if not item:
        flash("That picture is not in your Media Library — choose another.", "error")
        return redirect(url_for("admin.dashboard"))
    _set_setting(db, "favicon_url", item["url"])
    db.commit()
    flash("Favicon updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/settings/favicon/emoji", methods=["POST"])
@login_required
def settings_favicon_emoji():
    db = get_db()
    emoji = (request.form.get("emoji") or "").strip()
    if not emoji or emoji not in FAVICON_EMOJI_CHOICES:
        flash("Please pick one of the offered emoji.", "error")
        return redirect(url_for("admin.dashboard"))
    # An inline SVG data URI with the emoji as text — every modern browser
    # accepts this directly as a favicon, so a one-character "logo" needs
    # no generated image file or upload at all.
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<text x="50%" y="54%" font-size="52" text-anchor="middle" dominant-baseline="middle">{emoji}</text>'
        "</svg>"
    )
    data_url = "data:image/svg+xml," + urllib.parse.quote(svg)
    _set_setting(db, "favicon_url", data_url)
    db.commit()
    flash("Favicon updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/settings/favicon/generate", methods=["POST"])
@login_required
def settings_favicon_generate():
    db = get_db()
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        flash("Describe the favicon you want.", "error")
        return redirect(url_for("admin.dashboard"))
    try:
        image_bytes = ai_image.generate_image(
            db, prompt + " — a simple, bold, minimal icon/logo mark on a plain background, no text, no words, no letters",
            width=256, height=256,
        )
    except ai_image.ImageGenError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.dashboard"))
    unique_name = f"{uuid.uuid4().hex}.png"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(image_bytes)
    url = f"/static/uploads/{unique_name}"
    db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
    _set_setting(db, "favicon_url", url)
    db.commit()
    flash("Favicon generated!", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/settings/favicon/clear", methods=["POST"])
@login_required
def settings_favicon_clear():
    db = get_db()
    _set_setting(db, "favicon_url", "")
    db.commit()
    flash("Favicon removed.", "success")
    return redirect(url_for("admin.dashboard"))



@bp.route("/settings/layout", methods=["POST"])
@login_required
def settings_layout():
    db = get_db()
    width = request.form.get("default_section_width", "auto")
    width = width if width in ("auto", "full", "custom") else "auto"
    pct = request.form.get("default_section_width_pct", type=int) or 100
    pct = max(10, min(100, pct))
    for key, value in (("default_section_width", width), ("default_section_width_pct", str(pct))):
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    db.commit()
    flash("Default section width saved.", "success")
    return redirect(url_for("admin.dashboard"))


def _missing_email_fields(settings):
    """Which required fields are still blank. mailer.is_configured only
    answers yes or no, and "no" is useless to someone looking at a form
    that appears filled in."""
    labels = {
        "smtp_host": "SMTP host",
        "smtp_username": "username",
        "smtp_password": "password",
        "to_email": "the address messages go to",
    }
    return [label for key, label in labels.items() if not (settings.get(key) or "").strip()]


@bp.route("/settings/email", methods=["GET", "POST"])
@login_required
def settings_email():
    db = get_db()
    if request.method == "POST":
        for key in EMAIL_SETTINGS_KEYS:
            value = request.form.get(key, "").strip()
            if key == "smtp_use_tls":
                value = "1" if request.form.get("smtp_use_tls") else "0"
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        #  Who is sending, edited on the screen where sending is set up.
        #  These are the SAME two settings the legal pages are written
        #  from -- deliberately the same keys, not a second copy, because
        #  one install is one business and its name and address should be
        #  asked for once (see CLAUDE.md, "The site's identity is the
        #  site's"). They live here as well because this is where somebody
        #  goes when mail is not working, and mail to a list without a
        #  postal identity is refused rather than sent.
        for key in ("legal_business", "legal_address"):
            if key in request.form:
                db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, request.form.get(key, "").strip()),
                )
        #  Whether the postal address is repeated at the bottom of emails
        #  (the website's Impressum still carries it either way). A checkbox,
        #  so absent means unticked.
        _set_setting(db, "email_include_address",
                     "1" if request.form.get("email_include_address") else "0")
        db.commit()
        settings = get_email_settings(db)
        missing = _missing_email_fields(settings)
        if missing:
            #  Saving an incomplete configuration used to look identical to
            #  saving a working one, and the only symptom was mail silently
            #  never arriving. Say so at the moment it is saved.
            flash(
                "Saved — but email can't send yet: " + ", ".join(missing) +
                " still needed.", "warning",
            )
        else:
            flash("Email settings saved. This site can send mail.", "success")
        return redirect(url_for("admin.settings_email"))
    settings = get_email_settings(db)
    from ...services import legal as legal_service
    return render_template(
        "admin/settings_email.html",
        settings=settings,
        missing=_missing_email_fields(settings),
        sender=legal_service.settings_for(db),
    )


@bp.route("/commerce/bookings", methods=["GET"])
@login_required
def commerce_bookings():
    """The diary: what is booked, by whom, and what they have left.

    Deliberately a view onto Cal.com rather than a calendar of our own.
    Cal.com already connects to Google Calendar (and Outlook, and iCloud)
    with two-way sync — it blocks times the owner is busy and drops the
    meeting into their own calendar with the joining link. Building a
    second, direct Google integration here would mean an OAuth app,
    Google's verification review, and token refresh, all to re-display
    events something already connected is managing. What was missing was
    not the calendar; it was the one thing Cal.com cannot know — which
    booking came from which purchase, and how many sessions that person
    has left.
    """
    db = get_db()
    ready = integrations.is_configured(db, "calcom")
    bookings, error = ([], None)
    if ready:
        #  Keeps the ledger honest whenever the owner looks, not only
        #  when a buyer does.
        commerce.sync_bookings(db, integrations)
        db.commit()
        bookings, error = integrations.calcom_bookings(db)
        for b in bookings:
            b["from_purchase"] = bool(db.execute(
                "SELECT 1 FROM bookings WHERE provider_uid = ?", (b["uid"],)
            ).fetchone())
            #  Matched on the attendee's email, not on our own booking
            #  row, so a customer who books through the owner's public
            #  Cal.com page still shows what they have left.
            b["sessions_left"] = commerce.balance_for(db, b["email"]) if b["email"] else None
    return render_template(
        "admin/commerce_bookings.html",
        bookings=bookings,
        gone=commerce.gone_bookings(db),
        calcom_ready=ready,
        error=integrations.explain(error, "Cal.com"),
    )


@bp.route("/commerce/bookings/<uid>/cancel", methods=["POST"])
@login_required
def commerce_booking_cancel(uid):
    """Cancels from the owner's side, through Cal.com.

    Deliberately not a link into a calendar app: cancelling in Google
    Calendar does not reach Cal.com (the sync writes one way), so the
    booking would stay live, the buyer's session would stay spent, and
    nobody would find out until the meeting did not happen. Cancelling
    here goes to the authority and returns the session in the same step.
    """
    db = get_db()
    ok, error = commerce.cancel_booking(db, integrations, uid,
                                        reason="Cancelled by the organiser")
    db.commit()
    if not ok:
        return jsonify({"ok": False, "error": error or "Couldn't cancel that booking."}), 400
    return jsonify({"ok": True, "message": "Cancelled. The session went back to whoever paid for it."})


@bp.route("/commerce/orders/<int:order_id>/invoice")
@login_required
def commerce_order_invoice(order_id):
    """The seller's copy of the same tax document the buyer receives.

    A redirect for the same reasons the buyer's is: the Orders screen
    lists many orders, and asking Stripe about every invoice on every
    load would be one request per row for links nobody clicks. And the
    PDF link is null until Stripe finalises the invoice, which is
    normally after the webhook that recorded the order.
    """
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        flash("That order no longer exists.", "error")
        return redirect(url_for("admin.commerce_orders"))
    pdf, hosted = commerce.invoice_links(db, order, integrations)
    db.commit()
    if pdf or hosted:
        return redirect(pdf or hosted)
    #  Not "not found": the invoice exists and is not ready, and those
    #  two need different actions from whoever is reading.
    flash("Stripe hasn't finalised that invoice yet — it usually takes a minute. "
          "Try again shortly.", "warning")
    return redirect(url_for("admin.commerce_orders"))


@bp.route("/commerce/orders", methods=["GET"])
@login_required
def commerce_orders():
    """Who bought what, and what they are still owed.

    This is the answer to "someone says they never got their email" and
    to "what has this person actually paid for" — the two questions an
    owner asks about a sale after it happens.

    Filtered by buyer, by product and by date, because those are the three
    ways somebody arrives at this page with a question already in mind.
    The filters are plain links on this same address, so a filtered view
    can be bookmarked and sent to somebody.
    """
    db = get_db()
    who = (request.args.get("who") or "").strip()
    what = (request.args.get("what") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    since = (request.args.get("since") or "").strip()
    until = (request.args.get("until") or "").strip()

    sql = ("SELECT o.*, c.email, c.name, c.page_password_hash FROM orders o "
           "LEFT JOIN customers c ON c.id = o.customer_id WHERE 1=1")
    args = []
    if who:
        sql += " AND c.email = ?"
        args.append(who)
    if since:
        sql += " AND o.created_at >= ?"
        args.append(since)
    if until:
        #  An inclusive end date: somebody choosing the 27th means the
        #  whole of the 27th, not midnight at the start of it.
        sql += " AND o.created_at < date(?, '+1 day')"
        args.append(until)
    sql += " ORDER BY o.id DESC LIMIT 500"
    rows = db.execute(sql, args).fetchall()

    #  What each order was FOR. The screen showed an amount and no
    #  product, which answers neither of the questions above on its own.
    def bought(order):
        try:
            items = json.loads(order["line_items"] or "[]")
        except (ValueError, TypeError):
            return []
        out = []
        for item in items:
            name = item.get("description") or (item.get("price") or {}).get("nickname")
            if name:
                out.append((name, item.get("quantity") or 1))
        return out

    #  What each order DELIVERS, which is a different question from what
    #  it was called: "a download" and "something to post" are the two
    #  jobs an owner sorts their day by. Payment-only is the absence of
    #  any rule, so it is a kind here even though it is a row nowhere.
    ents_by_order = {}
    for row in db.execute("SELECT * FROM entitlements ORDER BY id").fetchall():
        ents_by_order.setdefault(row["order_id"], []).append(row)

    def kinds_of(order_id):
        found = {e["kind"] for e in ents_by_order.get(order_id, [])}
        return found or {"payment"}

    orders = []
    for row in rows:
        names = bought(row)
        if what and what not in [n for n, _ in names]:
            continue
        if kind and kind not in kinds_of(row["id"]):
            continue
        #  Not "items": Jinja resolves entry.items to dict.items, the
        #  method, and hands the template something it cannot loop over.
        orders.append({"row": row, "bought": names})

    #  The choices offered are the ones actually present, so a filter can
    #  never select nothing.
    buyers = [r["email"] for r in db.execute(
        "SELECT DISTINCT c.email FROM orders o JOIN customers c ON c.id = o.customer_id "
        "WHERE c.email IS NOT NULL ORDER BY c.email").fetchall()]
    products = sorted({n for r in db.execute(
        "SELECT line_items FROM orders").fetchall() for n, _ in bought(r)})

    return render_template(
        "admin/commerce_orders.html",
        orders=orders,
        entitlements=ents_by_order,
        buyers=buyers,
        products=products,
        filters={"who": who, "what": what, "kind": kind, "since": since, "until": until},
        filtered=bool(who or what or kind or since or until),
        email_ready=mailer.is_configured(get_email_settings(db)),
    )


@bp.route("/commerce/orders/<int:order_id>/resend", methods=["POST"])
@login_required
def commerce_order_resend(order_id):
    """Sends the buyer a fresh link to what they bought.

    Mints a NEW token rather than reusing the old one, because the stored
    hash cannot be turned back into a link. Any previous link keeps
    working until it expires, which is the kind thing to do when someone
    may still have the first email."""
    db = get_db()
    from ...routes.public import _send_order_email

    sent = _send_order_email(db, order_id)
    db.commit()
    if sent:
        return jsonify({"ok": True, "message": "Sent — a fresh link is on its way to them."})
    return jsonify({
        "ok": False,
        "message": "Couldn't send. Check Email Settings, and that this order has a customer email against it.",
    })


@bp.route("/commerce/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def commerce_order_delete(order_id):
    """Remove one order and anything it granted. Orders live HERE, not in
    Stripe, so switching or disconnecting Stripe never clears them -- this
    is how a test order gets tidied away. A real order is a record you
    usually keep, so the button asks first."""
    db = get_db()
    db.execute("DELETE FROM entitlements WHERE order_id = ?", (order_id,))
    db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    db.commit()
    flash("Order deleted.", "success")
    return redirect(url_for("admin.commerce_orders"))


@bp.route("/commerce/orders/purge", methods=["POST"])
@login_required
def commerce_orders_purge():
    """Clear orders in bulk -- for wiping test data before going live,
    since swapping Stripe keys leaves the orders untouched. `scope=test`
    removes only test-mode ones (a Stripe test id carries "test"); anything
    else removes every order. Their granted entitlements go with them."""
    db = get_db()
    if request.form.get("scope") == "test":
        rows = db.execute("SELECT id FROM orders WHERE provider_ref LIKE '%test%'").fetchall()
        what = "test order"
    else:
        rows = db.execute("SELECT id FROM orders").fetchall()
        what = "order"
    ids = [r["id"] for r in rows]
    if ids:
        marks = ",".join("?" * len(ids))
        db.execute("DELETE FROM entitlements WHERE order_id IN (%s)" % marks, ids)
        db.execute("DELETE FROM orders WHERE id IN (%s)" % marks, ids)
    db.commit()
    flash("Removed %d %s%s." % (len(ids), what, "" if len(ids) == 1 else "s"), "success")
    return redirect(url_for("admin.commerce_orders"))


@bp.route("/commerce/customers/<int:customer_id>/unlock", methods=["POST"])
@login_required
def commerce_customer_unlock(customer_id):
    """Takes a buyer's own password off their purchases page.

    The owner is the reset mechanism, deliberately: a buyer has no account
    and no address we could safely send a reset to that is not the same
    address the link already went to. Removing it costs them nothing --
    the link still works, and nothing they bought is touched.
    """
    db = get_db()
    commerce.set_page_password(db, customer_id, "")
    db.commit()
    return jsonify({"ok": True, "message": "Password removed. Their link opens the page again."})


@bp.route("/commerce/fulfilment", methods=["GET"])
@login_required
def commerce_fulfilment():
    """What each Stripe price actually delivers.

    Stripe knows a price exists and that someone paid it. It has no idea
    that "10 Coaching Sessions" should become ten bookable credits against
    a particular calendar, or that an item has three left in a cupboard.
    This screen is where the owner says so, once, and the payment handler
    then needs no special case per product.
    """
    db = get_db()
    #  The products themselves are all this screen shows now; the shop's
    #  own settings (currency, delivery, files, expiries) moved to their
    #  own tab, so there is no longer a reason to fetch the catalogue here
    #  as well as the product list.
    products, product_error = ([], None)
    if integrations.is_configured(db, "stripe"):
        products, product_error = integrations.stripe_products(db)
        product_error = integrations.explain(product_error, "Stripe")
    #  Cal.com event types feed the "bookable against" field of a
    #  session-credit rule, which is now folded into each product's editor.
    event_types, ev_error = ([], None)
    if integrations.is_configured(db, "calcom"):
        event_types, ev_error = integrations.calcom_event_types(db)
        ev_error = integrations.explain(ev_error, "Cal.com")
    rules = {
        r["price_id"]: r
        for r in db.execute("SELECT * FROM fulfilment_rules").fetchall()
    }
    #  Nothing sold through Stripe can ever be deleted — a price has no
    #  delete at all, and a product that has been bought keeps its
    #  history — so an owner's list only ever grows. Retired items are
    #  therefore folded away by default rather than left to bury the
    #  things actually on sale.
    show_all = request.args.get("show") == "all"
    retired = [p for p in products if not p["active"]]
    if not show_all:
        products = [p for p in products if p["active"]]
    return render_template(
        "admin/commerce_fulfilment.html",
        files=downloads.list_files(db),
        retired_count=len(retired),
        show_all=show_all,
        products=products,
        product_error=product_error,
        base_currency=integrations.base_currency(db),
        #  Whether a picture can be MADE, and if not, why -- said in the
        #  owner's terms rather than left as a button that does nothing.
        image_gen_ready=ai_image.is_configured(db),
        image_gen_reason=(None if ai_image.is_configured(db)
                          else ai_image.unavailable_reason(db)),
        intervals=integrations.INTERVALS,
        public_url=bool((get_email_settings(db).get("site_public_url") or "").strip()),
        event_types=event_types,
        event_error=ev_error,
        rules=rules,
        #  For the "something to post" rule: which delivery services a
        #  product can be tied to (or left on the shop-wide set).
        shipping_services=shipping.list_services(db, enabled_only=True),
        stripe_ready=integrations.is_configured(db, "stripe"),
        calcom_ready=integrations.is_configured(db, "calcom"),
    )


@bp.route("/commerce/settings", methods=["GET"])
@login_required
def commerce_settings():
    """Store-wide settings that are NOT a product: the currency the shop
    charges in, the pool of files sold as downloads, delivery, and how
    long a session credit or a download stays good for.

    These used to sit on the Products screen among the products, which
    made a long page read as one confusing list. A product is a thing you
    sell; these are the rules the shop runs by, so they get their own tab.
    """
    db = get_db()
    download_row = db.execute(
        "SELECT value FROM settings WHERE key = 'commerce_download_expiry_days'"
    ).fetchone()
    expiry_row = db.execute(
        "SELECT value FROM settings WHERE key = 'commerce_credit_expiry_months'"
    ).fetchone()
    return render_template(
        "admin/commerce_settings.html",
        stripe_ready=integrations.is_configured(db, "stripe"),
        currencies=integrations.CURRENCIES,
        base_currency=integrations.base_currency(db),
        currencies_in_use=integrations.currencies_in_use(db)[0],
        #  Delivery is now weight-based: a list of services, each with its
        #  own weight-band price table, plus a shop-wide free-over line.
        shipping_services=shipping.list_services(db),
        free_over=cart.free_over(db),
        zones=integrations.SHIPPING_ZONES,
        credit_expiry_months=(expiry_row["value"] if expiry_row else "") or "",
        download_expiry_days=(download_row["value"] if download_row else None),
    )


def _money_to_cents(value):
    """"12.50" -> 1250. Entered the way a price is written, stored the way
    Stripe counts."""
    value = (value or "").strip().replace(",", ".")
    try:
        return max(0, int(round(float(value) * 100)))
    except ValueError:
        return 0


#  A product photograph is square-ish on Stripe's payment page and in
#  this site's own shop grid, so that is what is asked for.
PRODUCT_IMAGE_SIZE = (800, 800)


def _generated_product_image_url(prompt):
    """(url, error_or_None). A picture made from a description.

    The same path an uploaded one takes from here on -- same folder, same
    `generated_images` record, same rule about what Stripe is handed --
    so there is exactly one answer to "where do product pictures live".
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return None, "Describe the picture you want."
    db = get_db()
    if not ai_image.is_configured(db):
        return None, ai_image.unavailable_reason(db)
    try:
        image_bytes = ai_image.generate_image(
            db,
            prompt + " — a clean product photograph on a plain, uncluttered "
                     "background, well lit, no text, no words, no watermark",
            width=PRODUCT_IMAGE_SIZE[0], height=PRODUCT_IMAGE_SIZE[1],
        )
    except ai_image.ImageGenError as e:
        return None, str(e)
    unique_name = f"{uuid.uuid4().hex}.png"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(image_bytes)
    url = f"/static/uploads/{unique_name}"
    db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
    #  Same rule as an upload: Stripe fetches from whatever URL it is
    #  handed, so one that does not resolve from outside this network is
    #  a broken picture on the payment page.
    base = site.public_base(db)
    return ((base + url) if base and site.is_public_host(base) else url), None


def _picture_for_product():
    """(url, error). Whichever way the owner chose to provide one.

    Three sources, in order of how deliberate each is: a file somebody
    actually attached wins, then a picture chosen from the Media Library,
    then an AI description. A prompt or a stale library pick left in the
    form from last time should never beat a file just attached. Neither is
    required; a product without a picture is fine.
    """
    file = request.files.get("image")
    if file and file.filename:
        return _product_image_url()
    picked = (request.form.get("image_library_url") or "").strip()
    if picked:
        return _library_image_url(picked)
    if (request.form.get("image_prompt") or "").strip():
        return _generated_product_image_url(request.form.get("image_prompt"))
    return None, None


def _library_image_url(picked):
    """(url, error). A picture the owner chose from the Media Library.

    The URL arrives from the picker but is never trusted as a path: it
    must match something actually IN the library (image files only) and
    the library's own stored value is used, not the string sent -- the
    same rule the favicon and file/image tools follow. Made absolute for
    Stripe when this site has a public address, since Stripe fetches the
    picture by URL; the shop on this site uses it either way.
    """
    known = {m["url"]: m for m in _list_media(image_only=True)}
    item = known.get(picked)
    if not item:
        return None, "That picture is not in your Media Library — choose another."
    db = get_db()
    url = item["url"]
    base = site.public_base(db)
    return ((base + url) if base and site.is_public_host(base) else url), None


def _product_image_url():
    """(url, error_or_None). An uploaded picture, saved locally.

    Sent on to Stripe only when this site has a public address, because
    Stripe fetches the image from the URL it is given — a link to a
    machine on someone's home network would simply be a broken picture on
    the payment page. The shop on this site uses it either way.
    """
    file = request.files.get("image")
    if not file or not file.filename:
        return None, None
    url, error = _save_card_image_file()
    if error:
        return None, error[0]
    db = get_db()
    #  Stripe fetches the picture from whatever URL it is handed, so it is
    #  only worth sending one that resolves from outside this network.
    base = site.public_base(db)
    return ((base + url) if base and site.is_public_host(base) else url), None


@bp.route("/settings/site-address", methods=["POST"])
@login_required
def settings_site_address():
    """The one place this site is told where it lives.

    Changing it is a transactional change, not a cosmetic one: it is the
    address Stripe returns buyers to, the address in every emailed access
    link, and the address Stripe calls back on. The last of those is
    registered WITH Stripe, so a changed domain leaves a webhook pointing
    at somewhere that no longer answers — silently, since a webhook that
    is never delivered looks exactly like one that was never needed. So
    any registered webhook is re-pointed here, in the same step.
    """
    db = get_db()
    previous = site.public_base(db)
    saved, error = site.set_base(db, request.form.get("site_public_url"))
    if error:
        flash(error, "error")
        return redirect(url_for("admin.dashboard"))
    db.commit()
    if not saved:
        flash("Site address cleared. Links will fall back to whatever address you happen to be using.", "warning")
        return redirect(url_for("admin.dashboard"))

    moved, repictured = [], 0
    if integrations.is_configured(db, "stripe") and previous and previous != saved:
        #  A product picture was handed to Stripe as a full address, and
        #  Stripe keeps its own copy of that address — so a domain change
        #  leaves the payment page fetching pictures from a host that has
        #  moved. Nothing else in this app stores an absolute link to
        #  itself; this is the one thing that lives on someone else's
        #  server and has to be told.
        products, _ = integrations.stripe_products(db)
        for product in products:
            image = product.get("image") or ""
            if image.startswith(previous):
                ok, _ = integrations.stripe_update_product(
                    db, product["product_id"], image_url=saved + image[len(previous):])
                repictured += 1 if ok else 0
    if integrations.is_configured(db, "stripe"):
        wanted = saved + url_for("public.stripe_webhook")
        hooks, hook_error = integrations.stripe_webhooks(db)
        for hook in hooks or []:
            if hook.get("url") and hook["url"] != wanted and "/stripe/webhook" in hook["url"]:
                ok, message = integrations.stripe_update_webhook(db, hook["id"], wanted)
                moved.append(message if not ok else hook["url"])
    #  A local address is worth saying so about EVEN IF the webhook moved
    #  successfully — Stripe now calling back on localhost is a worse
    #  outcome than it calling back on the old domain, not a better one.
    if not site.is_public_host(saved):
        note = " Stripe's callback was moved there too." if moved else ""
        flash("Saved — but that address only works on this machine or network, so links we "
              "email and Stripe's return address won't work for anyone else." + note, "warning")
    else:
        parts = ["Site address saved."]
        if moved:
            parts.append(f"Stripe now calls back on the new domain (was {moved[0]}).")
        if repictured:
            parts.append(f"{repictured} product picture{'s' if repictured != 1 else ''} re-pointed at it.")
        if not moved and not repictured:
            parts.append("Emails, Stripe returns and product pictures will all use it.")
        flash(" ".join(parts), "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/commerce/products/add", methods=["POST"])
@login_required
def commerce_product_add():
    """Creates a product in Stripe from this site -- name, price, picture --
    and, in the same submit, records what a sale of it DELIVERS from the
    Type field on the form. The owner never opens the Stripe dashboard, and
    never has to come back to a second screen to say what the product is."""
    db = get_db()
    image_url, image_error = _picture_for_product()
    if image_error:
        flash(image_error, "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    price_id, error = integrations.stripe_create_product(
        db,
        request.form.get("name"),
        request.form.get("description") or "",
        _money_to_cents(request.form.get("amount")),
        integrations.base_currency(db),
        request.form.get("interval") or "",
        image_url,
    )
    if error:
        flash(f"Stripe wouldn't accept that — {integrations.explain(error, 'Stripe')}", "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    #  The product exists now; set what it delivers from the same form. If
    #  the type's fields are incomplete (a download with no file), the
    #  product is still created -- as payment-only -- and the owner is told
    #  what to finish, rather than losing the product they just made.
    ok, ferr = _save_fulfilment(db, price_id)
    db.commit()
    if not ok:
        flash("Product created — but " + ferr[0].lower() + ferr[1:], "warning")
    else:
        flash("Product created.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/currency", methods=["POST"])
@login_required
def commerce_currency():
    """What this shop charges in.

    Changing it does NOT reprice anything: a Stripe price is immutable
    and its currency is part of it, so an existing product keeps what it
    was created with and the screen says so. This decides what the NEXT
    product is priced in.
    """
    db = get_db()
    saved, error = integrations.set_base_currency(db, request.form.get("base_currency"))
    if error:
        flash(error, "error")
    else:
        db.commit()
        flash("New products will be priced in %s. Anything already on sale keeps the "
              "currency it was created with." % saved.upper(), "success")
    return redirect(url_for("admin.commerce_settings"))


@bp.route("/commerce/products/<product_id>/save", methods=["POST"])
@login_required
def commerce_product_save(product_id):
    """Edits a product, including its price.

    Stripe prices are immutable — this is the wall an owner hits in the
    dashboard ("this price has been used, you can't change it"). So a
    changed amount here becomes a new price, made default, with the old
    one retired, and the fulfilment rule moved across so the new price
    still delivers whatever the old one did. To the owner it is simply
    "the price is now 15.00".
    """
    db = get_db()
    #  Replacing a picture takes the same two routes as adding one.
    image_url, image_error = _picture_for_product()
    if image_error:
        flash(image_error, "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    ok, error = integrations.stripe_update_product(
        db, product_id,
        name=request.form.get("name"),
        description=request.form.get("description") or "",
        image_url=image_url,
    )
    if not ok:
        flash(f"Stripe wouldn't accept that — {integrations.explain(error, 'Stripe')}", "error")
        return redirect(url_for("admin.commerce_fulfilment"))

    old_price_id = (request.form.get("price_id") or "").strip()
    amount = _money_to_cents(request.form.get("amount"))
    interval = request.form.get("interval") or ""
    currency = ((request.form.get("current_currency") or "").strip().lower()
                or integrations.base_currency(db))
    was = request.form.get("current_amount", type=int)
    final_price_id = old_price_id
    repriced = False
    if amount and (amount != was or interval != (request.form.get("current_interval") or "")):
        new_price_id, error = integrations.stripe_reprice(
            db, product_id, old_price_id, amount, currency, interval)
        if error:
            flash(f"The price could not be changed — {integrations.explain(error, 'Stripe')}", "error")
            return redirect(url_for("admin.commerce_fulfilment"))
        if new_price_id:
            #  The rule is keyed by price. The retired price's rule goes;
            #  this submit's Type is written to the NEW price just below, so
            #  the new price delivers exactly what the form now says --
            #  never a stale copy of the old one.
            final_price_id = new_price_id
            repriced = True
            db.execute("DELETE FROM fulfilment_rules WHERE price_id = ?", (old_price_id,))
    #  What it delivers, from the Type field on this same form.
    ok, ferr = _save_fulfilment(db, final_price_id)
    if not ok:
        db.commit()
        flash(ferr, "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    db.commit()
    flash("Saved. The new price is live and the old one retired." if repriced else "Saved.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/products/<product_id>/archive", methods=["POST"])
@login_required
def commerce_product_archive(product_id):
    db = get_db()
    active = request.form.get("active") == "1"
    ok, error = integrations.stripe_archive_product(db, product_id, active)
    flash(error if not ok else ("Back on sale." if active else "Taken off sale."),
          "error" if not ok else "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/shipping/free-over", methods=["POST"])
@login_required
def commerce_shipping_free_over():
    """The spend above which delivery is free, shop-wide. Entered in whole
    currency, stored the way Stripe counts. 0 (or blank) means never."""
    db = get_db()
    value = (request.form.get("free_over") or "").strip().replace(",", ".")
    try:
        cents = str(int(round(float(value) * 100))) if value else "0"
    except ValueError:
        cents = "0"
    _set_setting(db, cart.FREE_OVER_KEY, cents)
    db.commit()
    flash("Saved when delivery becomes free.", "success")
    return redirect(url_for("admin.commerce_settings"))


@bp.route("/commerce/shipping/service/save", methods=["POST"])
@login_required
def commerce_shipping_service_save():
    """Create or update a delivery service and its whole weight-band table
    at once.

    Weights are entered in kilograms for the owner and stored in grams;
    prices in whole currency, stored in the smallest unit. A band with
    both boxes blank is a spare row and simply dropped, so "add a row"
    can leave an empty one behind without consequence.
    """
    db = get_db()
    sid = request.form.get("service_id", type=int)
    name = (request.form.get("name") or "").strip()
    carrier = (request.form.get("carrier") or "").strip()
    zone = (request.form.get("zone") or "ch").strip()
    if zone not in integrations.SHIPPING_ZONES:
        zone = "ch"
    enabled = request.form.get("enabled") == "1"
    if not name:
        flash("Give the delivery service a name.", "error")
        return redirect(url_for("admin.commerce_settings"))
    if sid and shipping.get_service(db, sid):
        shipping.update_service(db, sid, name=name, carrier=carrier, zone=zone, enabled=enabled)
    else:
        sid = shipping.create_service(db, name, carrier, zone)
        shipping.update_service(db, sid, enabled=enabled)
    bands = []
    for up, amt in zip(request.form.getlist("band_up_to"), request.form.getlist("band_amount")):
        up = (up or "").strip().replace(",", ".")
        amt = (amt or "").strip().replace(",", ".")
        if not up and not amt:
            continue
        try:
            bands.append((int(round(float(up) * 1000)), int(round(float(amt) * 100))))
        except ValueError:
            continue
    shipping.set_rates(db, sid, bands)
    db.commit()
    flash("Delivery service saved.", "success")
    return redirect(url_for("admin.commerce_settings"))


@bp.route("/commerce/shipping/service/<int:service_id>/delete", methods=["POST"])
@login_required
def commerce_shipping_service_delete(service_id):
    """Remove a delivery service, presets included -- nothing installed as a
    starting point is permanent, and the one-time seed flag means a deleted
    one does not return on the next boot."""
    db = get_db()
    shipping.delete_service(db, service_id)
    db.commit()
    flash("Delivery service removed.", "success")
    return redirect(url_for("admin.commerce_settings"))


def _save_fulfilment(db, price_id):
    """Write (or clear) a product's fulfilment rule from the delivery TYPE
    and its fields on the current form. Returns (ok, error_message).

    This is not a route of its own any more: the type is a field IN the
    product form (Add and Edit), so it is saved in the same submit that
    creates or edits the product -- the owner picks a type and fills the
    fields that type needs, and one save does the lot. The caller commits.
    """
    kind = (request.form.get("kind") or "").strip()
    if kind not in ("credit", "physical", "download"):
        #  "Nothing extra" is expressed by having no rule at all, so the
        #  payment handler simply finds nothing to grant.
        db.execute("DELETE FROM fulfilment_rules WHERE price_id = ?", (price_id,))
        return True, None
    quantity = max(1, request.form.get("quantity", type=int) or 1)
    ref = (request.form.get("ref") or "").strip() or None
    stock = request.form.get("stock", type=int)
    if kind == "credit" and not ref:
        return False, "Choose which meeting these sessions can be booked against."
    if kind == "download":
        #  Say which file this delivers either way: a new upload wins (it
        #  is added to the shop's files, reusable on another product), or a
        #  file already uploaded is chosen from the list.
        up = request.files.get("download_file")
        if up and up.filename:
            file_id, up_error = downloads.save_upload(db, up)
            if up_error:
                return False, up_error
            ref = str(file_id)
        if not ref:
            return False, "Upload a file to sell, or choose one you have already uploaded."
    #  A posted product carries a weight (kg in, grams stored) that its
    #  delivery is priced from, and may name the service it ships by --
    #  otherwise the shop's services all apply. Only meaningful for the
    #  physical kind; cleared for the others so a changed type leaves
    #  nothing stale behind.
    weight_g = None
    service_id = None
    if kind == "physical":
        kg = (request.form.get("weight_kg") or "").strip().replace(",", ".")
        try:
            weight_g = int(round(float(kg) * 1000)) if kg else None
        except ValueError:
            weight_g = None
        service_id = request.form.get("shipping_service_id", type=int) or None
    db.execute(
        "INSERT INTO fulfilment_rules (price_id, kind, ref, quantity, stock, weight_g, shipping_service_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(price_id) DO UPDATE SET kind = excluded.kind, ref = excluded.ref, "
        "quantity = excluded.quantity, stock = excluded.stock, "
        "weight_g = excluded.weight_g, shipping_service_id = excluded.shipping_service_id",
        (price_id, kind, ref, quantity, stock if kind == "physical" else None, weight_g, service_id),
    )
    return True, None


@bp.route("/commerce/credit-expiry", methods=["POST"])
@login_required
def commerce_credit_expiry():
    """Credits never expire unless the owner turns this on. Twelve months
    is offered as the usual term, but nothing expires by default: a buyer
    who paid for ten sessions has paid for ten sessions."""
    db = get_db()
    months = request.form.get("months", type=int) or 0
    _set_setting(db, "commerce_credit_expiry_months", str(max(0, months)))
    db.commit()
    flash("Session credits never expire." if months <= 0
          else f"Session credits now expire {months} months after purchase.", "success")
    return redirect(url_for("admin.commerce_settings"))


@bp.route("/commerce/download-expiry", methods=["POST"])
@login_required
def commerce_download_expiry():
    """How long a paid file stays downloadable.

    Its own term, not the session one: a session is something the owner
    will honour, a download is something they have to keep hosting, and
    those are different promises.
    """
    db = get_db()
    days = request.form.get("days", type=int)
    days = 0 if days is None or days < 0 else days
    _set_setting(db, "commerce_download_expiry_days", str(days))
    db.commit()
    flash("Paid files never stop being downloadable." if days == 0
          else f"Buyers can download what they paid for for {days} days.", "success")
    return redirect(url_for("admin.commerce_settings"))


@bp.route("/settings/integrations", methods=["GET"])
@login_required
def settings_integrations():
    """One panel for every third-party provider. See services/integrations
    for why this is a registry rather than a page per provider."""
    db = get_db()
    #  Which tab is open. A query rather than three routes: one route, one
    #  template, and an address that can still be bookmarked or linked to.
    #  An unknown value falls back rather than 404ing -- a tab is a view of
    #  a page, not a page of its own.
    tab = (request.args.get("tab") or "").strip().lower()
    if tab not in ("stripe", "calcom", "ai"):
        tab = "stripe"
    return render_template(
        "admin/settings_integrations.html",
        tab=tab,
        #  The AI card lives on this page too -- see the partial for why.
        #  Prefixed, because `providers` already means something here.
        ai_settings=assistant.get_ai_settings(db),
        ai_providers=assistant.AI_PROVIDERS,
        ai_provider_labels=assistant.PROVIDER_LABELS,
        providers=integrations.PROVIDERS,
        values={key: integrations.get_provider_settings(db, key) for key in integrations.PROVIDERS},
        configured={key: integrations.is_configured(db, key) for key in integrations.PROVIDERS},
        verified={key: integrations.is_verified(db, key) for key in integrations.PROVIDERS},
        stripe_mode=integrations.stripe_mode(db),
        webhook_url=site.absolute(db, url_for("public.stripe_webhook"), request.host_url),
        site_base=site.public_base(db),
        site_is_public=site.is_public_host(site.public_base(db, request.host_url)),
        stripe_webhooks=(integrations.stripe_webhooks(db)[0] if integrations.is_configured(db, "stripe") else []),
        #  What this site acts on that Stripe is not sending it. An
        #  endpoint keeps the events it was created with, so a feature
        #  needing a new one works on new installs and does nothing on
        #  every existing one unless somebody is told.
        webhook_missing=(integrations.webhook_missing_events(
            db, site.absolute(db, url_for("public.stripe_webhook"), request.host_url))[0]
            if integrations.is_configured(db, "stripe") else []),
        storage_problem=bootstrap.storage_problems(db),
        key_source=crypto.key_source(),
    )


@bp.route("/settings/integrations/<provider>", methods=["POST"])
@login_required
def settings_integration_save(provider):
    db = get_db()
    if provider not in integrations.PROVIDERS:
        flash("Unknown provider.", "error")
        return redirect(url_for("admin.settings_integrations"))
    integrations.save_provider_settings(db, provider, request.form)
    name = integrations.PROVIDERS[provider]["name"]
    #  Then try it, because a key that is stored and a key that works are
    #  different things and only one of them is worth being told about.
    #  This is where an install that cannot reach the internet finds out,
    #  rather than months later when the first order does not arrive.
    if integrations.is_configured(db, provider):
        ok, message = integrations.test_connection(db, provider)
        integrations.record_test(db, provider, ok)
        db.commit()
        flash("%s saved. %s" % (name, message), "success" if ok else "error")
    else:
        integrations.record_test(db, provider, False)
        db.commit()
        flash("%s settings saved." % name, "success")
    return redirect(url_for("admin.settings_integrations", tab=provider))


@bp.route("/settings/integrations/<provider>/test", methods=["POST"])
@login_required
def settings_integration_test(provider):
    """Reads something the admin will recognise — their own products,
    their own event types — so a pass proves the key reaches the right
    account rather than merely being well-formed."""
    db = get_db()
    if provider not in integrations.PROVIDERS:
        return jsonify({"ok": False, "message": "Unknown provider."}), 404
    ok, message = integrations.test_connection(db, provider)
    #  Recorded, so the badge on this page agrees with what the button
    #  just said rather than contradicting it.
    integrations.record_test(db, provider, ok)
    db.commit()
    return jsonify({"ok": ok, "message": message})


@bp.route("/settings/integrations/stripe/webhook", methods=["POST"])
@login_required
def settings_stripe_webhook():
    """Registers this site with Stripe over the API, which is also the
    only moment Stripe ever reveals the signing secret — so doing it here
    removes the copy-paste step where a mistyped secret produces webhooks
    that fail verification for no visible reason."""
    db = get_db()
    url = ((request.form.get("webhook_url") or "").strip()
           or site.absolute(db, url_for("public.stripe_webhook"), request.host_url))
    ok, message = integrations.stripe_create_webhook(db, url)
    return jsonify({"ok": ok, "message": message})


@bp.route("/settings/integrations/stripe/sync", methods=["POST"])
@login_required
def settings_stripe_sync():
    """Pulls recent paid checkouts from Stripe and records anything
    missed. The counterpart to the webhook, and the whole answer while
    this site has no public address for Stripe to reach."""
    db = get_db()
    from ...routes.public import _credit_expiry_at
    recorded, checked, error = commerce.reconcile_stripe(
        db, integrations, credit_expiry_at=_credit_expiry_at(db)
    )
    if error:
        return jsonify({"ok": False, "message": f"Couldn't read orders from Stripe — {integrations.explain(error, 'Stripe')}"})
    if recorded:
        return jsonify({"ok": True, "message": f"Checked the last {checked} checkouts and recorded {recorded} new order(s)."})
    return jsonify({"ok": True, "message": f"Checked the last {checked} checkouts — nothing new to record."})


@bp.route("/settings/integrations/<provider>/disconnect", methods=["POST"])
@login_required
def settings_integration_disconnect(provider):
    db = get_db()
    if provider in integrations.PROVIDERS:
        integrations.clear_provider(db, provider)
        flash(f"{integrations.PROVIDERS[provider]['name']} disconnected.", "success")
    return redirect(url_for("admin.settings_integrations"))


@bp.route("/settings/ai", methods=["GET", "POST"])
@login_required
def settings_ai():
    """Where the AI card SAVES. It is shown on the Connections page beside
    Stripe and Cal.com, because all three answer the same question -- what
    does this site talk to, and with what key -- and only this one used to
    have a screen of its own, for no better reason than being written
    first.

    A GET is an old link or a bookmark, so it lands on the card rather
    than rendering a second copy of it.
    """
    db = get_db()
    if request.method == "POST":
        assistant.save_ai_settings(db, request.form)
        flash("AI settings saved.", "success")
        return redirect(url_for("admin.settings_integrations", tab="ai"))
    return redirect(url_for("admin.settings_integrations", tab="ai"))


@bp.route("/settings/ai/models", methods=["POST"])
@login_required
def settings_ai_models():
    """AJAX-only, from the Settings page's "Load Models" buttons — takes
    url/key straight from the form (not the saved DB values) so an admin
    can test a change before clicking Save. A blank key field falls back
    to whatever's already saved, same "blank = keep existing" convention
    as the rest of this page, so testing doesn't require re-typing an
    already-saved key."""
    provider = request.form.get("provider", "")
    url = request.form.get("url", "").strip()
    api_key = request.form.get("api_key", "").strip()
    if not api_key:
        db = get_db()
        saved = assistant.get_ai_settings(db)
        api_key = {"openwebui": saved["openwebui_api_key"], "gemini": saved["gemini_api_key"]}.get(provider, "")
    try:
        models = assistant.list_models(provider, url, api_key)
    except assistant.ProviderError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"models": models})


@bp.route("/settings/google", methods=["POST"])
@login_required
def settings_google():
    # Admin management (this + the two routes below) lives on the Account
    # page now — "who can sign in and how" is one topic, not split across
    # separate pages. These stay POST-only action endpoints; GET here has
    # nothing of its own to show.
    db = get_db()
    save_google_settings(db, request.form)
    flash("Google Sign-In settings saved.", "success")
    return redirect(url_for("auth.account"))


# ---------- Admins (multiple people can manage this site — see the Account page) ----------

@bp.route("/admins", methods=["POST"])
@login_required
def admins():
    db = get_db()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    google_email = request.form.get("google_email", "").strip().lower()
    if not username or len(password) < 6:
        flash("Username is required and password must be at least 6 characters.", "error")
    elif db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        flash(f'Username "{username}" is already taken.', "error")
    elif google_email and db.execute("SELECT 1 FROM users WHERE google_email = ?", (google_email,)).fetchone():
        flash(f'"{google_email}" is already linked to another admin.', "error")
    else:
        db.execute(
            "INSERT INTO users (username, password_hash, google_email) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), google_email or None),
        )
        db.commit()
        flash(f'Admin "{username}" added.', "success")
    return redirect(url_for("auth.account"))


@bp.route("/admins/<int:user_id>/delete", methods=["POST"])
@login_required
def admin_delete(user_id):
    db = get_db()
    if user_id == session.get("user_id"):
        flash("You can't remove your own admin account while logged in as it — have another admin remove it.", "error")
        return redirect(url_for("auth.account"))
    count = db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count <= 1:
        flash("Can't remove the last remaining admin account.", "error")
        return redirect(url_for("auth.account"))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("Admin removed.", "success")
    return redirect(url_for("auth.account"))





