"""
Turning a completed payment into something the buyer is owed.

The shape of this module follows one rule: **the browser coming back is
not proof of payment.** A visitor can reach the thank-you page without
paying, and a paying visitor can close the tab before it loads. So an
order is only ever written from what the PROVIDER says, never from what
the returning browser claims.

There are three ways that truth arrives, and all of them funnel through
record_checkout, which is keyed on the session id and therefore safe to
run twice:

  * a signed webhook (the push, once there is a public address for one),
  * the thank-you page looking the session up as the buyer lands on it,
  * reconcile_stripe pulling recent checkouts on demand.

The last two are what make this work with no webhook configured at all —
which is the normal state of a site still in development.

There are no customer accounts. A buyer is identified by the email
Stripe collected at checkout, and reaches their downloads or their
remaining sessions through a signed emailed link. "No accounts" is not
"no customer data" — the ledger below is exactly that data, kept to the
minimum that makes a re-downloadable file or a package of sessions
possible at all.
"""
import datetime
import hashlib
import hmac
import json
import secrets
import time

from werkzeug.security import check_password_hash, generate_password_hash

from .. import crypto

#  Stripe signs with a timestamp inside the signed payload specifically so
#  a captured request cannot be replayed later. Five minutes is Stripe's
#  own documented default tolerance.
SIGNATURE_TOLERANCE_S = 300

KIND_DOWNLOAD = "download"
KIND_CREDIT = "credit"
FULFILMENT_KINDS = (KIND_DOWNLOAD, KIND_CREDIT, "physical")


class WebhookError(Exception):
    """Raised when a payload cannot be trusted. The route turns this into
    a 400 without acting on anything the payload claimed."""


def verify_stripe_signature(payload, signature_header, secret, tolerance=SIGNATURE_TOLERANCE_S, now=None):
    """Returns the parsed event, or raises WebhookError.

    This is what replaces the app-wide Origin/Referer CSRF check for this
    one route (see csrf.py's exemption list): Stripe is not a browser and
    sends no Origin, so the proof that a request is genuine has to be
    cryptographic instead. Anything that fails here is rejected before a
    single field of the payload is read.
    """
    if not secret:
        raise WebhookError("No webhook signing secret is configured.")
    if not signature_header:
        raise WebhookError("Missing signature header.")

    parts = {}
    for chunk in signature_header.split(","):
        key, _, value = chunk.strip().partition("=")
        if key == "v1":
            parts.setdefault("v1", []).append(value)
        elif key:
            parts[key] = value
    timestamp = parts.get("t")
    signatures = parts.get("v1") or []
    if not timestamp or not signatures:
        raise WebhookError("Malformed signature header.")

    try:
        sent_at = int(timestamp)
    except ValueError:
        raise WebhookError("Malformed signature timestamp.")
    if abs((now or time.time()) - sent_at) > tolerance:
        raise WebhookError("Signature timestamp is outside the tolerance window.")

    body = payload.decode() if isinstance(payload, bytes) else payload
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    #  compare_digest, not ==, so a wrong signature cannot be discovered
    #  one character at a time by timing the response.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise WebhookError("Signature does not match.")

    try:
        return json.loads(body)
    except ValueError:
        raise WebhookError("Payload is not valid JSON.")


def already_processed(db, provider, event_id):
    """True if this exact event has been handled before. Stripe retries
    on any non-2xx and will happily deliver the same event twice on a
    slow response, so every handler has to be safe to run once."""
    if not event_id:
        return False
    return db.execute(
        "SELECT 1 FROM webhook_events WHERE provider = ? AND event_id = ?",
        (provider, event_id),
    ).fetchone() is not None


def record_event(db, provider, event_id, event_type):
    db.execute(
        "INSERT OR IGNORE INTO webhook_events (provider, event_id, event_type) VALUES (?, ?, ?)",
        (provider, event_id, event_type),
    )


