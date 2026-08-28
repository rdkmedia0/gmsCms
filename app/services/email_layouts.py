"""Email layouts: what a newsletter is made of, instead of page sections.

A newsletter used to be a page, written with the tools every other page
uses, and most of them do not survive the trip. Measured, of the tool
menu: Blog, Shop, Buy button, Contact form and FAQ Reader arrive EMPTY,
because each is a marker resolved against live data that does not exist
in an inbox; Search arrives as a magnifying glass; a Video gallery as
three play triangles; Columns as the literal text `{}`.

So a newsletter is not a page. It is an ordered list of BLOCKS -- a table
structure, because table structure is what email clients actually render,
with every style inline because most clients strip a stylesheet.

A LAYOUT is a starting arrangement of those blocks, and nothing more.
That is the same shape `PAGE_LAYOUTS` takes for pages, and it is here for
the same reason. A layout used to be a fixed set of named slots, which
meant a letter could never carry a picture and a story could never carry
two, and every newsletter had exactly the parts its layout declared
whether it wanted them or not. Now a template seeds the blocks and every
one of them can be added, removed, reordered or restyled afterwards.
Nothing later has to ask which layout a newsletter was made from.

What a layout does NOT decide: the ground, the card, the sender line and
the unsubscribe link. Those come from `newsletter.to_email_html`'s
wrapper and stay there, because two of them are legally required and one
of them is the reason the card is light (see that module's own notes).

What a BLOCK may be styled with is short, and the test for admitting a
control is two-part: an inbox has to honour it AND the stored form has to
be able to write it down. Background, text colour, alignment and a font
family all pass -- they are inline attributes on a table cell, which is
the one thing every client renders. `@font-face` does not: Gmail strips
it, so a font choice here is a real installed family and never a
webfont, however good the site's own looks.
"""
import json
import re
from html import escape

from flask import render_template

#  ---------------------------------------------------------------
#  What a newsletter can be made of
#  ---------------------------------------------------------------
#
#  A closed set, like PAGE_TYPES and for the same reason: everything in
#  it has to survive an inbox, which is a question with a fixed answer
#  rather than a matter of taste. A new kind of block is a considered
#  addition to this dictionary, never something a template can invent.

BLOCK_TYPES = {
    "heading": {
        "name": "Heading",
        "icon": "H",
        "hint": "A line that introduces what follows.",
    },
    "text": {
        "name": "Words",
        "icon": "¶",
        "hint": "Paragraphs. Select some words to make them bold, or a link.",
    },
    "image": {
        "name": "Picture",
        "icon": "\U0001f5bc️",
        "hint": "Shown the full width of the card. Landscape works best.",
    },
    "button": {
        "name": "Button",
        "icon": "▭",
        "hint": "One thing to click. Drawn as a table, so Outlook renders it.",
    },
    "divider": {
        "name": "A line",
        "icon": "—",
        "hint": "A rule, to separate one part from the next.",
    },
}

#  The order the Insert menu offers them in -- most-used first, rather
#  than however the dictionary happens to iterate.
BLOCK_ORDER = ("heading", "text", "image", "button", "divider")

#  Real installed families only. A webfont cannot travel: Gmail strips
#  @font-face, so a name here has to be something already on the machine
#  reading the mail. "" means "whatever the site uses", which is the
#  default and what a newsletter keeps unless somebody chooses otherwise.
EMAIL_FONTS = (
    ("", "The site's own"),
    ("Arial, Helvetica, sans-serif", "Arial"),
    ("Georgia, 'Times New Roman', serif", "Georgia"),
    ("'Times New Roman', Times, serif", "Times New Roman"),
    ("Verdana, Geneva, sans-serif", "Verdana"),
    ("'Trebuchet MS', Tahoma, sans-serif", "Trebuchet MS"),
    ("'Courier New', Courier, monospace", "Courier New"),
)

ALIGNMENTS = (("left", "Left"), ("center", "Centred"), ("right", "Right"))


