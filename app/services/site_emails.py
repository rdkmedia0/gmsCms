"""The wording of the messages this site sends on its own.

Four of them go out without anybody pressing anything -- an order lands,
somebody signs up, somebody confirms -- and until now their words were
fixed in the code. They are good words, but they are OUR words: they say
"we'll be in touch shortly" to a shop that answers within the hour and to
one that ships on Thursdays, and there is no register in them that
belongs to the business sending them.

So each message has a greeting and a sign-off the owner writes, wrapped
around facts the code always renders. That is exactly the shape
`newsletter_intro`/`newsletter_outro` already had; this is the same idea
applied to the other four, in one place, with a screen.

**What may be edited, and what may not.** The editable part is the
wrapper. The FACTS are not editable and are not optional:

  * the link a buyer gets back in with, and what it does;
  * how many sessions or downloads are waiting, and by when;
  * what somebody agreed to when they signed up;
  * the unsubscribe link and the sender line.

That is not tidiness. CLAUDE.md already says this about the sign-up
form's "a confirmation email is coming" line: an owner rewording it into
"you're subscribed" would make the site lie about its own mechanism.
Every one of the facts above is a statement about what actually happened
or what the reader can actually do, and an owner writing around them is
adding their voice; an owner writing OVER them is removing a fact
somebody needs, usually without meaning to.

**A placeholder is offered, never remembered.** Each message declares the
ones it can fill, they are listed on the screen to click in, and one that
this app cannot fill is left as the literal text somebody typed rather
than becoming an empty gap in a real message.
"""


def _p(name, means):
    return {"name": name, "means": means}


#  The four messages, in the order somebody meets them. `fixed` is what
#  the code always says regardless -- listed so the screen can show it,
#  greyed, between the two boxes: an owner writing a greeting should be
#  able to see what it is a greeting TO.
MESSAGES = {
    "order": {
        "name": "Your order",
        "when": "Sent to the buyer the moment a payment goes through.",
        "fixed": "What they bought, how many sessions or downloads are waiting, "
                 "when to save them by, and the link back to it all.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("total", "what they paid, e.g. 24.00 CHF"),
            _p("link", "their way back to what they bought"),
        ],
        "intro_default": "Thanks for your order from {{site}}.",
        "outro_default": "",
    },
    "sale": {
        "name": "Sale (to you)",
        "when": "Sent to you whenever somebody buys something.",
        "fixed": "What sold, for how much, who bought it, and anything you have to do about it.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("total", "what they paid"),
            _p("buyer", "the buyer's email address"),
        ],
        "intro_default": "",
        "outro_default": "",
    },
    "confirm": {
        "name": "Confirm your subscription",
        "when": "The one message that may go to an address that has not confirmed.",
        "fixed": "Who is asking, what was agreed to, the link that confirms it, and that "
                 "ignoring it means nothing further is ever sent.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("link", "the link that confirms it"),
        ],
        "intro_default": "",
        "outro_default": "",
    },
    "subscribed": {
        "name": "You're subscribed",
        "when": "Sent once, immediately after somebody confirms.",
        "fixed": "What they agreed to, and the unsubscribe link — which the law requires "
                 "and which is the reason this message exists at all.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("link", "their unsubscribe link"),
        ],
        "intro_default": "",
        "outro_default": "",
    },
}

ORDER = ("order", "sale", "confirm", "subscribed")


def _key(message, part):
    return "email_%s_%s" % (message, part)


def wording(db, message):
    """(intro, outro) as the owner has written them, or the defaults."""
    spec = MESSAGES.get(message)
    if not spec:
        return "", ""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?)",
        (_key(message, "intro"), _key(message, "outro"))).fetchall()
    found = {r["key"]: r["value"] for r in rows}
    #  A row that exists and is empty means the owner deleted it, which is
    #  a choice and not the same as never having touched it.
    intro = found.get(_key(message, "intro"))
    outro = found.get(_key(message, "outro"))
    return (spec["intro_default"] if intro is None else intro,
            spec["outro_default"] if outro is None else outro)


def save(db, message, intro, outro):
    """(saved, error). Refuses a message this app does not send."""
    if message not in MESSAGES:
        return False, "That isn't a message this site sends."
    for part, value in (("intro", intro), ("outro", outro)):
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (_key(message, part), (value or "").strip()))
    return True, None


def reset(db, message):
    """Back to the words this app ships with."""
    db.execute("DELETE FROM settings WHERE key IN (?, ?)",
               (_key(message, "intro"), _key(message, "outro")))


def fill(text, values):
    """Substitute the placeholders a message declares.

    One this app cannot fill is left as the literal text somebody typed,
    rather than becoming an empty gap in a real message: a visible
    `{{discount}}` is a mistake somebody can see and fix, and a blank
    space is one nobody notices until a customer asks about it.
    """
    out = (text or "").strip()
    if not out:
        return ""
    for name, value in (values or {}).items():
        out = out.replace("{{%s}}" % name, str(value if value is not None else ""))
    return out


def wrap(db, message, body, values):
    """The owner's greeting, the facts, and the owner's sign-off.

    Blank lines between them and nowhere else, so an empty greeting costs
    nothing rather than leaving a gap at the top of the message.
    """
    intro, outro = wording(db, message)
    parts = [fill(intro, values), (body or "").strip(), fill(outro, values)]
    return (chr(10) * 2).join(p for p in parts if p)


#  Sample values for the preview. Real-shaped rather than
#  `{{placeholder}}` repeated back, because the point of a preview is to
#  show how the WORDS read once they are filled in.
SAMPLE = {
    "site": "Your site",
    "total": "24.00 CHF",
    "buyer": "somebody@example.com",
    "link": "https://your.site/account/abc123",
}


def preview(db, message, sample_body):
    """One message as it would arrive, against believable data."""
    return wrap(db, message, sample_body, SAMPLE)