def upsert_customer(db, email, name=None):
    """The ledger key. Email arrives from Stripe, already validated by the
    checkout the buyer just completed, so it is never typed here."""
    email = (email or "").strip().lower()
    if not email:
        return None
    row = db.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
    if row:
        if name:
            db.execute(
                "UPDATE customers SET name = COALESCE(NULLIF(?, ''), name) WHERE id = ?",
                (name, row["id"]),
            )
        return row["id"]
    cur = db.execute("INSERT INTO customers (email, name) VALUES (?, ?)", (email, name or None))
    return cur.lastrowid


def fulfilment_rule(db, price_id):
    if not price_id:
        return None
    return db.execute("SELECT * FROM fulfilment_rules WHERE price_id = ?", (price_id,)).fetchone()


def grant_for_line_item(db, customer_id, order_id, price_id, quantity, expires_at=None):
    """Applies whatever the admin said this price delivers. Returns the
    entitlement kind granted, or None when the price has no rule — which
    is the normal case for a plain physical item that needs no unlocking."""
    rule = fulfilment_rule(db, price_id)
    if not rule or rule["kind"] not in FULFILMENT_KINDS:
        return None
    count = max(1, int(quantity or 1))
    #  Stock is only ever set on a physical item, and this used to sit
    #  below an early return that fired for exactly that kind -- so the
    #  one line maintaining the count could never run, and "3 left" stayed
    #  3 however many were sold. Counted first, for every kind that has
    #  one, so no later branch can strand it again.
    if rule["stock"] is not None:
        #  Stock lives here because Stripe has no such field at all.
        db.execute(
            "UPDATE fulfilment_rules SET stock = MAX(0, stock - ?) WHERE id = ?",
            (count, rule["id"]),
        )
    #  A posted item is recorded like anything else a sale owes somebody.
    #  The buyer's page ignores this kind -- there is nothing for them to
    #  claim -- but the owner has to see that something needs posting,
    #  which "nothing to unlock, this was payment only" actively hid.
    granted = (rule["quantity"] or 1) * count if rule["kind"] != "physical" else count
    db.execute(
        "INSERT INTO entitlements (customer_id, order_id, kind, ref, granted, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (customer_id, order_id, rule["kind"], rule["ref"], granted,
         #  Sessions take the owner's own term; a download takes the
         #  hosting one, which is a different promise about a different
         #  thing. Neither belongs to a posted item.
         expires_at if rule["kind"] == KIND_CREDIT
         else (download_expiry_at(db) if rule["kind"] == KIND_DOWNLOAD else None)),
    )
    return rule["kind"]


def record_checkout(db, session, line_items, credit_expiry_at=None):
    """Writes the order and everything it entitles the buyer to.

    Returns (order_id, created) — `created` is False when this session had
    already been recorded, which is how a replayed webhook stays harmless
    even if the event id check above were somehow bypassed.
    """
    provider_ref = session.get("id")
    if not provider_ref:
        raise WebhookError("Checkout session had no id.")
    existing = db.execute(
        "SELECT id FROM orders WHERE provider_ref = ?", (provider_ref,)
    ).fetchone()
    if existing:
        return existing["id"], False

    details = session.get("customer_details") or {}
    customer_id = upsert_customer(db, details.get("email"), details.get("name"))
    cur = db.execute(
        "INSERT INTO orders (provider, provider_ref, customer_id, amount_total, currency, status, line_items) "
        "VALUES ('stripe', ?, ?, ?, ?, ?, ?)",
        (
            provider_ref,
            customer_id,
            session.get("amount_total"),
            (session.get("currency") or "").lower() or None,
            "paid" if session.get("payment_status") == "paid" else (session.get("payment_status") or "pending"),
            json.dumps(line_items or []),
        ),
    )
    order_id = cur.lastrowid
    if customer_id:
        for item in line_items or []:
            price_id = ((item.get("price") or {}).get("id")) or item.get("price_id")
            grant_for_line_item(
                db, customer_id, order_id, price_id, item.get("quantity") or 1,
                expires_at=credit_expiry_at,
            )
    return order_id, True


