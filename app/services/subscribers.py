"""
The list behind the Email sign-up block.

Consent is recorded, not assumed. Every row keeps the exact wording the
person agreed to, when, and from which page — because "we have consent"
is a claim you have to be able to evidence a year later, and a bare list
of addresses cannot evidence anything. The wording is stored per row
rather than looked up from the current block, since the block will be
edited and the promise made to somebody last spring is the one that
counts.

Unsubscribing needs no login and no password: the link carries a token
that identifies the row and nothing else. That is the only way an
unsubscribe link in an email can work, and it is why the token is random
rather than derived from the address — a guessable one would let anyone
unsubscribe anyone.
"""
import csv
import io
import secrets


def add(db, email, consent_text, source, ip=None):
    """(status, confirm_token). status is 'added', 'already', or 'refused'.

    An address goes on the list unconfirmed and stays that way until the
    link in the mail it is sent has been followed. Nothing else is ever
    sent in the meantime -- see `listing(confirmed_only=True)`, which is
    what a send reads.

    'already' now means "already confirmed": somebody re-entering an
    address that has not answered yet gets the confirmation sent again,
    because the usual reason for typing it twice is that the first mail
    did not arrive.
    """
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 200:
        return "refused", None
    existing = db.execute(
        "SELECT token, unsubscribed_at, confirmed_at, confirm_token "
        "FROM subscribers WHERE email = ?", (email,)
    ).fetchone()
    if existing:
        if existing["unsubscribed_at"]:
            #  Coming back is allowed, and is a fresh consent -- which
            #  means it is confirmed again from scratch, exactly like a new
            #  address. The old withdrawal stays on the row as history.
            confirm = secrets.token_urlsafe(16)
            db.execute(
                "UPDATE subscribers SET unsubscribed_at = NULL, consent_text = ?, "
                "source = ?, created_at = CURRENT_TIMESTAMP, confirmed_at = NULL, "
                "confirm_token = ? WHERE email = ?",
                (consent_text, source, confirm, email),
            )
            return "added", confirm
        if existing["confirmed_at"]:
            return "already", None
        #  Waiting on an answer. Send the same invitation again rather than
        #  making a second row: somebody typing their address in twice is
        #  usually telling you the first mail did not arrive.
        confirm = existing["confirm_token"] or secrets.token_urlsafe(16)
        db.execute("UPDATE subscribers SET confirm_token = ? WHERE email = ?", (confirm, email))
        return "added", confirm
    confirm = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO subscribers (email, token, consent_text, source, ip, confirm_token) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (email, secrets.token_urlsafe(16), consent_text, source, ip, confirm),
    )
    return "added", confirm


def unsubscribe(db, token):
    cur = db.execute(
        "UPDATE subscribers SET unsubscribed_at = CURRENT_TIMESTAMP "
        "WHERE token = ? AND unsubscribed_at IS NULL", (token,)
    )
    if cur.rowcount:
        return True
    #  Already gone is still success as far as the person is concerned:
    #  the point of the link is that they end up off the list.
    return bool(db.execute("SELECT 1 FROM subscribers WHERE token = ?", (token,)).fetchone())


def mark_confirmation_sent(db, email):
    """Writes down that the invitation actually went out.

    "We sent them a confirmation" is a claim like any other, and the row
    could not evidence it: it recorded that somebody typed an address and
    that somebody later clicked a link, with nothing in between. This is
    stamped after the mail server has taken the message, so it says what
    happened rather than what was intended.
    """
    db.execute("UPDATE subscribers SET confirm_sent_at = CURRENT_TIMESTAMP "
               "WHERE email = ?", ((email or "").strip().lower(),))


def confirm(db, confirm_token, ip=None):
    """Follows the link in the invitation. Returns the row, or None.

    Idempotent on purpose: a link followed twice, or a mail opened by
    something that fetches links before a person sees them, must not read
    as a failure to somebody who did what was asked.
    """
    row = db.execute(
        "SELECT * FROM subscribers WHERE confirm_token = ?", (confirm_token,)
    ).fetchone()
    if row is None:
        return None
    if row["confirmed_at"] is None:
        #  The address the answer came from is kept beside the address the
        #  request came from. Two different machines is normal -- people
        #  sign up on a laptop and read mail on a phone -- but between
        #  them they are what shows the two halves were separate acts.
        db.execute(
            "UPDATE subscribers SET confirmed_at = CURRENT_TIMESTAMP, unsubscribed_at = NULL, "
            "confirm_ip = ? WHERE id = ?", (ip, row["id"])
        )
    return row


def erase(db, subscriber_id):
    """Removes somebody completely, at their request or the owner's.

    Erasing and unsubscribing are different acts and both are needed.
    Unsubscribing stops the email and keeps the row, which is what lets
    the site prove it stopped -- and stops a later import quietly putting
    the same person back. Erasing removes the person from the site
    altogether, including the record of their consent.

    That trade is real and is not for this function to decide: somebody
    exercising a right to erasure is entitled to have the evidence go
    too. The admin screen says so plainly before it happens.
    """
    row = db.execute("SELECT email FROM subscribers WHERE id = ?", (subscriber_id,)).fetchone()
    if row is None:
        return None
    db.execute("DELETE FROM subscribers WHERE id = ?", (subscriber_id,))
    return row["email"]