def blank(kind):
    """A new block of one kind, with everything it needs to be drawn.

    An empty block still has to be visible in the editor -- a slot you
    cannot see is a slot you cannot fill -- so each carries whatever the
    canvas needs to draw its empty shape.
    """
    kind = kind if kind in BLOCK_TYPES else "text"
    made = {"type": kind, "style": {}}
    if kind == "heading":
        made.update({"text": "", "level": 2})
    elif kind == "text":
        made["text"] = ""
    elif kind == "image":
        made.update({"src": "", "alt": "", "url": ""})
    elif kind == "button":
        made.update({"label": "", "url": ""})
    return made


def _clean_style(style):
    """Only what an inbox honours, and only in a form it can be given."""
    style = style if isinstance(style, dict) else {}
    out = {}
    for key in ("bg", "color"):
        if _is_hex(style.get(key)):
            out[key] = style[key]
    font = style.get("font") or ""
    if font and font in dict(EMAIL_FONTS):
        out["font"] = font
    align = style.get("align") or ""
    if align in dict(ALIGNMENTS):
        out["align"] = align
    return out


def _is_hex(value):
    return bool(value) and bool(re.match(r"^#[0-9a-fA-F]{6}$", str(value)))


def normalise(blocks):
    """Whatever arrived, as a list of blocks this module can render.

    Forgiving on purpose: a newsletter written before a block type
    existed, or saved by a browser that dropped a field, should open and
    be fixable rather than fail.
    """
    if not isinstance(blocks, list):
        return []
    out = []
    for raw in blocks:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type")
        if kind not in BLOCK_TYPES:
            continue
        made = blank(kind)
        for key in list(made):
            if key in ("type", "style"):
                continue
            if raw.get(key) is not None:
                made[key] = raw[key]
        if kind == "heading":
            try:
                made["level"] = int(made.get("level") or 2)
            except (TypeError, ValueError):
                made["level"] = 2
            if made["level"] not in (1, 2, 3):
                made["level"] = 2
        made["style"] = _clean_style(raw.get("style"))
        out.append(made)
    return out


#  A newsletter written under the old named-slot model, read as blocks.
#  Kept because these are somebody's drafts: the shape changed, what they
#  wrote did not, and an upgrade that silently empties a draft is worse
#  than one that refuses to run.
_OLD_ORDER = (
    ("image", "image"),
    ("heading", "heading"),
    ("body", "text"),
    ("left_heading", "heading"),
    ("left_body", "text"),
    ("right_heading", "heading"),
    ("right_body", "text"),
)


def from_named_slots(values):
    """The old {heading: ..., body: ...} shape, as blocks."""
    values = values or {}
    out = []
    for key, kind in _OLD_ORDER:
        text = (values.get(key) or "").strip()
        if not text:
            continue
        if kind == "image":
            out.append(dict(blank("image"), src=text))
        elif kind == "heading":
            out.append(dict(blank("heading"), text=text))
        else:
            out.append(dict(blank("text"), text=text))
    label = (values.get("button_label") or "").strip()
    url = (values.get("button_url") or "").strip()
    if label or url:
        out.append(dict(blank("button"), label=label, url=url,
                        style={"align": "center"}))
    return normalise(out)


#  ---------------------------------------------------------------
#  Layouts: a starting arrangement, not a kind
#  ---------------------------------------------------------------

def _h(text, level=2, **style):
    return {"type": "heading", "text": text, "level": level, "style": style}


def _t(text, **style):
    return {"type": "text", "text": text, "style": style}


def _img(**style):
    return {"type": "image", "src": "", "alt": "", "url": "", "style": style}


def _btn(label, **style):
    return {"type": "button", "label": label, "url": "", "style": style}


def _rule(**style):
    return {"type": "divider", "style": style}