def revoke_unused_for_order(db, order_id):
    """A refunded package must not stay bookable. Only the UNUSED portion
    is revoked — sessions already taken happened, and pretending otherwise
    would make the ledger disagree with the calendar."""
    db.execute(
        "UPDATE entitlements SET revoked_at = CURRENT_TIMESTAMP "
        "WHERE order_id = ? AND revoked_at IS NULL AND used < granted",
        (order_id,),
    )
    db.execute("UPDATE orders SET status = 'refunded' WHERE id = ?", (order_id,))


def order_by_ref(db, provider_ref):
    return db.execute("SELECT * FROM orders WHERE provider_ref = ?", (provider_ref,)).fetchone()


def balance_for(db, email, kind=KIND_CREDIT, ref=None):
    """What this buyer may still do. Expired and revoked rows are excluded
    here rather than deleted, so the history of what was sold survives."""
    email = (email or "").strip().lower()
    sql = (
        "SELECT COALESCE(SUM(e.granted - e.used), 0) AS remaining "
        "FROM entitlements e JOIN customers c ON c.id = e.customer_id "
        "WHERE c.email = ? AND e.kind = ? AND e.revoked_at IS NULL "
        "AND (e.expires_at IS NULL OR e.expires_at > CURRENT_TIMESTAMP) "
        "AND e.used < e.granted"
    )
    params = [email, kind]
    if ref:
        sql += " AND e.ref = ?"
        params.append(ref)
    row = db.execute(sql, params).fetchone()
    return row["remaining"] if row else 0


def reconcile_stripe(db, integrations, limit=25, credit_expiry_at=None):
    """Pulls recent paid checkouts from Stripe and records any this site
    has missed. Returns (recorded, checked, error).

    A webhook is a push, and a push can be missed — the endpoint was down,
    the site was mid-deploy, or (as during development) there is no public
    address for Stripe to reach at all. Pulling is the same truth from the
    other direction, and it makes the whole design work with no webhook
    configured whatsoever.

    Safe to run repeatedly: record_checkout skips a session already stored,
    so this can never double-grant an entitlement no matter how often it
    runs or how it overlaps with a webhook arriving for the same session.
    """
    data, error = integrations.stripe_call(
        db, f"/checkout/sessions?limit={limit}&expand[]=data.line_items"
    )
    if error:
        return 0, 0, error
    sessions = data.get("data", [])
    recorded = 0
    for session in sessions:
        if session.get("payment_status") != "paid":
            continue
        line_items = (session.get("line_items") or {}).get("data") or []
        _, created = record_checkout(db, session, line_items, credit_expiry_at=credit_expiry_at)
        if created:
            recorded += 1
    db.commit()
    return recorded, len(sessions), None


#  ---------------------------------------------------------------------
#  Reaching what you bought, without an account
#  ---------------------------------------------------------------------
ACCESS_TOKEN_DAYS = 30

#  A paid file is hosted by the owner, and nobody promises to host
#  anything forever. Thirty days is the default answer, said out loud to
#  the buyer rather than discovered when a link stops working. 0 means
#  never, for an owner who would rather promise forever.
DOWNLOAD_EXPIRY_DAYS_DEFAULT = 30


