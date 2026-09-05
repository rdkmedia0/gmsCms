"""The wording of the messages this site sends on its own.

Four of them go out without anybody pressing anything -- an order lands,
somebody signs up, somebody confirms -- and until now their words were
fixed in the code. They are good words, but they are OUR words: they say
"we'll be in touch shortly" to a shop that answers within the hour and to
one that ships on Thursdays, and there is no register in them that
belongs to the business sending them.

**The whole message is the owner's.** This began as a greeting and a
sign-off wrapped around a body the code rendered, on the reasoning that
the FACTS are not a field: an owner writing over them removes something
the reader needs, usually without meaning to.

That was half right, and the wrong half cost more. The fixed middle told
a returning buyer how many sessions they had IN TOTAL -- summed across
every order they had ever placed -- in an email about the one they had
just paid for. No owner could correct it, because the sentence was ours.
A fixed body that says the wrong thing is worse than an editable one that
says nothing: the first cannot be fixed by the person being blamed for
it.

So the body is written by the owner, and the facts arrive as
**placeholders**: `{{total}}`, `{{items}}`, `{{invoice}}`, `{{link}}`.
The facts did not become optional; they became addressable. An owner who
wants the amount inside their own sentence can put it there, and one who
leaves `{{invoice}}` where it stands gets a real invoice.

**Two things are still not a field**, and neither is a matter of taste:

  * the unsubscribe link and the sender line on anything going to a
    mailing list. Both are required by law, both are appended below
    whatever the owner writes, and no wording can remove them.
  * a placeholder this app cannot fill, which is left as the literal
    text somebody typed rather than becoming a gap. A visible
    `{{discount}}` is a mistake somebody can see and fix; a blank space
    is one nobody notices until a customer asks about it.

**An owner's earlier words are not thrown away.** Installs configured
before this carry `email_<message>_intro` / `_outro`; a message with no
body of its own is composed from those around the default, so upgrading
changes nobody's wording. Saving once replaces the pair with a body.
"""


def _p(name, means):
    return {"name": name, "means": means}


NL = chr(10)


#  The four messages, in the order somebody meets them.
#
#  `body_default` is what the site ships with, and it is a real message
#  rather than a skeleton -- an owner should be able to leave it alone and
#  have it be right. Placeholders are declared per message so the screen
#  offers exactly the ones that message can fill, and no others: a
#  `{{buyer}}` on a subscription confirmation would be a promise this app
#  cannot keep.
MESSAGES = {
    "order": {
        "name": "Your order",
        "when": "Sent to the buyer the moment a payment goes through.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("items", "what they bought, one line each with quantity and price"),
            _p("invoice", "the whole invoice: reference, date, your details, items, total"),
            _p("invoice_pdf", "a link to the PDF invoice, when the payment produced one"),
            _p("product", "the names of what they bought, on one line"),
            _p("total", "what they paid, e.g. 24.00 CHF"),
            _p("method", "how they paid, e.g. Card (Stripe)"),
            _p("order", "this order's reference"),
            _p("date", "the date of this order"),
            _p("access", "sessions or downloads THIS order includes, and by when"),
            _p("link", "their way back to what they bought"),
        ],
        "body_default": NL.join([
            '## Thank you for your order',
            '',
            'Please find your order from {{site}} below:',
            '',
            '{{items}}',
            '',
            '**Total:** {{total}}',
            '**Payment method:** {{method}}',
            '',
            'You can find your orders, make bookings and download your files from here where applicable:',
            '',
            '{{link}}',
            '',
            'Many thanks for your trust and loyalty.',
        ]),
    },
    "sale": {
        "name": "Sale (to you)",
        "when": "Sent to you whenever somebody buys something.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("items", "what sold, one line each with quantity and price"),
            _p("invoice", "the whole invoice, as the buyer receives it"),
            _p("invoice_pdf", "a link to the PDF invoice, when the payment produced one"),
            _p("product", "the names of what sold, on one line"),
            _p("total", "what they paid"),
            _p("method", "how they paid"),
            _p("order", "this order's reference"),
            _p("date", "the date of this order"),
            _p("buyer", "the buyer's email address"),
            _p("action", "anything you have to do about it, e.g. post two items"),
        ],
        "body_default": NL.join([
            '## A customer made an order',
            '',
            'Somebody has bought something from your website.',
            '',
            '{{items}}',
            '',
            '**Total:** {{total}}',
            '**Payment method:** {{method}}',
            '**Buyer:** {{buyer}}',
            '',
            '{{action}}',
        ]),
    },
    "contact": {
        "name": "Contact form message (to you)",
        "when": "Sent to you whenever a visitor sends a message through a Contact Form.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("name", "the name the visitor gave"),
            _p("email", "the visitor's email address"),
            _p("message", "the message they typed"),
        ],
        "body_default": NL.join([
            '## New message from your website',
            '',
            'You have received a message through {{site}}.',
            '',
            '**From:** {{name}} <{{email}}>',
            '',
            '{{message}}',
        ]),
    },
    "confirm": {
        "name": "Confirm your subscription",
        "when": "The one message that may go to an address that has not confirmed.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("link", "the link that confirms it"),
            #  What the form said at the moment they ticked it, quoted
            #  back. Not required by law -- the RECORD is what evidences
            #  consent, and that is written down either way -- but it is
            #  the thing that makes a confirmation checkable by the
            #  person receiving it, so it is offered rather than dropped.
            _p("consent", "the exact wording they agreed to when they signed up"),
        ],
        "body_default": NL.join([
            '## Please confirm your subscription',
            '',
            'Dear Subscriber,',
            '',
            'We have received a request to add you to our mailing list @ {{site}}.',
            '',
            'If this was you and you wish to be subscribed, please opt in by clicking the link below:',
            '',
            '{{link}}',
            '',
            "If this wasn't you then you may delete and ignore this email.",
            '',
            'Many thanks for your interest.',
        ]),
    },
    "subscribed": {
        "name": "You're subscribed",
        "when": "Sent once, immediately after somebody confirms.",
        "placeholders": [
            _p("site", "your site's name"),
            _p("link", "their unsubscribe link"),
        ],
        "body_default": NL.join([
            '## You are on the list',
            '',
            'Dear Subscriber,',
            '',
            'You are now subscribed to the mailing list @ {{site}}.',
            '',
            'We will send you news and offers from time to time, and you can stop them whenever you like using the link at the bottom of any message.',
            '',
            'Many thanks for your interest.',
        ]),
    },
}