LAYOUTS = {
    "letter": {
        "name": "A letter",
        "blurb": "Just words. The plainest thing to send, and the one least likely to look wrong anywhere.",
        "blocks": [
            _h("A heading"),
            _t("What you want to say."),
        ],
    },
    "story": {
        "name": "One story with a picture",
        "blurb": "A picture, a heading, some words and a button. The usual shape for announcing one thing.",
        "blocks": [
            _img(),
            _h("A heading"),
            _t("What you want to say."),
            _btn("Read the rest", align="center"),
        ],
    },
    "two-up": {
        "name": "Two things, one after the other",
        "blurb": "Two short items with a line between them. Good for a round-up.",
        "blocks": [
            _h("The first thing", level=3),
            _t("Keep it short."),
            _rule(),
            _h("The second thing", level=3),
            _t("Keep this one short too."),
        ],
    },
    "announcement": {
        "name": "An announcement",
        "blurb": "A big heading, a line or two, and one button. For when there is exactly one thing to say.",
        "blocks": [
            _h("The announcement", level=1, align="center"),
            _t("A line or two.", align="center"),
            _btn("Find out more", align="center"),
        ],
    },
}


#  A saved layout's key is prefixed so it can never collide with a
#  shipped one, and so any code reading a key can tell them apart without
#  a database lookup.
SAVED_PREFIX = "saved:"


def _slugify(name):
    out = "".join(c.lower() if c.isalnum() else "-" for c in (name or "").strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:60] or "layout"


def saved(db):
    """Every arrangement this install has kept, newest first."""
    if db is None:
        return []
    try:
        rows = db.execute(
            "SELECT slug, name, blocks FROM email_layouts ORDER BY id DESC").fetchall()
    except Exception:  # noqa: BLE001 - a missing table must not break the editor
        return []
    return list(rows)


def choices(db=None):
    """(key, name, blurb) for the dropdown, in a fixed order so the list
    does not shuffle between visits.

    The shipped arrangements first, then anything this install has saved.
    Saved ones come last because the shipped set is what somebody
    starting out is choosing between, and it does not grow.
    """
    out = [(key, LAYOUTS[key]["name"], LAYOUTS[key]["blurb"])
           for key in ("letter", "story", "two-up", "announcement")]
    for row in saved(db):
        out.append((SAVED_PREFIX + row["slug"], row["name"],
                    "One of yours, saved from a newsletter you had already laid out."))
    return out


def save_layout(db, name, blocks):
    """(key, error). Keeps one arrangement under a name somebody chose.

    A name they chose is one they will recognise in a dropdown six weeks
    later, which is why this asks rather than generating "Layout 3".
    Saving the same name again replaces it -- the alternative is two
    entries with one name, and no way to tell which is which.
    """
    name = (name or "").strip()
    if not name:
        return None, "Give it a name so you can find it again."
    blocks = normalise(blocks)
    if not blocks:
        return None, "There is nothing laid out to save."
    slug = _slugify(name)
    db.execute(
        "INSERT INTO email_layouts (slug, name, blocks) VALUES (?, ?, ?) "
        "ON CONFLICT(slug) DO UPDATE SET name = excluded.name, blocks = excluded.blocks",
        (slug, name, json.dumps(blocks)))
    return SAVED_PREFIX + slug, None


def delete_layout(db, key):
    """Removes one saved arrangement. A shipped one is not deletable --
    it is in the code, and would come back on the next boot."""
    if not str(key or "").startswith(SAVED_PREFIX):
        return False
    slug = str(key)[len(SAVED_PREFIX):]
    return db.execute("DELETE FROM email_layouts WHERE slug = ?", (slug,)).rowcount > 0


def starting_blocks(key, db=None):
    """A fresh copy of one layout's arrangement.

    A copy, because these are module-level dictionaries: handing the real
    ones out would let the first newsletter somebody wrote edit the
    template for every newsletter written after it. A saved layout is
    read from its row and needs no such care, but goes through the same
    normalise so both kinds arrive in one shape.
    """
    if str(key or "").startswith(SAVED_PREFIX) and db is not None:
        slug = str(key)[len(SAVED_PREFIX):]
        try:
            row = db.execute("SELECT blocks FROM email_layouts WHERE slug = ?",
                             (slug,)).fetchone()
        except Exception:  # noqa: BLE001
            row = None
        if row:
            try:
                return normalise(json.loads(row["blocks"]))
            except (ValueError, TypeError):
                return []
    layout = LAYOUTS.get(key) or LAYOUTS["letter"]
    return normalise([dict(b, style=dict(b.get("style") or {}))
                      for b in layout["blocks"]])