def create_access_token(db, customer_id, days=ACCESS_TOKEN_DAYS):
    """Returns the raw token to put in a link. Only its hash is stored, so
    a copy of this database cannot open anyone's page — the same reasoning
    a password reset follows, and the reason the token can never be shown
    again after the email goes out.

    Reusable until it expires rather than single-use: this is the buyer's
    way back to sessions they may spend over months, and a link that dies
    on first click would strand them.
    """
    token = secrets.token_urlsafe(32)
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    db.execute(
        "INSERT INTO access_tokens (customer_id, token_hash, token_enc, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (customer_id, hashlib.sha256(token.encode()).hexdigest(),
         crypto.encrypt(token),
         expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return token


def get_or_create_token(db, customer_id, days=ACCESS_TOKEN_DAYS):
    """The buyer's one link, minting it only if they have none live.

    Returns (token, is_new). One customer keeps ONE link for as long as it
    is valid, because a link that changes with every purchase is not a
    link anybody can keep -- which is what hash-only storage forced, since
    a hash cannot be turned back into a link to show again.

    So the token is also held encrypted (`crypto`, the same key the API
    keys use). The hash stays and is still what a lookup matches on. What
    changes is the threat model, stated plainly: a copy of the database
    alone used to be useless, and now a copy of the database TOGETHER with
    the encryption key would open a buyer's page. That is the bar this app
    already sets for the Stripe key sitting in the same file, and backups
    leave the key out by default for exactly this reason.
    """
    live = db.execute(
        "SELECT token_enc FROM access_tokens WHERE customer_id = ? "
        "AND expires_at > CURRENT_TIMESTAMP ORDER BY id DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    if live and live["token_enc"]:
        existing = crypto.decrypt(live["token_enc"])
        if existing:
            return existing, False
    #  A row from before this column existed, or one that will not decrypt:
    #  mint a fresh link rather than stranding the buyer. The old one keeps
    #  working until it expires.
    return create_access_token(db, customer_id, days), True


#  A buyer's optional lock on their own purchases page.
#
#  The link is still the credential; this is a second one, for somebody
#  who would rather a forwarded email did not open their orders. It is
#  deliberately not an account: no sign-up, no address to remember, no
#  reset mail to send -- if it is forgotten the owner clears it, which is
#  the same conversation they would have had anyway.
def download_expiry_at(db):
    """When a download bought right now stops being available, or None."""
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'commerce_download_expiry_days'"
    ).fetchone()
    try:
        days = int(row["value"]) if row and row["value"] not in (None, "")             else DOWNLOAD_EXPIRY_DAYS_DEFAULT
    except (TypeError, ValueError):
        days = DOWNLOAD_EXPIRY_DAYS_DEFAULT
    if days <= 0:
        return None
    return (datetime.datetime.utcnow()
            + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def set_page_password(db, customer_id, password):
    """Locks a buyer's page. An empty password clears the lock."""
    if not password:
        db.execute("UPDATE customers SET page_password_hash = NULL, page_lock_asked = 1 "
                   "WHERE id = ?", (customer_id,))
        return
    db.execute("UPDATE customers SET page_password_hash = ?, page_lock_asked = 1 WHERE id = ?",
               (generate_password_hash(password), customer_id))


def decline_page_password(db, customer_id):
    """Remembers that they were offered a lock and said no, so the offer
    is made once rather than on every visit."""
    db.execute("UPDATE customers SET page_lock_asked = 1 WHERE id = ?", (customer_id,))


def page_password_ok(db, customer_id, password):
    row = db.execute("SELECT page_password_hash FROM customers WHERE id = ?",
                     (customer_id,)).fetchone()
    if not row or not row["page_password_hash"]:
        return True
    return check_password_hash(row["page_password_hash"], password or "")


def customer_for_token(db, token):
    """The customer a link belongs to, or None if it is unknown, expired
    or tampered with. Looked up by hash, so the raw token never has to
    exist anywhere but the buyer's inbox."""
    if not token:
        return None
    row = db.execute(
        "SELECT c.* FROM access_tokens t JOIN customers c ON c.id = t.customer_id "
        "WHERE t.token_hash = ? AND t.expires_at > CURRENT_TIMESTAMP",
        (hashlib.sha256(token.encode()).hexdigest(),),
    ).fetchone()
    if row:
        #  Using the link pushes its expiry out again. A download never
        #  expires and sessions may be spent over months, so a link that
        #  died on a fixed date would strand somebody who did exactly what
        #  the email told them to do -- keep it. An abandoned link still
        #  ages out; one that is in use does not.
        db.execute(
            "UPDATE access_tokens SET last_used_at = CURRENT_TIMESTAMP, "
            "expires_at = datetime('now', ?) WHERE token_hash = ?",
            (f"+{ACCESS_TOKEN_DAYS} days", hashlib.sha256(token.encode()).hexdigest()),
        )
    return row


def entitlements_for(db, customer_id):
    """Everything this buyer may still do, newest first. Spent, revoked
    and expired rows are excluded here but kept in the table — the history
    of what was sold is worth more than the tidiness of deleting it."""
    return db.execute(
        #  The file's real name comes along for the ride: a buyer should
        #  see "Wedding Guide.pdf", not the id it happens to be stored
        #  under. Joined only for downloads, since `ref` means something
        #  different for a session credit.
        "SELECT e.*, f.original_name AS file_name FROM entitlements e "
        "LEFT JOIN digital_files f ON e.kind = 'download' AND f.id = CAST(e.ref AS INTEGER) "
        "WHERE e.customer_id = ? AND e.revoked_at IS NULL "
        "AND (e.expires_at IS NULL OR e.expires_at > CURRENT_TIMESTAMP) "
        "ORDER BY e.id DESC",
        (customer_id,),
    ).fetchall()


def orders_for(db, customer_id):
    return db.execute(
        "SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC", (customer_id,)
    ).fetchall()


def order_email_body(db, order, token_url, site_name):
    """Plain text on purpose: it renders everywhere, never trips a spam
    filter on markup, and the one thing that matters is the link."""
    lines = [
        f"Thanks for your order from {site_name}.",
        "",
    ]
    ents = entitlements_for(db, order["customer_id"])
    credits = sum(e["granted"] - e["used"] for e in ents if e["kind"] == KIND_CREDIT)
    downloads = [e for e in ents if e["kind"] == KIND_DOWNLOAD]
    if credits:
        lines.append(f"You have {credits} session{'s' if credits != 1 else ''} to book.")
    if downloads:
        left = sum(e["granted"] - e["used"] for e in downloads)
        lines.append(
            f"You have {len(downloads)} download{'s' if len(downloads) != 1 else ''} waiting"
            f" ({left} download{'s' if left != 1 else ''} left)."
        )
        #  The date, not a duration: "30 days" needs the reader to know
        #  when they bought it, and they are reading this weeks later.
        last = min((e["expires_at"] for e in downloads if e["expires_at"]), default=None)
        if last:
            lines.append(f"Please save {'them' if len(downloads) != 1 else 'it'} before "
                         f"{last[:10]} — we don't keep paid files up forever.")
    if credits or downloads:
        lines += ["", "Everything is here:", token_url, ""]
        #  Said plainly, because the next line tells them to keep the
        #  email: a link that quietly expires while they are keeping it is
        #  the worst version of this.
        lines.append(
            f"The link keeps working for {ACCESS_TOKEN_DAYS} days after the last time "
            "you use it, so opening it now and again is enough to keep it alive. "
            "If it ever stops working, reply to this email and we'll send a new one."
        )
    else:
        lines += ["", "We'll be in touch shortly.", ""]
    lines.append("Keep this email — the link above is how you get back to it.")
    return chr(10).join(lines)


def sale_notice_body(db, order, site_name):
    """What the OWNER needs to know about a sale, in the order they need
    it: what to do, then who, then what, then how much.

    There was no seller notification at all -- the only way to learn a
    sale had happened was to open the Orders screen and notice a new row.
    That is fine for a download, which delivers itself, and no good at all
    for something sitting in a cupboard waiting to be posted.
    """
    ents = entitlements_for(db, order["customer_id"]) if order["customer_id"] else []
    mine = [e for e in ents if e["order_id"] == order["id"]]
    to_post = sum(e["granted"] for e in mine if e["kind"] == "physical")
    lines = []
    if to_post:
        lines += [f"ACTION: post {to_post} item{'s' if to_post != 1 else ''}."
                  " The delivery address is on the payment in Stripe.", ""]
    else:
        lines += ["Nothing to post — this one delivers itself.", ""]
    try:
        items = json.loads(order["line_items"] or "[]")
    except (ValueError, TypeError):
        items = []
    bought = [f"{i.get('description') or 'item'} x{i.get('quantity') or 1}" for i in items]
    customer = db.execute("SELECT email, name FROM customers WHERE id = ?",
                          (order["customer_id"],)).fetchone() if order["customer_id"] else None
    amount = f"{(order['amount_total'] or 0) / 100:.2f} {(order['currency'] or '').upper()}"
    lines += [
        f"Sold: {', '.join(bought) if bought else 'see Stripe'}",
        f"To:   {customer['email'] if customer else 'unknown'}"
        + (f" ({customer['name']})" if customer and customer["name"] else ""),
        f"For:  {amount}",
        "",
        f"This is an automatic note from {site_name}. The buyer has had their own email.",
    ]
    return chr(10).join(lines)


def spend_credit(db, entitlement_id, customer_id):
    """Takes one session, atomically. Returns False if there was none left.

    The WHERE clause carries the check — `used < granted` — so two
    requests racing for the last session cannot both win: SQL decides,
    not a read followed by a write.
    """
    cur = db.execute(
        "UPDATE entitlements SET used = used + 1 "
        "WHERE id = ? AND customer_id = ? AND kind = ? AND revoked_at IS NULL "
        "AND used < granted AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
        (entitlement_id, customer_id, KIND_CREDIT),
    )
    return cur.rowcount > 0


def refund_credit(db, entitlement_id):
    """Hands a session back when the booking it was spent on failed."""
    db.execute(
        "UPDATE entitlements SET used = MAX(0, used - 1) WHERE id = ?", (entitlement_id,)
    )


def record_booking(db, uid, customer_id, entitlement_id, event_type_ref, starts_at, timezone=None):
    """Ties a booking to the session it spent, so a cancellation can give
    that session back. Without this link the ledger says "used" forever
    while the calendar says the meeting never happened."""
    db.execute(
        "INSERT OR IGNORE INTO bookings (provider_uid, customer_id, entitlement_id, event_type_ref, "
        "starts_at, timezone) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, customer_id, entitlement_id, str(event_type_ref), starts_at, timezone),
    )


def bookings_for(db, customer_id, include_settled=False):
    """The bookings that still stand.

    Anything whose session has been handed back — cancelled, or an entry
    deleted from the calendar — is not a booking any more, and leaving it
    listed would tell someone a meeting is happening while the ledger
    already says it is not. `missing` rows stay: the session was not
    returned, so it counts as a session they had.
    """
    sql = "SELECT * FROM bookings WHERE customer_id = ?"
    if not include_settled:
        sql += " AND status NOT IN ('cancelled', 'removed')"
    return db.execute(sql + " ORDER BY starts_at", (customer_id,)).fetchall()


def sync_cancellations(db, integrations, limit=50):
    """Gives a session back for every booking that has since been
    cancelled. Returns (returned, checked, error).

    A pull, for the same reason orders are pulled: Cal.com can push a
    cancellation webhook, but only to a publicly reachable address, and
    this site may not have one. Checking is cheap and can run whenever the
    buyer opens their page — the moment it actually matters to them.

    `credit_returned` makes it idempotent: a session is handed back once,
    however many times this runs.
    """
    data, error = integrations.calcom_call(db, f"/bookings?take={limit}&status=cancelled")
    if error:
        return 0, 0, error
    items = data.get("data", data) or []
    if not isinstance(items, list):
        items = items.get("bookings", []) or []
    cancelled_uids = {b.get("uid") for b in items if b.get("uid")}
    if not cancelled_uids:
        return 0, 0, None
    returned = 0
    for uid in cancelled_uids:
        row = db.execute(
            "SELECT * FROM bookings WHERE provider_uid = ? AND credit_returned = 0", (uid,)
        ).fetchone()
        if not row:
            continue
        if row["entitlement_id"]:
            refund_credit(db, row["entitlement_id"])
        db.execute(
            "UPDATE bookings SET status = 'cancelled', credit_returned = 1 WHERE id = ?",
            (row["id"],),
        )
        returned += 1
    return returned, len(cancelled_uids), None


def starts_in_future(starts_at):
    """Unparseable is treated as future — the benefit of the doubt goes to
    the person who paid."""
    if not starts_at:
        return True
    try:
        when = datetime.datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when > datetime.datetime.now(datetime.timezone.utc)


def sync_removed_bookings(db, integrations, limit=25):
    """Gives a session back when its calendar entry has GONE, not merely
    been cancelled. Returns (returned, checked).

    A booking deleted outright never reaches the cancelled list — Cal.com
    has nothing left to report — so without this a deleted entry leaves
    the buyer permanently short, which is the same bug cancellation had,
    one step further along.

    Two deliberate limits. A definite 404 is the only thing read as
    "gone", so an outage cannot refund the whole diary. And a vanished
    entry for a meeting that has already STARTED does not refund: the
    session was most likely delivered and the entry tidied away
    afterwards, and refunding it would give away a session that was used.
    Those are recorded as `missing` instead, so the owner can see them and
    decide.
    """
    rows = db.execute(
        "SELECT * FROM bookings WHERE credit_returned = 0 AND status NOT IN ('cancelled', 'missing') "
        "ORDER BY starts_at LIMIT ?", (limit,)
    ).fetchall()
    returned, checked = 0, 0
    for row in rows:
        booking, missing, error = integrations.calcom_booking(db, row["provider_uid"])
        checked += 1
        if error and not missing:
            continue  # transient — say nothing rather than the wrong thing
        if missing:
            if not starts_in_future(row["starts_at"]):
                db.execute("UPDATE bookings SET status = 'missing' WHERE id = ?", (row["id"],))
                continue
            status = "removed"
        elif (booking or {}).get("status") in ("cancelled", "rejected"):
            status = "cancelled"
        else:
            continue
        if row["entitlement_id"]:
            refund_credit(db, row["entitlement_id"])
        db.execute(
            "UPDATE bookings SET status = ?, credit_returned = 1 WHERE id = ?", (status, row["id"])
        )
        returned += 1
    return returned, checked


def sync_bookings(db, integrations):
    """One call for callers: cancelled bookings and vanished ones both
    give the session back. Returns how many were returned."""
    returned, _, _ = sync_cancellations(db, integrations)
    removed, _ = sync_removed_bookings(db, integrations)
    return returned + removed


def gone_bookings(db, limit=20):
    """Bookings no longer in the calendar, and whether the session came
    back — the record of what this reconciliation actually did."""
    return db.execute(
        "SELECT b.*, c.email FROM bookings b LEFT JOIN customers c ON c.id = b.customer_id "
        "WHERE b.status IN ('cancelled', 'removed', 'missing') ORDER BY b.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def cancel_booking(db, integrations, uid, customer_id=None, reason=None):
    """Cancels a booking and gives the session straight back. (ok, error).

    `customer_id` scopes it to one buyer's own bookings — the public page
    is reached with nothing but a token in a URL, so it must never be able
    to cancel somebody else's meeting by editing an id.

    The refund happens here rather than waiting for the next reconcile, so
    the page the person is looking at already shows the session back.
    `credit_returned` keeps that safe: the later sync will see the booking
    is settled and leave it alone.
    """
    sql = "SELECT * FROM bookings WHERE provider_uid = ?"
    params = [uid]
    if customer_id is not None:
        sql += " AND customer_id = ?"
        params.append(customer_id)
    row = db.execute(sql, params).fetchone()
    if not row:
        return False, "That booking isn't yours to cancel."
    if row["status"] == "cancelled":
        return True, None
    _, error = integrations.calcom_cancel_booking(db, uid, reason)
    if error:
        return False, error
    if row["entitlement_id"] and not row["credit_returned"]:
        refund_credit(db, row["entitlement_id"])
    db.execute(
        "UPDATE bookings SET status = 'cancelled', credit_returned = 1 WHERE id = ?", (row["id"],)
    )
    return True, None