#  What the code adds below whatever the owner writes, and why. Shown on
#  the screen, greyed, under the message it belongs to: an owner who
#  cannot see it writes their own and the reader gets two.
APPENDED = {
    "order": "The sender line, which says who this came from.",
    "sale": "The sender line, which says who this came from.",
    "contact": "The sender line, which says who this came from. The visitor's "
               "own address is set as Reply-To, so replying reaches them.",
    "confirm": "The sender line, which says who this came from.",
    "subscribed": "The unsubscribe link and the sender line. Both are required by "
                  "law on a message to a mailing list, so they are added for you "
                  "and cannot be removed by any wording.",
}

#  Messages that go to a mailing list, and therefore carry an
#  unsubscribe link whatever the owner writes. `confirm` is deliberately
#  NOT here: it goes to somebody who has not joined a list, so there is
#  nothing yet to leave, and offering to unsubscribe them from something
#  they never joined is its own kind of confusing.
NEEDS_UNSUBSCRIBE = ("subscribed",)

ORDER = ("order", "sale", "contact", "confirm", "subscribed")


def _key(message, part):
    return "email_%s_%s" % (message, part)


def body(db, message):
    """The message as the owner has it, or the words the site ships with.

    An install configured before the body existed has an intro and an
    outro instead. Those are composed around the default rather than
    dropped -- somebody wrote them, and an upgrade that silently deletes
    what you wrote is the worst kind of upgrade. Saving once replaces the
    pair with a body, and this never runs again for that message.
    """
    spec = MESSAGES.get(message)
    if not spec:
        return ""
    rows = {r["key"]: r["value"] for r in db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?, ?)",
        (_key(message, "body"), _key(message, "intro"),
         _key(message, "outro"))).fetchall()}
    stored = rows.get(_key(message, "body"))
    #  A row that exists and is empty means the owner deleted it, which is
    #  a choice and not the same as never having touched it.
    if stored is not None:
        return stored
    intro = (rows.get(_key(message, "intro")) or "").strip()
    outro = (rows.get(_key(message, "outro")) or "").strip()
    if not intro and not outro:
        return spec["body_default"]
    return (NL * 2).join(p for p in (intro, spec["body_default"], outro) if p)


def wording(db, message):
    """(body, "") -- kept for anything still asking the old two-part
    question, so a caller that has not been updated reads the real
    message rather than an empty string."""
    return body(db, message), ""