#  Schemes a link in a newsletter may use. The same list a button holds
#  itself to: anything else is left as the literal text somebody typed
#  rather than quietly becoming a link.
LINK_SCHEMES = ("http://", "https://", "mailto:", "tel:", "/", "#")

#  The written vocabulary a newsletter body may use. Small on purpose,
#  and the same shape as the one an FAQ answer takes (see
#  sections.faq_markdown): the owner never types HTML -- this app has no
#  raw-HTML box for anything a person writes, and an email is the worst
#  place to start -- so what the toolbar produces is written down as
#  TEXT, escaped first and converted second. No tag can arrive by being
#  typed, and the stored form stays something a person can read.
#
#      ## a heading        ### a smaller heading
#      **bold**            *italic*
#      [words](address)    - a bullet
#      a blank line between paragraphs
#
#  newsletter-editor.js's serialiser is the exact inverse of this. If one
#  changes the other has to, or a newsletter stops reading back the way
#  it was written.
_LINK_STYLE = ["color:#1a5fd0;text-decoration:underline;"]


def _spans(escaped):
    """What happens inside a line: bold, italic, a link."""
    def link(match):
        label, href = match.group(1), match.group(2).strip()
        if not href.startswith(LINK_SCHEMES):
            return match.group(0)   # left as the literal text it was
        return '<a href="%s" style="%s">%s</a>' % (href, _LINK_STYLE[0], label)

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, escaped)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    return out


def block_styles(look, size=16, style=None):
    """The inline style each kind of thing inside a block carries.

    Named separately because the EDITOR needs the same strings: a heading
    made by the toolbar has to arrive looking exactly like the heading
    that will be sent, and the only way to be sure of that is for both to
    read the same dictionary rather than two hand-copied lists that
    drift.

    `style` is one block's own overrides. A block that says nothing gets
    the site's look, which is what almost every block does.
    """
    look = look or {}
    style = style or {}
    body_font = style.get("font") or look.get("body_font") or "Arial, sans-serif"
    heading_font = style.get("font") or look.get("heading_font") or body_font
    accent = look.get("accent") or "#1a5fd0"
    body_colour = style.get("color") or "#333c47"
    head_colour = style.get("color") or "#1c2430"
    return {
        "p": "margin:0 0 14px;font-size:%dpx;line-height:1.65;color:%s;"
             "font-family:%s;" % (size, body_colour, body_font),
        "li": "margin:0 0 8px;font-size:%dpx;line-height:1.6;color:%s;"
              "font-family:%s;" % (size, body_colour, body_font),
        "ul": "margin:0 0 16px;padding-left:22px;",
        "h1": "margin:0 0 14px;font-size:%dpx;line-height:1.2;font-weight:700;"
              "color:%s;font-family:%s;" % (size + 10, head_colour, heading_font),
        "h2": "margin:0 0 10px;font-size:%dpx;line-height:1.3;font-weight:700;"
              "color:%s;font-family:%s;" % (size + 5, head_colour, heading_font),
        "h3": "margin:0 0 8px;font-size:%dpx;line-height:1.35;font-weight:700;"
              "color:%s;font-family:%s;" % (size + 1, head_colour, heading_font),
        "a": "color:%s;text-decoration:underline;" % accent,
    }


def cell_style(style):
    """What the table cell around one block carries.

    Background and alignment live here rather than on the words, because
    a background on a heading paints only as far as the letters go: the
    cell is the box, so the cell is what gets the colour. Padding follows
    the background for the same reason -- an unpadded colour hugs the
    text and looks like a mistake.
    """
    style = style or {}
    bits = ["text-align:%s;" % (style.get("align") or "left")]
    if style.get("bg"):
        bits.append("background-color:%s;" % style["bg"])
        bits.append("padding:18px 20px;")
    return "".join(bits)


