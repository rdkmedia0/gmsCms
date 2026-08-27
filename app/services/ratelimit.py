"""How often one address may do something.

`services/captcha.py` ends by saying, correctly, that it "will not stop a
determined attacker who reads the page and does the sum. It is not meant
to: the rate limit on the route is what bounds the damage." That rate
limit did not exist. The only limiter in the app was
`unlock_rate_limited`, which guards the password on a purchases page and
nothing else -- so the module documented a defence it did not have, which
is worse than documenting none, because it is the reason nobody went
looking.

Two public forms send email, and they are not equally dangerous:

  * the **contact form** mails the OWNER. A flood is a nuisance in their
    inbox.
  * the **sign-up form** mails whatever address was typed into it. A
    flood is a confirmation email sent to a stranger who did not ask, at
    an address the attacker chose -- which is somebody else's inbox, and
    this site's reputation. Double opt-in already means an address that
    never confirms is never written to again, so the harm is bounded at
    one message; a limit is what bounds how many strangers get one.

Counted in `login_attempts`, which already exists, already carries a
`kind`, and is already pruned. A second table for the same question would
be a second thing to clean up.

Deliberately per-IP and only per-IP. Per-address would be trivially
beaten by varying the address, which is the whole attack; and anything
cleverer needs to remember more about visitors than a site like this
should.
"""

#  Generous enough that a real person retrying a typo never meets it, and
#  small enough that a script gets very little for its trouble.
LIMITS = {
    #  The owner's own inbox. A person filling this in twice is normal;
    #  six times in an hour is not.
    "contact": (6, 60),
    #  Somebody else's inbox. Tighter, because each one is a message to a
    #  stranger who did not ask for it.
    "signup": (4, 60),
}


def _limit(kind):
    return LIMITS.get(kind, (6, 60))


def too_many(db, kind, ip):
    """Whether this address has already had its turn."""
    if not ip:
        #  No address to count against -- fail OPEN rather than closed. A
        #  proxy that strips the header would otherwise lock out every
        #  visitor at once, and a contact form nobody can use is a worse
        #  outcome than one that can be spammed.
        return False
    allowed, minutes = _limit(kind)
    row = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND kind = ? "
        "AND attempted_at > datetime('now', ?)",
        (ip, kind, "-%d minutes" % minutes)).fetchone()
    return row["n"] >= allowed


def record(db, kind, ip):
    """Count one, and forget the old ones.

    Recorded on the way IN, before the work, so a request that fails
    half-way still counts -- otherwise the cheapest way past this would be
    to make each attempt fail.
    """
    if not ip:
        return
    db.execute("INSERT INTO login_attempts (ip, kind) VALUES (?, ?)", (ip, kind))
    #  Pruned here rather than on a schedule: this table is only ever
    #  written by these paths, so this is the only moment it grows.
    db.execute("DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-1 day')")


def wait_message(kind):
    """What to tell a person who has met the limit.

    Never "you are being rate limited", which reads as an accusation to
    somebody who simply typed their address wrong twice.
    """
    _allowed, minutes = _limit(kind)
    if kind == "signup":
        return ("That address has been asked for a few times already. Please check your "
                "inbox — including the spam folder — and try again in an hour if nothing "
                "arrived.")
    return ("Thanks — we have had a few messages from here already. Please give it an hour "
            "before sending another, or email us directly if it is urgent.")