def save(db, message, text):
    """(saved, error). Refuses a message this app does not send."""
    if message not in MESSAGES:
        return False, "That isn't a message this site sends."
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
               (_key(message, "body"), (text or "").strip()))
    return True, None


def reset(db, message):
    """Back to the words this app ships with.

    Clears the legacy pair too. Leaving those behind would make a reset
    fall through to an intro the owner believed they had just cleared,
    which is the same class of surprise as a stale cache.
    """
    db.execute("DELETE FROM settings WHERE key IN (?, ?, ?)",
               (_key(message, "body"), _key(message, "intro"),
                _key(message, "outro")))


def fill(text, values):
    """Substitute the placeholders a message declares.

    One this app cannot fill is left as the literal text somebody typed,
    rather than becoming an empty gap in a real message: a visible
    `{{discount}}` is a mistake somebody can see and fix, and a blank
    space is one nobody notices until a customer asks.

    A value that is itself empty -- an order with nothing to post, a
    payment with no PDF -- takes its whole line with it, so a template
    ending in `{{action}}` does not send a message ending in a blank.
    """
    out = (text or "")
    if not out.strip():
        return ""
    for name, value in (values or {}).items():
        token = "{{%s}}" % name
        if token not in out:
            continue
        text_value = "" if value is None else str(value)
        if not text_value.strip():
            #  Drop the line rather than leave a stranded label. "Buyer:
            #  " with nothing after it reads as a fault in the site.
            out = NL.join(line for line in out.split(NL)
                          if token not in line or line.strip() != token)
            out = out.replace(token, "")
        else:
            out = out.replace(token, text_value)
    #  Never more than one blank line in a row: removing a line above can
    #  otherwise leave a hole in the middle of somebody's message.
    lines, cleaned = out.split(NL), []
    for line in lines:
        if not line.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(line.rstrip())
    return NL.join(cleaned).strip()


def wrap(db, message, unused=None, values=None):
    """The owner's message, with its placeholders filled in, plus
    whatever the law adds below it.

    The third argument used to be the body the code rendered. It is kept
    so the call sites read unchanged, and ignored, because there is no
    longer a body that is not the owner's.

    The unsubscribe link is the one thing a wording cannot remove. It is
    appended here rather than in the route that happens to know the URL,
    so a fifth list message added later cannot ship without it -- and
    only when it is not already there, because an owner who wrote
    `{{link}}` into their own sentence should not get it twice.
    """
    values = values or {}
    text = fill(body(db, message), values)
    if message in NEEDS_UNSUBSCRIBE:
        url = (values.get("link") or "").strip()
        if url and url not in text:
            text = (text + NL * 2 + "Unsubscribe: " + url).strip()
    return text


#  Sample values for the preview. Real-shaped rather than
#  `{{placeholder}}` repeated back, because the point of a preview is to
#  show how the WORDS read once they are filled in.
SAMPLE = {
    "site": "Your site",
    "items": NL.join(["1 x Coaching pack  24.00 CHF",
                      "2 x Session notes  18.00 CHF"]),
    "invoice": (NL * 2).join([
        NL.join(["Order cs_test_a1b2c3", "2026-08-28"]),
        NL.join(["Your Business GmbH", "1 Example Street, 8001 Zurich"]),
        NL.join(["1 x Coaching pack  24.00 CHF",
                 "2 x Session notes  18.00 CHF",
                 "",
                 "Total: 42.00 CHF",
                 "Payment method: Card (Stripe)"]),
    ]),
    "invoice_pdf": "https://pay.stripe.com/invoice/acct_1/test/pdf",
    "consent": "Yes, email me news and offers from Your site.",
    "product": "Coaching pack, Session notes",
    "total": "42.00 CHF",
    "method": "Card (Stripe)",
    "order": "cs_test_a1b2c3",
    "date": "2026-08-28",
    "access": "This order includes 3 sessions to book.",
    "action": "Nothing to post - this one delivers itself.",
    "buyer": "somebody@example.com",
    "name": "Alex Visitor",
    "email": "alex@example.com",
    "message": NL.join(["Hello,", "",
                        "I saw your site and wanted to ask about your opening hours.",
                        "Could you let me know?", "", "Thanks, Alex"]),
    "link": "https://your.site/my/abc123",
}


def preview(db, message, sample_body=None):
    """One message as it would arrive, against believable data."""
    return wrap(db, message, None, SAMPLE)
