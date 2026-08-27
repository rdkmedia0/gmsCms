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
from ...services.sections import _save_card_image_file
from ...services import integrations, commerce, downloads, cart, site
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

    orders = []
    for row in rows:
        names = bought(row)
        if what and what not in [n for n, _ in names]:
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

    entitlements = {}
    for row in db.execute("SELECT * FROM entitlements ORDER BY id").fetchall():
        entitlements.setdefault(row["order_id"], []).append(row)
    return render_template(
        "admin/commerce_orders.html",
        orders=orders,
        entitlements=entitlements,
        buyers=buyers,
        products=products,
        filters={"who": who, "what": what, "since": since, "until": until},
        filtered=bool(who or what or since or until),
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
    catalogue, cat_error = ([], None)
    products, product_error = ([], None)
    if integrations.is_configured(db, "stripe"):
        catalogue, cat_error = integrations.stripe_catalogue_cached(db)
        products, product_error = integrations.stripe_products(db)
        cat_error = integrations.explain(cat_error, "Stripe")
        product_error = integrations.explain(product_error, "Stripe")
    event_types, ev_error = ([], None)
    if integrations.is_configured(db, "calcom"):
        event_types, ev_error = integrations.calcom_event_types(db)
        ev_error = integrations.explain(ev_error, "Cal.com")
    rules = {
        r["price_id"]: r
        for r in db.execute("SELECT * FROM fulfilment_rules").fetchall()
    }
    download_row = db.execute(
        "SELECT value FROM settings WHERE key = 'commerce_download_expiry_days'"
    ).fetchone()
    expiry_row = db.execute(
        "SELECT value FROM settings WHERE key = 'commerce_credit_expiry_months'"
    ).fetchone()
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
        postage=cart.shipping_settings(db),
        products=products,
        product_error=product_error,
        currencies=integrations.CURRENCIES,
        intervals=integrations.INTERVALS,
        public_url=bool((get_email_settings(db).get("site_public_url") or "").strip()),
        zones=integrations.SHIPPING_ZONES,
        catalogue=catalogue,
        catalogue_error=cat_error,
        event_types=event_types,
        event_error=ev_error,
        rules=rules,
        stripe_ready=integrations.is_configured(db, "stripe"),
        calcom_ready=integrations.is_configured(db, "calcom"),
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
    """Creates a product in Stripe from this site, so the owner never has
    to open the Stripe dashboard to put something on sale."""
    db = get_db()
    image_url, image_error = _product_image_url()
    if image_error:
        flash(image_error, "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    price_id, error = integrations.stripe_create_product(
        db,
        request.form.get("name"),
        request.form.get("description") or "",
        _money_to_cents(request.form.get("amount")),
        request.form.get("currency") or "chf",
        request.form.get("interval") or "",
        image_url,
    )
    if error:
        flash(f"Stripe wouldn't accept that — {integrations.explain(error, 'Stripe')}", "error")
    else:
        flash("Product created. Now say what it delivers.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


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
    image_url, image_error = _product_image_url()
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
    currency = (request.form.get("currency") or "chf").lower()
    was = request.form.get("current_amount", type=int)
    if amount and (amount != was or interval != (request.form.get("current_interval") or "")):
        new_price_id, error = integrations.stripe_reprice(
            db, product_id, old_price_id, amount, currency, interval)
        if error:
            flash(f"The price could not be changed — {integrations.explain(error, 'Stripe')}", "error")
            return redirect(url_for("admin.commerce_fulfilment"))
        if old_price_id and new_price_id:
            #  The rule says what a sale delivers, and it is keyed by
            #  price. Leaving it on the retired price would mean the next
            #  buyer paid and got nothing.
            db.execute("DELETE FROM fulfilment_rules WHERE price_id = ?", (new_price_id,))
            db.execute("UPDATE fulfilment_rules SET price_id = ? WHERE price_id = ?",
                       (new_price_id, old_price_id))
            db.commit()
        flash("Saved. The new price is live and the old one retired.", "success")
    else:
        flash("Saved.", "success")
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


@bp.route("/commerce/postage", methods=["POST"])
@login_required
def commerce_postage():
    """What delivery costs, and where the shop will post to.

    Kept here rather than in Stripe because it has to be known BEFORE
    checkout starts: the basket shows the buyer what postage will be, and
    Stripe is then told the same figure. Amounts are entered in whole
    currency and stored in the smallest unit, the way Stripe counts.
    """
    db = get_db()
    def _cents(field):
        value = (request.form.get(field) or "").strip().replace(",", ".")
        try:
            return str(int(round(float(value) * 100))) if value else "0"
        except ValueError:
            return "0"
    zone = (request.form.get("zone") or "ch").strip()
    if zone not in integrations.SHIPPING_ZONES:
        zone = "ch"
    _set_setting(db, "shop_shipping_zone", zone)
    _set_setting(db, "shop_shipping_amount", _cents("amount"))
    _set_setting(db, "shop_free_over", _cents("free_over"))
    _set_setting(db, "shop_shipping_label", (request.form.get("label") or "Standard delivery").strip())
    db.commit()
    flash("Delivery settings saved.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/files/upload", methods=["POST"])
@login_required
def commerce_file_upload():
    """Adds a file to the ones this site can sell.

    It goes under DATA_DIR rather than static/uploads, so it has no URL of
    its own at all — see services/downloads.py for why that is the whole
    point.
    """
    db = get_db()
    file_id, error = downloads.save_upload(db, request.files.get("file"))
    if error:
        flash(error, "error")
    else:
        db.commit()
        flash("File added. Now choose it on whichever product sends it.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/files/<int:file_id>/delete", methods=["POST"])
@login_required
def commerce_file_delete(file_id):
    db = get_db()
    ok, error = downloads.delete_file(db, file_id)
    db.commit()
    flash(error if error else "File deleted.", "error" if error else "success")
    return redirect(url_for("admin.commerce_fulfilment"))


@bp.route("/commerce/fulfilment/save", methods=["POST"])
@login_required
def commerce_fulfilment_save():
    db = get_db()
    price_id = (request.form.get("price_id") or "").strip()
    kind = (request.form.get("kind") or "").strip()
    if not price_id:
        flash("No product was selected.", "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    if kind not in ("credit", "physical", "download"):
        #  "Nothing extra" is expressed by having no rule at all, so the
        #  payment handler simply finds nothing to grant.
        db.execute("DELETE FROM fulfilment_rules WHERE price_id = ?", (price_id,))
        db.commit()
        flash("This product now just takes the payment, with nothing to unlock.", "success")
        return redirect(url_for("admin.commerce_fulfilment"))
    quantity = max(1, request.form.get("quantity", type=int) or 1)
    ref = (request.form.get("ref") or "").strip() or None
    stock = request.form.get("stock", type=int)
    if kind == "credit" and not ref:
        flash("Choose which meeting these sessions can be booked against.", "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    if kind == "download" and not ref:
        flash("Choose which file this product sends.", "error")
        return redirect(url_for("admin.commerce_fulfilment"))
    db.execute(
        "INSERT INTO fulfilment_rules (price_id, kind, ref, quantity, stock) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(price_id) DO UPDATE SET kind = excluded.kind, ref = excluded.ref, "
        "quantity = excluded.quantity, stock = excluded.stock",
        (price_id, kind, ref, quantity, stock if kind == "physical" else None),
    )
    db.commit()
    flash("Saved what this product delivers.", "success")
    return redirect(url_for("admin.commerce_fulfilment"))


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
    return redirect(url_for("admin.commerce_fulfilment"))


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
    return redirect(url_for("admin.commerce_fulfilment"))


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