def rich(text, look, size=16, style=None):
    """One text block as finished, inline-styled email blocks.

    Every style is written onto the tag itself, because most clients
    strip a stylesheet -- which is also why this returns whole blocks
    rather than text for a macro to wrap: a heading and a bullet are not
    paragraphs and cannot be styled as though they were.
    """
    st = block_styles(look, size, style)
    _LINK_STYLE[0] = st["a"]
    para, item = st["p"], st["li"]
    head = {2: st["h2"], 3: st["h3"]}

    blocks, bullets, para_lines = [], [], []

    def flush_list():
        if bullets:
            blocks.append(
                '<ul style="' + st["ul"] + '">'
                + "".join('<li style="%s">%s</li>' % (item, b) for b in bullets)
                + "</ul>")
            del bullets[:]

    def flush_para():
        #  Lines inside one paragraph are joined by a break, not split
        #  into paragraphs. That distinction is the whole reason a blank
        #  line means something: an address or a sign-off is several
        #  lines of ONE paragraph, and turning each into its own would
        #  put 14px between every line of it.
        if para_lines:
            blocks.append('<p style="%s">%s</p>' % (para, "<br>".join(para_lines)))
            del para_lines[:]

    def flush():
        flush_para()
        flush_list()

    for chunk in re.split(r"\n\s*\n", (text or "").strip()):
        for line in chunk.split(chr(10)):
            line = line.strip()
            if not line:
                continue
            escaped = escape(line)
            if escaped.startswith("- "):
                flush_para()
                bullets.append(_spans(escaped[2:].strip()))
                continue
            flush_list()
            #  Deepest marker first: "### " also starts with "## ".
            if escaped.startswith("### "):
                flush_para()
                blocks.append('<h3 style="%s">%s</h3>' % (head[3], _spans(escaped[4:].strip())))
            elif escaped.startswith("## "):
                flush_para()
                blocks.append('<h2 style="%s">%s</h2>' % (head[2], _spans(escaped[3:].strip())))
            else:
                para_lines.append(_spans(escaped))
        #  A blank line in the source ends whatever was being built.
        flush()
    flush()
    return blocks


def paragraphs(text):
    """Plain text as escaped paragraphs.

    Still used by anything that wants the words without a look to style
    them with.
    """
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        block = block.strip()
        if block:
            out.append(escape(block).replace(chr(10), "<br>"))
    return out


def describe(block):
    """One block, named the way the editor labels it."""
    return BLOCK_TYPES.get(block.get("type"), {}).get("name", "Block")


def missing(blocks):
    """What is still empty, by name, so the screen can say what is
    stopping a send rather than refusing without a reason.

    A block is only a problem if it would arrive BROKEN. An empty text
    block is skipped on send and costs nothing; a button with words and
    nowhere to go, or a picture slot with no picture, is a hole in the
    email somebody meant to fill.
    """
    gaps = []
    for i, block in enumerate(normalise(blocks), start=1):
        kind = block["type"]
        where = "%s %d" % (describe(block), i)
        if kind == "button":
            if block.get("label") and not block.get("url"):
                gaps.append("%s has no web address" % where)
            elif block.get("url") and not block.get("label"):
                gaps.append("%s has no words on it" % where)
        elif kind == "image" and not block.get("src"):
            gaps.append("%s has no picture in it" % where)
    if not any((b["type"] in ("heading", "text") and (b.get("text") or "").strip())
               for b in normalise(blocks)):
        gaps.insert(0, "There are no words in it yet")
    return gaps


def render(blocks, look, edit=False):
    """The email BODY for one newsletter. The wrapper adds the rest.

    `edit=True` returns the SAME email with its blocks opened up: each one
    boxed and named, its words made editable in place, and the empty ones
    drawn so the shape can be seen before it is filled. That is the whole
    point -- the thing being written into is the thing being sent, rather
    than a column of boxes beside a picture of it.

    What an inbox receives is untouched by this: with edit false, not one
    extra attribute is emitted.
    """
    prepared = []
    for block in normalise(blocks):
        made = dict(block)
        made["cell"] = cell_style(block["style"])
        made["st"] = block_styles(look, style=block["style"])
        if block["type"] == "text":
            made["html"] = rich(block.get("text") or "", look, style=block["style"])
        prepared.append(made)
    return render_template("emails/blocks.html", look=look, blocks=prepared,
                           edit=edit)

