"""Email layouts: what a newsletter is made of, instead of page sections.

A newsletter used to be a page, written with the tools every other page
uses, and most of them do not survive the trip. Measured, of the tool
menu: Blog, Shop, Buy button, Contact form and FAQ Reader arrive EMPTY,
because each is a marker resolved against live data that does not exist
in an inbox; Search arrives as a magnifying glass; a Video gallery as
three play triangles; Columns as the literal text `{}`.

So a newsletter is not a page. It is a LAYOUT with named slots the owner
fills in -- a table structure, because table structure is what email
clients actually render, with every style inline because most clients
strip a stylesheet.

What a layout does NOT decide: the ground, the card, the sender line and
the unsubscribe link. Those come from `newsletter.to_email_html`'s
wrapper and stay there, because two of them are legally required and one
of them is the reason the card is light (see that module's own notes).

A layout is a Jinja template under `templates/emails/layouts/`, and its
fields are declared here so the editing screen can build itself: one
labelled control per field, a hint under each, in the same shape as
every other admin form.
"""
import re
from html import escape

from flask import render_template

#  Field kinds, and what the editor makes of each. Deliberately few: an
#  owner filling in a newsletter should recognise every control from
#  somewhere else in this app.
TEXT = "text"            # one line
PARAGRAPHS = "paragraphs"  # several, blank line between
IMAGE = "image"          # a picture from the media library
URL = "url"              # somewhere to send a reader


def _field(key, label, kind, hint, required=False):
    return {"key": key, "label": label, "kind": kind, "hint": hint, "required": required}


LAYOUTS = {
    "letter": {
        "name": "A letter",
        "blurb": "Just words. A heading and as much as you want to say — the plainest thing to send, and the one least likely to look wrong anywhere.",
        "fields": [
            _field("heading", "Heading", TEXT, "The first thing they read. Say what this is about.", True),
            _field("body", "What you want to say", PARAGRAPHS,
                   "Leave a blank line between paragraphs. No formatting needed.", True),
        ],
    },
    "story": {
        "name": "One story with a picture",
        "blurb": "A picture, a heading, some words and a button. The usual shape for announcing one thing.",
        "fields": [
            _field("image", "Picture", IMAGE, "Shown full width at the top. Landscape works best."),
            _field("heading", "Heading", TEXT, "One line, above the words.", True),
            _field("body", "What you want to say", PARAGRAPHS, "Leave a blank line between paragraphs.", True),
            _field("button_label", "Button", TEXT, "What the button says, e.g. 'Read the rest'. Leave blank for no button."),
            _field("button_url", "Button goes to", URL, "The web address the button opens."),
        ],
    },
    "two-up": {
        "name": "Two things side by side",
        "blurb": "Two short items in a row, which fall one above the other on a phone. Good for a round-up.",
        "fields": [
            _field("left_heading", "First heading", TEXT, "", True),
            _field("left_body", "First item", PARAGRAPHS, "Keep it short — it only has half the width."),
            _field("right_heading", "Second heading", TEXT, "", True),
            _field("right_body", "Second item", PARAGRAPHS, "Keep it short — it only has half the width."),
        ],
    },
    "announcement": {
        "name": "An announcement",
        "blurb": "A big heading, a line or two, and one button. For when there is exactly one thing to say.",
        "fields": [
            _field("heading", "Heading", TEXT, "Big and short. This is the whole message.", True),
            _field("body", "A line or two", PARAGRAPHS, "Optional. Anything longer belongs in a letter."),
            _field("button_label", "Button", TEXT, "What the button says.", True),
            _field("button_url", "Button goes to", URL, "The web address the button opens.", True),
        ],
    },
}


def choices():
    """(key, name, blurb) for the picker, in a fixed order so the list does
    not shuffle between visits."""
    return [(key, LAYOUTS[key]["name"], LAYOUTS[key]["blurb"])
            for key in ("letter", "story", "two-up", "announcement")]


def fields_for(key):
    return LAYOUTS.get(key, LAYOUTS["letter"])["fields"]


def paragraphs(text):
    """Plain text as escaped paragraphs.

    The owner never types HTML -- this app has no raw-HTML box for
    anything a person writes, and an email is the worst place to start.
    """
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        block = block.strip()
        if block:
            out.append(escape(block).replace("\n", "<br>"))
    return out


def missing(key, values):
    """Which required slots are still empty, by label, so the screen can
    say what is stopping a send rather than refusing without a reason."""
    return [f["label"] for f in fields_for(key)
            if f["required"] and not (values or {}).get(f["key"], "").strip()]


#  Words for a specimen. Real sentences rather than "Lorem ipsum" or a
#  field name, because the point of a specimen is to show what the shape
#  does to WRITING -- how long a heading can be before it wraps, what two
#  paragraphs look like beside a button.
SAMPLE = {
    "heading": "A quiet week, and one thing worth saying",
    "body": ("I have been asked the same question three times this month."
             + chr(10) * 2
             + "When people say they want more time, they rarely mean more hours."),
    "image": "",
    "button_label": "Read the rest",
    "button_url": "#",
    "left_heading": "Evening slots",
    "left_body": "Thursdays now run until 8pm.",
    "right_heading": "Two spaces left",
    "right_body": "The next block starts in October.",
}


def sample(key, look):
    """One layout, filled in, for somebody choosing between them.

    A name and a sentence cannot show what a shape looks like -- which is
    the whole basis on which one is picked. This renders the real layout
    with real words, so the picker shows the thing itself rather than a
    description of it.
    """
    return render(key, SAMPLE, look)


def render(key, values, look):
    """The email BODY for one layout. The wrapper adds the rest."""
    key = key if key in LAYOUTS else "letter"
    values = values or {}
    prepared = {}
    for field in fields_for(key):
        raw = (values.get(field["key"]) or "").strip()
        prepared[field["key"]] = paragraphs(raw) if field["kind"] == PARAGRAPHS else raw
    return render_template("emails/layouts/%s.html" % key, look=look, v=prepared)