#  Who a send can be aimed at. Two answers, because two is what there
#  is to say today: everybody who confirmed, or the ones who have also
#  bought something. A third is a line in this tuple plus a clause in
#  `_audience_sql`, not a new feature.
AUDIENCES = (
    ("all", "Everyone on the list"),
    ("customers", "Customers only"),
)

#  A customer is somebody who has paid for something. A refunded order
#  stops counting, because `refund` rewrites its status -- so one purchase
#  since refunded does not make somebody a customer, while four purchases
#  and one refund still does. Matched on the address, lowercased on both
#  sides: the list stores addresses lowercased and a checkout does not.
CUSTOMER_MATCH = """
    EXISTS (SELECT 1 FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE LOWER(c.email) = subscribers.email AND o.status = 'paid')
"""


def is_customer_sql():
    """The whole test, as SQL: the orders say so, or the owner does."""
    return "(subscribers.is_customer = 1 OR " + CUSTOMER_MATCH + ")"


def orders_by_email(db):
    """{email: (how many, when the last one was)} for everybody who has
    paid for something. Read once and looked up, rather than a query per
    row of a list that can run to thousands."""
    rows = db.execute(
        "SELECT LOWER(c.email) AS email, COUNT(*) AS n, MAX(o.created_at) AS last "
        "FROM orders o JOIN customers c ON c.id = o.customer_id "
        "WHERE o.status = 'paid' GROUP BY LOWER(c.email)"
    ).fetchall()
    return {r["email"]: (r["n"], r["last"]) for r in rows}


def set_customer_flag(db, subscriber_id, flag):
    """The owner's own answer, which never overrides the orders -- it only
    adds to them. Unflagging somebody who has actually bought something
    leaves them a customer, because they are one."""
    db.execute("UPDATE subscribers SET is_customer = ? WHERE id = ?",
               (1 if flag else 0, subscriber_id))
    row = db.execute("SELECT email FROM subscribers WHERE id = ?", (subscriber_id,)).fetchone()
    return row["email"] if row else None


def listing(db, include_gone=False, confirmed_only=False, audience="all"):
    """The list. `confirmed_only` is what a SEND must read.

    An address that has not answered its invitation is on this table and
    is not a subscriber: it is written down so it can be shown to the
    owner and so a second attempt does not make a second row, and it is
    never mailed again.
    """
    sql = "SELECT * FROM subscribers"
    where = []
    if not include_gone:
        where.append("unsubscribed_at IS NULL")
    if confirmed_only:
        where.append("confirmed_at IS NOT NULL")
    if audience == "customers":
        where.append(is_customer_sql())
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.execute(sql + " ORDER BY id DESC").fetchall()


def counts(db):
    row = db.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(unsubscribed_at IS NULL AND confirmed_at IS NOT NULL) AS active, "
        "SUM(unsubscribed_at IS NULL AND confirmed_at IS NULL) AS pending, "
        #  Customers among the people who could actually be sent to, not
        #  among everybody who ever appeared on the table -- the number is
        #  read as "this is how many that send would reach".
        "SUM(unsubscribed_at IS NULL AND confirmed_at IS NOT NULL AND " +
        is_customer_sql() + ") AS customers "
        "FROM subscribers"
    ).fetchone()
    return {"total": row["total"] or 0, "active": row["active"] or 0,
            "pending": row["pending"] or 0, "customers": row["customers"] or 0}


def audience_count(db, audience):
    """How many a send aimed this way would reach."""
    return len(listing(db, confirmed_only=True, audience=audience))


def audience_label(audience):
    return dict(AUDIENCES).get(audience, dict(AUDIENCES)["all"])


def export_csv(db):
    """Everything, including who has left and what each person agreed to —
    an export that drops the consent record is the half you would actually
    need if anyone asked."""
    out = io.StringIO()
    writer = csv.writer(out)
    #  The whole record, because half of it is no record at all. What
    #  somebody asking would want to see is the sequence: this address
    #  asked, from this page, in these words, from this machine; we
    #  invited it at this time; it answered at this time from this
    #  machine; it left at this time. Every one of those is a column.
    writer.writerow(["email", "signed up", "signed up from (IP)", "from page",
                     "what they agreed to", "confirmation sent", "confirmed",
                     "confirmed from (IP)", "status", "unsubscribed",
                     "customer", "orders paid"])
    orders = orders_by_email(db)
    for row in listing(db, include_gone=True):
        if row["unsubscribed_at"]:
            status = "unsubscribed"
        elif row["confirmed_at"]:
            status = "subscribed"
        else:
            status = "never confirmed - not mailed"
        bought = orders.get(row["email"], (0, ""))[0]
        writer.writerow([row["email"], row["created_at"], row["ip"] or "",
                         row["source"] or "", row["consent_text"] or "",
                         row["confirm_sent_at"] or "", row["confirmed_at"] or "",
                         row["confirm_ip"] or "", status, row["unsubscribed_at"] or "",
                         "yes" if (bought or row["is_customer"]) else "no", bought])
    return out.getvalue()
