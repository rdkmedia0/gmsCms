"""Section/tool content logic — what a section's content can be (SECTION_TYPES,
BLOCK_LIBRARY), how raw HTML gets classified into native sections
(_classify_layout_chunk, used by the AI Theme Generator and package content),
Columns-cell manipulation, and Banner/Card/Image styling and uploads. Pure
content-shaping logic plus direct db/request reads — no route decorators,
no flash/redirect (see CLAUDE.md's layering rule)."""
import os
import re
import json
import uuid
import hashlib
import urllib.request
import urllib.error
from html import escape as html_escape
from bs4 import BeautifulSoup

from ..icons import render_icon
from werkzeug.utils import secure_filename
from flask import request, current_app

from ..db import get_db
from .. import ai_image
from .. import ai_video


SECTION_TYPES = [
    ("header", "Header / Banner"),
    ("text", "Text"),
    ("html", "HTML / Embed"),
    ("image", "Image"),
    ("file", "File / Download"),
    ("media", "Media Player (Audio / Video / YouTube)"),
    ("columns", "Columns"),
]

BLOCK_LIBRARY = {
    #  The site's own name. Filled in below, beside the other starters
    #  that are built by the same function every later edit goes
    #  through, so the starter can never drift from an edited one.
    "wordmark": ("html", ""),
    "table": (
        "html",
        '<table class="cms-table">\n'
        "<thead><tr><th>Column 1</th><th>Column 2</th><th>Column 3</th></tr></thead>\n"
        "<tbody>\n"
        "<tr><td>Row 1</td><td>Detail</td><td>Detail</td></tr>\n"
        "<tr><td>Row 2</td><td>Detail</td><td>Detail</td></tr>\n"
        "</tbody>\n</table>",
    ),
    #  "video-gallery" is filled in at the bottom of this file by
    #  build_video_gallery() -- the same function every later edit goes
    #  through -- so the starter markup can never drift from the shape
    #  an edited gallery gets rebuilt into.
    "image-accordion": (
        "html",
        '<div class="cms-image-accordion">\n'
        + "\n".join(
            '<div class="cms-accordion-panel" tabindex="0" style="background-image:url(\'/static/img/placeholder.svg\')">'
            f'<span class="cms-accordion-caption">Panel {i}</span></div>'
            for i in range(1, 6)
        )
        + "\n</div>",
    ),
}

IMAGE_WIDTHS = ("small", "medium", "large", "full")
IMAGE_ANIMATIONS = ("none", "fade-in", "zoom-hover")
#  Silhouettes, not corner styles. "Rounded" and "Square" used to live
#  here too, which meant the word "rounded" named one thing on a picture
#  (a fixed 16px) and another site-wide (22px), and a masked picture
#  ignored the Corners setting entirely because the mask wrote a literal
#  radius. Those two are corner choices and now belong to Corners, which
#  does them properly and at one value. What is left genuinely cannot be
#  said with a radius: each one crops the picture to a shape and forces
#  its aspect ratio.
IMAGE_MASKS = ("none", "circle", "diamond", "hexagon", "star")
FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".txt", ".csv")
TABLE_STYLES = ("cms-table", "cms-table-striped", "cms-table-colored", "cms-table-plain")

#  Same four styles, with the plain-English labels the Table tool's own
#  config dropdown shows — a novice picking "Striped rows" should never
#  have to know the class name behind it.
TABLE_STYLE_CHOICES = (
    ("cms-table", "Bordered (spreadsheet)"),
    ("cms-table-striped", "Striped rows"),
    ("cms-table-colored", "Colored header"),
    ("cms-table-plain", "Plain (no lines)"),
)

#  The blog's card styles moved to services/blog.py with the rest of it —
#  a blog is a tool now, and how its posts are laid out is that tool's
#  business rather than a column on the page that used to be the blog.

MEDIA_TYPES = ("youtube", "video", "audio")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".ogv", ".mov")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac")
FILE_DISPLAYS = ("card", "button", "text-link", "icon")
#  The drawn mark a File download wears (icons.UI_ICON_PATHS keys). "document"
#  is the default; "resume" is the CV/résumé card.
FILE_ICONS = ("document", "resume")


BLOCK_TAGS = {"div", "section", "article", "figure", "ul", "ol"}
INTERACTIVE_TAGS = {"table", "iframe", "script", "form"}

# Class-name fragments that signal real interactive/dynamic behavior (a JS
# widget, not just decorative markup) — this is content a "plugin"-style
# html section is actually meant for, since there's no static/local
# equivalent tool that can reproduce it.
INTERACTIVE_CLASS_HINTS = (
    "counter", "typing", "swiper", "splide", "slider", "carousel",
    "accordion", "tabs-", "-tab", "countdown", "marquee", "lightbox",
)


def _has_interactive_content(node):
    if node.find(list(INTERACTIVE_TAGS)):
        return True
    for el in node.find_all(class_=True):
        classes = " ".join(el.get("class") or [])
        if any(hint in classes for hint in INTERACTIVE_CLASS_HINTS):
            return True
    return False


def _significant_children(node):
    return [c for c in node.contents if getattr(c, "name", None)]


def _descend_single_wrappers(nodes):
    """Follow a chain of single-child wrapper elements (a chunk can nest a
    pattern in 2-3 layers of purely-layout divs) down to the level where the
    real content actually branches, so classification below looks at the
    meaningful siblings instead of always seeing "one wrapper div"."""
    level = nodes
    while len(level) == 1 and level[0].name in BLOCK_TAGS:
        children = _significant_children(level[0])
        if not children:
            break
        level = children
    return level


def _is_image_ish(node):
    if node.name in ("img", "figure"):
        return True
    if node.name == "a" and node.find("img") and not node.get_text(strip=True):
        return True
    return False


def _classify_layout_chunk(html_chunk, _depth=0):
    """
    Translate one raw HTML chunk (from the AI Theme Generator or a package's
    page content) into native CMS sections (text/image/columns/banner/card)
    instead of dumping it as an opaque 'html' blob — so it's editable
    through the normal section tools (image size/shape pickers, WYSIWYG
    toolbar, column editing) like any section the admin created by hand.

    A chunk can nest arbitrarily deeply (a heading, then a sub-heading, then
    a row of columns, all wrapped in one outer group) — a single top-level
    shape check can't classify that as a whole, so when nothing simple
    matches, this recurses into each top-level piece and classifies them
    independently, effectively flattening one chunk into several ordered
    native sections. Only content that's genuinely atomic and interactive
    (real JS widgets: sliders, counters, forms, embeds — see
    INTERACTIVE_CLASS_HINTS) falls back to 'html', since there's no local
    tool equivalent for those.

    Returns a LIST of dicts of the fields to insert into `sections`.
    """
    soup = BeautifulSoup(html_chunk or "", "html.parser")
    top_level = _significant_children(soup)
    if not top_level:
        return []

    # A whole chunk that translated straight to a Banner or Card — tag it
    # with that tool's own type immediately, before the generic text/columns
    # rules below get a chance to reclassify it as something else (a Banner
    # with little text and no <img> would otherwise match the Text rule).
    if len(top_level) == 1 and "cms-banner" in (top_level[0].get("class") or []):
        return [{"type": "banner", "title": "", "content": html_chunk}]
    if len(top_level) == 1 and "cms-card-shape" in (top_level[0].get("class") or []):
        return [{"type": "card", "title": "", "content": html_chunk}]

    has_interactive = _has_interactive_content(soup)

    # A chunk can be wrapped in 1-3 layers of purely-layout <div>s — follow
    # those down to where the real content branches.
    level = _descend_single_wrappers(top_level)
    imgs = soup.find_all("img")
    text_len = len(soup.get_text(strip=True))

    # A chunk that's essentially just one image (optionally linked).
    if not has_interactive and len(imgs) == 1 and text_len < 20:
        img = imgs[0]
        link = img.find_parent("a")
        return [{
            "type": "image",
            "title": img.get("alt", "") or "",
            "content": img.get("src", "") or "",
            "link_url": link.get("href", "") if link else "",
        }]

    # A row of nothing but images (a logo strip / simple gallery, any
    # count >= 2, however deeply it was wrapped) — one Columns section,
    # one image per column. Columns cells already hold raw HTML (same as
    # a hand-built Columns section can), so this doesn't need to be
    # interactive-content-free the way the plain Text rule below does.
    if len(level) >= 2 and all(_is_image_ish(c) for c in level):
        return [{
            "type": "columns",
            "title": "",
            "content": json.dumps({"columns": [str(c).strip() for c in level]}),
        }]

    # 2-6 similarly-structured sibling blocks (a WordPress "columns"/"group"
    # pattern) — map onto the native Columns section instead of leaving it
    # as opaque raw HTML. Checked before the Text fallback below, since a
    # columns/group wrapper with 0-1 images in it would otherwise also
    # match that broader rule. Not gated on has_interactive for the same
    # reason as the image row above — any widget nested inside one cell
    # just becomes part of that cell's raw HTML, same as manual editing.
    if 2 <= len(level) <= 6 and all((c.name or "") in BLOCK_TAGS for c in level):
        return [{
            "type": "columns",
            "title": "",
            "content": json.dumps({"columns": [str(c).strip() for c in level]}),
        }]

    # Only text-ish tags, no complex/interactive markup — a plain Text
    # section, not raw HTML. This also covers the very common "one image
    # plus a heading/paragraph" pattern (e.g. a WP media-and-text block):
    # up to one <img> is fine here too, since the WYSIWYG toolbar already
    # supports inline images directly (its Insert Image button), so an
    # embedded <img> doesn't need the dedicated Image section type — that's
    # only for a chunk that's *essentially just* the image (caught above).
    # Excludes "cover" blocks (background image/color + overlay via
    # absolutely-positioned children, tagged .cms-banner and already
    # returned above) — those aren't plain text and the WYSIWYG editor's
    # contenteditable could mangle their nested markup on save, so they
    # stay raw HTML, editable only via "Edit raw HTML".
    if not has_interactive and len(imgs) <= 1 and all(
        (c.name or "") not in INTERACTIVE_TAGS for c in top_level
    ):
        return [{"type": "text", "title": "", "content": str(soup).strip()}]

    # Nothing simple matched as a whole (e.g. a heading + sub-heading
    # followed by a columns block, all in one wrapper) — split into its
    # meaningful pieces (post single-wrapper-descend, so a chunk that's one
    # outer <div> around several real children still splits on those
    # children instead of immediately bailing out) and classify each
    # independently, rather than giving up and keeping the whole thing as
    # one raw HTML blob. Bounded depth so a pathological chunk can't
    # recurse forever.
    if len(level) > 1 and _depth < 6:
        results = []
        for child in level:
            piece = str(child).strip()
            if piece:
                results.extend(_classify_layout_chunk(piece, _depth + 1))
        if results:
            return results

    return [{"type": "html", "title": "", "content": html_chunk}]



BREADCRUMB_SIZES = ("small", "medium", "large")
BREADCRUMB_STYLES = ("plain", "uppercase", "pill")
BANNER_SHAPES = ("none", "rounded", "circle", "square", "diamond", "hexagon", "star")
CONTACT_FIELDS = ("phone", "email", "website", "facebook", "instagram", "x")


def _breadcrumb_starter_html(size, style):
    size = size if size in BREADCRUMB_SIZES else "medium"
    style = style if style in BREADCRUMB_STYLES else "plain"
    return f'<nav class="cms-breadcrumb cms-breadcrumb-{size} cms-breadcrumb-style-{style}">%%CMS_BREADCRUMB%%</nav>'


#  ---------------------------------------------------------------
#  WORDMARK — the site's own name, as a thing you can put somewhere.
#
#  The name lives in settings and everything that needs it reads it
#  there: the browser tab, the footer, the legal pages, an email's
#  sender line. The one place it could not go was a PAGE -- so an owner
#  who wanted their name in the header had to type it into a Text
#  section, where it becomes dead text that does not follow a rename.
#
#  Optional, like every tool: nothing puts one on a page but a person
#  choosing it, and no template ships one.
#  Written as constants so no format string can eat them.
TITLE_PLACEHOLDER = "%" + "%CMS_SITE_TITLE%" + "%"
TAGLINE_PLACEHOLDER = "%" + "%CMS_SITE_TAGLINE%" + "%"
WORDMARK_SIZES = ("small", "medium", "large")
WORDMARK_STYLES = ("plain", "uppercase", "spaced")


def _wordmark_starter_html(size="medium", style="plain", with_tagline=False):
    size = size if size in WORDMARK_SIZES else "medium"
    style = style if style in WORDMARK_STYLES else "plain"
    #  Built by concatenation, NOT by %-formatting: the placeholder this
    #  markup has to carry is literally `%%CMS_SITE_TITLE%%`, and a
    #  %-format collapses the doubled percent signs to one -- so the tool
    #  stored `%CMS_SITE_TITLE%`, which matches no placeholder and
    #  printed itself on the page.
    tagline = ('<span class="cms-wordmark-tagline">' + TAGLINE_PLACEHOLDER + "</span>"
               if with_tagline else "")
    return ('<a class="cms-wordmark cms-wordmark-' + size
            + " cms-wordmark-style-" + style + '" href="/">'
            '<span class="cms-wordmark-name">' + TITLE_PLACEHOLDER + "</span>"
            + tagline + "</a>")


BLOCK_LIBRARY["wordmark"] = ("html", _wordmark_starter_html())


#  How the Language tool is formatted. The languages themselves always come
#  from the site's settings (the render fills them in); these are only the
#  LOOK, stored as data-* on the marker so a dropped switcher shows whatever
#  is enabled and remembers how it was styled.
LS_STYLES = (("list", "Row of links"), ("dropdown", "Dropdown"), ("buttons", "Buttons"))
LS_COLORS = (("text", "Text colour"), ("accent", "Accent"), ("subtle", "Subtle"))
#  What each language reads as -- one OR the other, never a flag glued to a
#  word ("GB English"): a name in one of three forms, or the flag on its own.
LS_LABELS = (("native", "Native name"), ("english", "English name"),
             ("code", "Code"), ("flag", "Flag only"))
LS_ALIGNS = (("left", "Left"), ("center", "Centre"), ("right", "Right"))
LS_DEFAULTS = {"style": "list", "color": "text", "labels": "native", "align": "left"}


def _ls_valid(opts):
    o = dict(LS_DEFAULTS)
    for key, allowed in (("style", LS_STYLES), ("color", LS_COLORS),
                         ("labels", LS_LABELS), ("align", LS_ALIGNS)):
        v = (opts.get(key) or "").strip()
        if v in dict(allowed):
            o[key] = v
    return o


def read_lang_switcher_opts(content):
    """The switcher's formatting, read back off the marker's data-* (defaults
    for anything unset, so a switcher made before these options still works)."""
    c = content or ""
    opts = {}
    for key in ("style", "color", "labels", "align"):
        m = re.search(r'data-ls-%s="([a-z]+)"' % key, c)
        if m:
            opts[key] = m.group(1)
    return _ls_valid(opts)


def build_lang_switcher_marker(opts=None):
    o = _ls_valid(opts or {})
    return ('<div class="cms-lang-switcher" data-lang-switcher="1" '
            'data-ls-style="%(style)s" data-ls-color="%(color)s" '
            'data-ls-labels="%(labels)s" data-ls-align="%(align)s"></div>' % o)


def apply_lang_switcher_form(form):
    """Rebuild the marker from the tool's own form (which carries every
    option), the same shape the other marker tools use."""
    return build_lang_switcher_marker({
        "style": form.get("ls_style", ""),
        "color": form.get("ls_color", ""),
        "labels": form.get("ls_labels", ""),
        "align": form.get("ls_align", ""),
    })


def _lang_switcher_starter_html():
    #  A marker the render replaces with the site's actual language links
    #  (see _lang_switcher in public.py). It carries only its LOOK; the
    #  languages come from the site's settings, so one dropped anywhere shows
    #  whatever the owner has enabled -- and stays correct when that changes.
    return build_lang_switcher_marker()


BLOCK_LIBRARY["lang-switcher"] = ("html", _lang_switcher_starter_html())


DIVIDER_STYLES = ("solid", "dashed", "dotted", "double")
DIVIDER_WIDTHS = ("narrow", "medium", "full")
DIVIDER_SPACINGS = ("small", "medium", "large")


def _divider_starter_html(style, width, spacing, color):
    """A plain <hr> with a marker class + style/width/spacing classes, and
    an optional inline color — same in-place-reconfigure shape as
    Breadcrumb/Banner (placed with defaults, then adjusted via its own
    config form, never through the raw HTML editor)."""
    style = style if style in DIVIDER_STYLES else "solid"
    width = width if width in DIVIDER_WIDTHS else "medium"
    spacing = spacing if spacing in DIVIDER_SPACINGS else "medium"
    color = (color or "").strip()
    color_attr = f' style="border-color:{color}"' if color and re.match(r"^#[0-9a-fA-F]{6}$", color) else ""
    return (
        f'<hr class="cms-content-divider cms-divider-{style} cms-divider-{width} '
        f'cms-divider-spacing-{spacing}"{color_attr}>'
    )


BANNER_ATTACHMENTS = ("scroll", "fixed")


# Real brand marks (single-path monochrome, 0 0 24 24 viewBox) instead of
# the letter/initials placeholders ("f", "IG", "X") this used to fall back
# to — those read as an unfinished/broken icon font, not an actual icon.
# Sourced from Simple Icons (simpleicons.org), CC0-licensed — safe to
# embed and ship, unlike pulling a random dafont icon font whose license
# usually only covers personal use, not redistribution in a product.


def _insert_layout_chunks(db, page_id, layout_sections):
    """Classify and insert a template's imported layout into a page,
    appending after any existing sections. Each imported chunk may expand
    into several native sections (see _classify_layout_chunk), so the
    returned count is the number of sections actually inserted, not the
    number of chunks passed in."""
    start_pos_row = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM sections WHERE page_id = ?", (page_id,)
    ).fetchone()
    pos = start_pos_row["next_pos"]
    count = 0
    for html_chunk in layout_sections:
        for section in _classify_layout_chunk(html_chunk):
            db.execute(
                "INSERT INTO sections (page_id, type, title, content, position, link_url) VALUES (?, ?, ?, ?, ?, ?)",
                (page_id, section["type"], section["title"], section["content"], pos, section.get("link_url", "")),
            )
            pos += 1
            count += 1
    return count


def is_contact_tool_block(content):
    """Whether this block is a Contact Info TOOL, or merely writing that
    happens to sit in a contact wrapper.

    Ten templates ship `<div class="cms-contact-tool">` holding
    hand-written lines — a business name, opening hours — which the tool's
    fields have no home for. Offering them the form would quietly replace
    a salon's hours with four empty inputs on the first save, so they are
    left as the text they are and keep the editing they already had.
    Structured items, or the empty starter, are the tool.
    """
    if not content:
        return False
    return any(m in content for m in
               ("cms-contact-detail", "cms-contact-icon", "cms-contact-empty"))


CONTACT_EMPTY_HTML = ('<div class="cms-contact-tool cms-contact-empty">Add a phone number, '
                      'email, address, or social link by editing this block.</div>')


#  A Contacts block is a list of lines, and a line is an icon and a value:
#  pick the Instagram mark, type the handle. There is no kind to choose
#  first — what a line IS is read from what was typed (see contact_link),
#  because the value already says so. A dropdown reading "Phone" beside a
#  WhatsApp link is a question the app should not have been asking.
#
#  Each line carries its icon and its print-or-hover choice in data-
#  attributes. Two earlier shapes are still read by the same loop — the
#  fixed-field one, and the one that stored a kind — so a block made
#  either way keeps its contents and its marks (LEGACY_KIND_ICONS).
MAX_CONTACT_ROWS = 12

_PHONEISH = re.compile(r"^[\d\s+()./-]{5,}$")

#  An old block stored what KIND each line was, from the version that had
#  a dropdown for it. The kind is gone -- what a line is, is read from
#  what was typed -- but the icon it implied is not, so a block written
#  before this keeps its marks.
LEGACY_KIND_ICONS = {
    "phone": "\U0001F4DE", "email": "✉️", "website": "\U0001F310",
    "address": "\U0001F4CD", "copyright": "©", "custom": "\U0001F517",
    "facebook": "brand:facebook", "instagram": "brand:instagram", "x": "brand:x",
    "youtube": "brand:youtube", "linkedin": "brand:linkedin",
    "tiktok": "brand:tiktok", "pinterest": "brand:pinterest",
}
DEFAULT_CONTACT_ICON = "\U0001F517"
ADDRESS_ICON = "📍"


def is_postal_address(value):
    """Whether a line is somewhere you go rather than something you open.

    Read from what was typed, like everything else in this tool -- there is
    no type dropdown to argue with. A comma or a line break is what
    separates "Unit 4, St. Mary's Road" from "flourandsalt.example", and no
    email, phone number or web address needs either.

    It has to be asked BEFORE the "contains a dot, so it is a domain" rule
    in contact_link, which was turning any address with a full stop in it
    into a link to https://Unit 4, St. Mary's Road.
    """
    value = (value or "").strip()
    if not value or value.startswith(("http://", "https://", "/")):
        return False
    return "," in value or "\n" in value


def contact_link(value):
    """The href for a line, or "" for one that is not a link.

    Read from what was typed, because that is the only thing that knows.
    A dropdown saying "Phone" next to a WhatsApp link would have to be
    argued with; four rules in order do not:
    """
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://", "/")):
        return value                                    # already an address
    if "@" in value and "/" not in value:
        return "mailto:" + value                        # looks like an email
    if _PHONEISH.match(value):
        return "tel:" + re.sub(r"[^\d+]", "", value)    # + or digits, reads as a number
    if is_postal_address(value):
        return ""                                       # a place, not a page
    if "." in value or "/" in value:
        return "https://" + value                       # example.com, or a path
    return ""                                           # plain words are not a link


def _contact_row_html(value, icon, show_text=True):
    value = (value or "").strip()
    if not value:
        return ""
    href = contact_link(value)
    #  An address that has not been given an icon gets the pin rather than
    #  the generic link mark, for the same reason an email gets an
    #  envelope: the icon should say what the line IS before it is read.
    glyph = render_icon(icon or (ADDRESS_ICON if is_postal_address(value) else DEFAULT_CONTACT_ICON))
    #  An address is shown without its scheme -- "flourandsalt.example",
    #  not "https://flourandsalt.example/" -- because that is how a person
    #  writes it down. The link still goes to the whole thing.
    shown = value
    if href.startswith("http"):
        shown = re.sub(r"^https?://(www\.)?", "", shown).rstrip("/")
    attrs = ('class="cms-contact-detail" '
             f'data-icon="{html_escape(icon or "", quote=True)}" '
             f'data-show="{"1" if show_text else "0"}"')
    #  A line break typed or pasted into an address is kept, because that
    #  is how an address is written. Escaped first and converted second --
    #  the same order the FAQ's own small vocabulary uses, never the other
    #  way round.
    shown_html = html_escape(shown).replace("\n", "<br>")
    if show_text:
        inner = glyph + '<span class="cms-contact-text">%s</span>' % shown_html
    else:
        #  Icon alone, with the words on hover: a row of five networks
        #  reads as five marks, not five addresses. The value stays in the
        #  title so it is not a mystery to anyone who stops.
        attrs += f' title="{html_escape(shown, quote=True)}"'
        inner = glyph + '<span class="cms-visually-hidden">%s</span>' % shown_html
    if not href:
        return f"<span {attrs}>{inner}</span>"
    external = ' target="_blank" rel="noopener"' if href.startswith("http") else ""
    return f'<a href="{html_escape(href, quote=True)}" {attrs}{external}>{inner}</a>'


CONTACT_LAYOUTS = (("row", "Side by side"), ("column", "One per line"))
#  Which way the lines sit in their space. Centre is what every block
#  written before the choice existed does (the CSS centred them), so it is
#  the default and a block with no `data-align` reads as it.
CONTACT_ALIGNS = (("left", "Left"), ("center", "Centre"), ("right", "Right"))
#  How big the marks read. Off means the block takes whatever the zone
#  around it already says — which is right nearly everywhere, and is why
#  it is the default. On, the size is the owner's, in pixels, and applies
#  to the ICON only: the words beside it keep following the site, because
#  a footer whose text has been sized by its template should not have that
#  overruled by a contact line.
CONTACT_ICON_MIN, CONTACT_ICON_MAX, CONTACT_ICON_DEFAULT = 12, 48, 20


def build_contact_tool(rows, layout="row", icon_size=0, align="center"):
    """The whole block, from a list of {value, icon, show} lines.

    `layout` is how the lines sit: side by side, which suits a footer
    strip, or one per line, which suits a sidebar or a contact page. It
    rides on the wrapper like everything else this tool remembers,
    because the block is the storage.

    `align` is which way those lines sit in their space -- left, centre or
    right -- a structural choice the owner makes, stored as a class so the
    CSS can align both layouts (a row justifies, a column text-aligns).
    """
    layout = layout if layout in dict(CONTACT_LAYOUTS) else "row"
    align = align if align in dict(CONTACT_ALIGNS) else "center"
    try:
        icon_size = int(icon_size or 0)
    except (TypeError, ValueError):
        icon_size = 0
    if icon_size:
        icon_size = max(CONTACT_ICON_MIN, min(CONTACT_ICON_MAX, icon_size))
    items = [_contact_row_html(r.get("value", ""), r.get("icon", ""), r.get("show", True))
             for r in rows]
    items = [i for i in items if i]
    shown = max(len(rows), 1)
    #  A line with nothing in it is not published — a visitor should not
    #  get an empty link — but WHERE it was has to survive, or pressing +
    #  on the first line would put the new one at the bottom. The indices
    #  ride along on the wrapper and the reader puts the gaps back.
    blanks = ",".join(str(i) for i, r in enumerate(rows) if not (r.get("value") or "").strip())
    #  The chosen size is a value, not a class: it is a number somebody
    #  dragged to, so it rides as a custom property the CSS reads. Off
    #  writes nothing at all, which is how the block goes back to
    #  inheriting rather than to some remembered default.
    style = ' style="--cms-contact-icon: %dpx"' % icon_size if icon_size else ""
    meta = ' data-rows="%d"%s data-layout="%s" data-icon-size="%d" data-align="%s"%s' % (
        shown, (' data-blanks="%s"' % blanks) if blanks else "", layout, icon_size, align, style)
    align_class = " cms-contact-align-%s" % align
    if not items:
        return CONTACT_EMPTY_HTML.replace('class="cms-contact-tool',
                                          '%s class="cms-contact-tool%s' % (meta.strip(), align_class))
    return ('<div class="cms-contact-tool cms-contact-%s%s"%s><div class="cms-contact-details">'
            % (layout, align_class, meta) + "".join(items) + "</div></div>")


def read_contact_layout(content):
    """How this block's lines are arranged. Defaults to side by side,
    which is what every block written before the choice existed does."""
    if content:
        m = re.search(r'data-layout="(\w+)"', content)
        if m and m.group(1) in dict(CONTACT_LAYOUTS):
            return m.group(1)
    return "row"


def read_contact_align(content):
    """Which way this block's lines sit. Defaults to centre, which is what
    every block written before the choice existed does (the CSS centred
    them), so an old block reads back correctly."""
    if content:
        m = re.search(r'data-align="(\w+)"', content)
        if m and m.group(1) in dict(CONTACT_ALIGNS):
            return m.group(1)
    return "center"


def read_contact_icon_size(content):
    """The icon size in pixels, or 0 meaning "whatever the zone says".
    0 is what every block written before the choice existed reads as."""
    if content:
        m = re.search(r'data-icon-size="(\d+)"', content)
        if m:
            return int(m.group(1))
    return 0


def read_contact_tool(content):
    """The rows behind a Contacts block, read back out of it.

    The exact inverse of build_contact_tool, and it has to be, because the
    block IS the storage: the phone number lives in the markup and there
    is no second copy for a form to read.
    """
    if not content or "cms-contact-tool" not in content:
        return []
    soup = BeautifulSoup(content, "html.parser")
    rows = []
    #  Every line this tool writes carries cms-contact-detail. Older
    #  blocks are the same elements with a kind in the class or a
    #  data-kind attribute, so one loop reads all three shapes.
    for node in soup.select(".cms-contact-detail, .cms-contact-icon"):
        classes = node.get("class") or []
        kind = node.get("data-kind") or next(
            (c[len("cms-contact-"):] for c in classes
             if c.startswith("cms-contact-") and c[len("cms-contact-"):] in LEGACY_KIND_ICONS), "")
        href = node.get("href") or ""
        text = node.select_one(".cms-contact-text")
        value = text.get_text(strip=True) if text else node.get_text(strip=True)
        #  The href is the truer copy for anything that became a link: a
        #  website row SHOWS "example.com" and links to the full address,
        #  and it is the full one the owner should get back in the field.
        if href.startswith("tel:"):
            #  The text, not the href: a phone number is written
            #  "01233 555 019" and dialled 01233555019, and the spacing is
            #  the owner's — handing back the stripped digits would quietly
            #  reformat their number the first time they opened the form.
            value = value or href[4:]
        elif href.startswith("mailto:"):
            value = href[7:]
        elif href:
            value = href
        elif kind == "copyright":
            value = value.lstrip("©").strip()
        #  data-kind is what an older block stored; the icon it implied
        #  is kept, so nothing loses its mark.
        icon = node.get("data-icon") or LEGACY_KIND_ICONS.get(kind, "")
        rows.append({"value": value, "icon": icon,
                     "show": (node.get("data-show") or "1") != "0"})
    #  An empty row the owner is part-way through typing is not published,
    #  so the wrapper carries how many boxes the form had; pad back to it.
    wrapper = soup.select_one(".cms-contact-tool")
    want = int(wrapper.get("data-rows") or 0) if wrapper else 0
    blanks = [int(x) for x in (wrapper.get("data-blanks") or "").split(",") if x.strip().isdigit()] if wrapper else []
    for at in sorted(blanks):
        if at <= len(rows) and len(rows) < MAX_CONTACT_ROWS:
            rows.insert(at, {"value": "", "icon": "", "show": True})
    while len(rows) < min(want, MAX_CONTACT_ROWS):
        rows.append({"value": "", "icon": "", "show": True})
    return rows


def apply_contact_form(content):
    """One submit of the Contacts form, applied whole.

    Same shape as the Accordion's: the form carries every row plus any +/-
    that was pressed, so a value typed in the same submit as "add a row"
    still lands. Shared by the section route and the Columns-cell route so
    the two cannot drift.
    """
    count = request.form.get("row_count", type=int) or 1
    count = max(0, min(MAX_CONTACT_ROWS, count))
    rows = []
    for i in range(count):
        rows.append({
            "value": (request.form.get("value_%d" % i) or "").strip(),
            "icon": (request.form.get("icon_%d" % i) or "").strip(),
            "show": request.form.get("show_%d" % i) == "1",
        })
    #  The + and - sit at the end of the row they act on, so they name it:
    #  "add_2" puts a new line under the third, "del_2" takes it away. A
    #  stepper at the top could only ever add at the bottom, which is the
    #  wrong end when the line you are looking at is in the middle.
    op = request.form.get("op") or ""
    if op.startswith("add_") and len(rows) < MAX_CONTACT_ROWS:
        at = int(op[4:]) if op[4:].isdigit() else len(rows) - 1
        rows.insert(min(at + 1, len(rows)), {"value": "", "icon": "", "show": True})
    elif op.startswith("del_") and op[4:].isdigit() and rows:
        at = int(op[4:])
        if 0 <= at < len(rows):
            rows.pop(at)
    #  An empty row is kept while the form is open (it is the one being
    #  filled in) but never written into the page -- build_contact_tool
    #  drops it, so a half-finished row is not published.
    layout = (request.form.get("layout") or "").strip() or read_contact_layout(content)
    align = (request.form.get("align") or "").strip() or read_contact_align(content)
    #  The slider only counts when the switch beside it is on; off is
    #  zero, which is the block saying nothing about size at all.
    icon_size = request.form.get("icon_size", type=int) or 0         if request.form.get("icon_size_on") == "1" else 0
    return build_contact_tool(rows, layout, icon_size, align)


def _resolve_tool_content(db, form):
    """Returns (section_type, content) for whichever tool the form
    describes (tool_id, block, or a raw type/columns count), or (None, None)
    if the tool no longer exists."""
    tool_id = form.get("tool_id", type=int)
    block = form.get("block")
    if tool_id:
        tool = db.execute("SELECT * FROM content_tools WHERE id = ?", (tool_id,)).fetchone()
        if not tool:
            return None, None
        if tool["block_key"] and tool["block_key"] in BLOCK_LIBRARY:
            return BLOCK_LIBRARY[tool["block_key"]]
        if tool["starter_content"] is not None:
            return tool["section_type"], tool["starter_content"]
        if tool["section_type"] == "columns":
            return "columns", json.dumps({"columns": [""] * 2})
        return tool["section_type"], ""
    if block and block in BLOCK_LIBRARY:
        return BLOCK_LIBRARY[block]
    section_type = form.get("type", "blank")
    if section_type != "blank" and section_type not in dict(SECTION_TYPES):
        section_type = "text"
    content = ""
    if section_type == "columns":
        count = form.get("columns", type=int) or 2
        count = max(1, min(6, count))
        content = json.dumps({"columns": [""] * count})
    return section_type, content


def _columns_section_or_404(section_id):
    db = get_db()
    section = db.execute("SELECT * FROM sections WHERE id = ? AND type = 'columns'", (section_id,)).fetchone()
    return db, section


#  How a Columns section apportions its width. Equal is the default and
#  what every column layout has always been; "wide-left"/"wide-right"
#  give one column more room -- a CV's main text beside a narrower
#  sidebar. A real control on the tool, styled centrally (site-base.css),
#  never a per-instance style. Only meaningful for two columns; three or
#  more stay equal.
COLUMN_WIDTHS = ("equal", "wide-left", "wide-right")


def _columns_data(section):
    try:
        data = json.loads(section["content"])
        return data if isinstance(data, dict) else {}
    except (ValueError, AttributeError, TypeError):
        return {}


def _get_columns_cells(section):
    return _columns_data(section).get("columns", [])


def columns_width_of(section):
    """The width preset stored on a Columns section (equal/wide-left/
    wide-right), for the render's fallback; "equal" when none is set."""
    w = _columns_data(section).get("width", "equal")
    return w if w in COLUMN_WIDTHS else "equal"


#  A preset maps to a ratio, so the render has one thing to read -- the
#  drag control stores a ratio directly, and the generator or an older
#  section may carry a preset instead.
_PRESET_RATIOS = {"wide-left": [1.7, 1.0], "wide-right": [1.0, 1.7]}


def columns_widths_of(section):
    """The column ratio, as a list of positive numbers (fr units), or
    None for an equal split. A dragged ratio wins; a preset is turned
    into one; equal is None, so every existing section is unchanged."""
    data = _columns_data(section)
    w = data.get("widths")
    if isinstance(w, list) and len(w) >= 2 and all(
            isinstance(x, (int, float)) and x > 0 for x in w):
        return [float(x) for x in w]
    return list(_PRESET_RATIOS.get(data.get("width", "equal"), []) or []) or None


def _columns_content(cells, width="equal", widths=None):
    #  Width rides on the same JSON as the cells. Equal is the default and
    #  is not written down -- an absent key IS equal, which keeps every
    #  existing section unchanged and the stored form minimal. A dragged
    #  RATIO (widths) is the precise form; a PRESET (width) is the coarse
    #  one an older section or the generator may carry.
    out = {"columns": cells}
    if isinstance(widths, list) and len(widths) >= 2 and all(
            isinstance(x, (int, float)) and x > 0 for x in widths):
        out["widths"] = [round(float(x), 3) for x in widths]
    elif width in COLUMN_WIDTHS and width != "equal":
        out["width"] = width
    return json.dumps(out)


def _save_columns_cells(db, section_id, cells):
    #  The cells changed; the width choice did not, so it is carried
    #  through rather than dropped -- editing a cell must not silently
    #  reset the layout back to equal.
    row = db.execute("SELECT content FROM sections WHERE id = ?", (section_id,)).fetchone()
    widths = columns_widths_of(row) if row else None
    width = columns_width_of(row) if row else "equal"
    db.execute("UPDATE sections SET content = ? WHERE id = ?",
               (_columns_content(cells, width, widths), section_id))
    db.commit()


def set_columns_widths(db, section_id, widths):
    """Store a dragged column ratio (a list of fr numbers), keeping the
    cells. An empty/short list clears it back to an equal split."""
    section = db.execute(
        "SELECT * FROM sections WHERE id = ? AND type = 'columns'",
        (section_id,)).fetchone()
    if not section:
        return False
    cells = _get_columns_cells(section)
    db.execute("UPDATE sections SET content = ? WHERE id = ?",
               (_columns_content(cells, "equal", widths), section_id))
    db.commit()
    return True


def set_columns_width(db, section_id, width):
    """Store the width choice on a Columns section, keeping its cells."""
    section = db.execute(
        "SELECT * FROM sections WHERE id = ? AND type = 'columns'",
        (section_id,)).fetchone()
    if not section:
        return False
    cells = _get_columns_cells(section)
    db.execute("UPDATE sections SET content = ? WHERE id = ?",
               (_columns_content(cells, width), section_id))
    db.commit()
    return True


def _normalize_cell(cell, type_hint="text"):
    """A cell is either a dict (a tool has been placed — carries its own
    type/content/tool_name, same shape a full section's row would if cells
    had their own table) or a bare string (legacy content from before cells
    had per-tool identity, or simply blank). Always returns a dict so every
    per-cell route has one shape to work with."""
    if isinstance(cell, dict):
        return dict(cell)
    if not cell:
        return {"type": "empty", "content": "", "tool_name": ""}
    return {"type": type_hint, "content": cell, "tool_name": type_hint.title()}


def _cell_slot(cells, col_index, row_index):
    """Resolves the (list, index) to read/write for a cell — either the
    column cell itself, or (when row_index is given) one of the cell's own
    rows once it's been divided. A row is a normal cell dict in every way
    (own type/content/tool_name) living inside cell["rows"] — dividing a
    column cell into rows lets each row hold its own independent tool,
    instead of rows being a client-side visual split of one shared tool's
    content. Returns None if col_index/row_index don't resolve."""
    if not (0 <= col_index < len(cells)):
        return None
    if row_index is None:
        return cells, col_index
    cell = _normalize_cell(cells[col_index])
    cells[col_index] = cell
    if cell.get("type") != "rows":
        return None
    rows = cell.setdefault("rows", [])
    if not (0 <= row_index < len(rows)):
        return None
    return rows, row_index


CARD_SHAPES = ("rectangle", "rounded", "oval", "circle", "pill")


def _update_banner_classes(content, shape, attachment):
    """Unlike Menu/Breadcrumb, Banner and Card carry free-text content the
    admin has typed over (headline, body text) — reshaping them can't just
    regenerate starter HTML from scratch like those two do, or it would
    wipe whatever's been written. Instead, only the outer wrapper's shape/
    attachment classes are swapped in place, via BeautifulSoup, leaving the
    overlay/text children untouched."""
    soup = BeautifulSoup(content or '<div class="cms-banner"><div class="cms-banner-overlay"></div></div>', "html.parser")
    div = soup.find(class_="cms-banner") or soup.find("div")
    if div is None:
        return content
    classes = [c for c in (div.get("class") or []) if c == "cms-banner" or (not c.startswith("cms-mask-") and c != "cms-banner-fixed")]
    if "cms-banner" not in classes:
        classes.insert(0, "cms-banner")
    shape = shape if shape in BANNER_SHAPES else "none"
    if shape != "none":
        classes.append(f"cms-mask-{shape}")
    attachment = attachment if attachment in BANNER_ATTACHMENTS else "scroll"
    if attachment == "fixed":
        classes.append("cms-banner-fixed")
    div["class"] = classes
    return str(soup)


#  A PORTRAIT ON A BANNER, the shape every profile page has settled on:
#  a round picture of a person overlapping the bottom edge of a wide one.
#
#  An option on the Banner rather than a tool of its own, because that is
#  what it is -- the same band, with a face on it. A tool would mean a
#  second thing to place, a second thing to style, and a rule about which
#  of the two owns the space they share.
#
#  It works with no background picture too: the band is then whatever
#  colour the section is, and the portrait sits on that. Somebody with a
#  headshot and no cover photograph should not have to find one.
BANNER_PORTRAITS = ("none", "left", "center", "right")

#  How big. A headshot on a CV wants more presence than the small round
#  avatar a contact strip wants, and the difference is not something one
#  number can settle for both. Sized as a FRACTION of the banner (see
#  site-base.css) so it holds its proportion whatever the banner's size.
BANNER_PORTRAIT_SIZES = ("small", "medium", "large")

#  And what shape. A round photo is the profile default; a square with
#  soft corners is the CV convention; an oval is the passport/portrait
#  one. The picture is the same file cropped by the frame, so this is a
#  class on the frame and nothing about the image itself.
BANNER_PORTRAIT_SHAPES = ("round", "square", "oval")


def _update_banner_portrait(content, position, size=None, shape=None, view="desktop"):
    """Where the portrait sits on a banner, how big, and what shape -- or
    that there is not one. `view` "mobile" stores the answer as a per-view
    override (cms-sm-*) that only applies at phone widths, over the
    desktop base.

    All in one call, because they are one control's worth of answer and
    setting them separately would mean a banner that briefly has a size
    and no position.
    """
    soup = BeautifulSoup(content or "", "html.parser")
    div = soup.find(class_="cms-banner") or soup.find("div")
    if div is None:
        return content
    position = position if position in BANNER_PORTRAITS else "none"
    if view in NON_DESKTOP_VIEWS:
        #  A per-VIEW override -- position/size/shape for one width band
        #  only, as prefixed classes layered on the desktop base. The
        #  figure is shared (created on desktop), so nothing is added or
        #  removed here but this view's classes; "none" hides it for the view.
        pre = VIEW_PREFIX[view]
        classes = [c for c in (div.get("class") or [])
                   if not c.startswith(pre + "has-portrait")
                   and not c.startswith(pre + "portrait-")]
        if position == "none":
            classes.append(pre + "portrait-none")
        else:
            classes.append(pre + "has-portrait-%s" % position)
            if size in BANNER_PORTRAIT_SIZES:
                classes.append(pre + "portrait-size-%s" % size)
            if shape in BANNER_PORTRAIT_SHAPES:
                classes.append(pre + "portrait-shape-%s" % shape)
        div["class"] = classes
        return str(soup)
    classes = [c for c in (div.get("class") or [])
               if not c.startswith("cms-has-portrait")
               and not c.startswith("cms-portrait-size-")
               and not c.startswith("cms-portrait-shape-")]
    figure = soup.find(class_="cms-banner-portrait")
    if position == "none":
        if figure:
            figure.decompose()
        div["class"] = classes
        return str(soup)
    classes.append("cms-has-portrait")
    classes.append("cms-has-portrait-%s" % position)
    size = size if size in BANNER_PORTRAIT_SIZES else "medium"
    classes.append("cms-portrait-size-%s" % size)
    shape = shape if shape in BANNER_PORTRAIT_SHAPES else "round"
    classes.append("cms-portrait-shape-%s" % shape)
    div["class"] = classes
    if not figure:
        #  Empty until a picture is chosen: an <img> with no src is a
        #  broken picture on the page, so the placeholder is a box the
        #  owner clicks, which is what every other picture control here
        #  does.
        figure = BeautifulSoup(
            '<figure class="cms-banner-portrait cms-banner-portrait-empty">'
            '<span class="cms-banner-portrait-hint">Choose a picture</span>'
            "</figure>", "html.parser").figure
        div.insert(0, figure)
    return str(soup)


def _set_banner_portrait_image(content, url):
    """The portrait's own picture, put in or taken out."""
    soup = BeautifulSoup(content or "", "html.parser")
    figure = soup.find(class_="cms-banner-portrait")
    if figure is None:
        return content
    for child in list(figure.children):
        child.extract()
    classes = [c for c in (figure.get("class") or [])
               if c != "cms-banner-portrait-empty"]
    if url:
        img = BeautifulSoup("<img>", "html.parser").img
        img["src"] = url
        img["alt"] = ""
        figure.append(img)
    else:
        classes.append("cms-banner-portrait-empty")
        hint = BeautifulSoup(
            '<span class="cms-banner-portrait-hint">Choose a picture</span>',
            "html.parser").span
        figure.append(hint)
    figure["class"] = classes
    return str(soup)


def banner_portrait_size_of(content, view="desktop"):
    """How big a banner's portrait is, for the control to show. A non-desktop
    view's own override (its cms-<prefix>portrait-size-*) wins; with none set
    the control shows the desktop value it inherits."""
    c = content or ""
    if view in NON_DESKTOP_VIEWS:
        pre = VIEW_PREFIX[view] + "portrait-size-"
        for size in BANNER_PORTRAIT_SIZES:
            if pre + size in c:
                return size
        return banner_portrait_size_of(content, "desktop")
    for size in BANNER_PORTRAIT_SIZES:
        if "cms-portrait-size-" + size in c:
            return size
    return "medium"


def banner_portrait_shape_of(content, view="desktop"):
    """What shape a banner's portrait is, for the control to show."""
    c = content or ""
    if view in NON_DESKTOP_VIEWS:
        pre = VIEW_PREFIX[view] + "portrait-shape-"
        for shape in BANNER_PORTRAIT_SHAPES:
            if pre + shape in c:
                return shape
        return banner_portrait_shape_of(content, "desktop")
    for shape in BANNER_PORTRAIT_SHAPES:
        if "cms-portrait-shape-" + shape in c:
            return shape
    return "round"


def banner_portrait_of(content, view="desktop"):
    """Which position a banner's portrait is in, for the control to show.
    A non-desktop view's own override wins; "none" means hidden on that view;
    otherwise the control shows the desktop position it inherits."""
    c = content or ""
    if view in NON_DESKTOP_VIEWS:
        pre = VIEW_PREFIX[view]
        if pre + "portrait-none" in c:
            return "none"
        for position in BANNER_PORTRAITS[1:]:
            if pre + "has-portrait-%s" % position in c:
                return position
        return banner_portrait_of(content, "desktop")
    for position in BANNER_PORTRAITS[1:]:
        if "cms-has-portrait-%s" % position in c:
            return position
    return "none"


# ---------------------------------------------------------------------------
# Per-view STRUCTURE overrides on a section (see sections.view_overrides in
# db.py). STRUCTURE and SIZE only -- never fonts or colours, which stay one
# look at every size. Two kinds so far:
#   hide  -- a list of views the section is HIDDEN on (independent per view,
#            not a base+override: "hidden on mobile" leaves desktop alone).
#   align -- text alignment per view (base + mobile override, like portrait:
#            mobile inherits desktop when unset).
# The desktop/mobile split matches the two edit buckets the View selector
# exposes; laptop/tablet reflow the desktop layout and store nothing of
# their own.
# ---------------------------------------------------------------------------
#  Four buckets now, one per size the View selector offers. Desktop is the
#  BASE (plain classes / base columns, applying at every width); the other
#  three are overrides, each scoped by CSS to its own width band (and, while
#  editing, to its cms-view-* canvas). A non-desktop view inherits the
#  desktop base for anything it has not set of its own.
PER_VIEW_VIEWS = ("desktop", "laptop", "tablet", "mobile")
#  The class prefix each view's overrides ride on. Mobile keeps its historical
#  cms-sm- prefix so banner content already stored keeps rendering; the two
#  new views get readable prefixes. Desktop has none -- it is the base.
VIEW_PREFIX = {"desktop": "", "laptop": "cms-laptop-", "tablet": "cms-tablet-", "mobile": "cms-sm-"}
NON_DESKTOP_VIEWS = ("laptop", "tablet", "mobile")
SECTION_ALIGNS = ("left", "center", "right")


def view_overrides_of(section):
    """The section's per-view structure overrides as a plain dict, always
    with the two known keys present and well-shaped."""
    raw = None
    try:
        raw = section["view_overrides"]
    except (KeyError, IndexError, TypeError):
        raw = getattr(section, "view_overrides", None) if not isinstance(section, dict) else section.get("view_overrides")
    data = {}
    if raw:
        try:
            data = json.loads(raw) or {}
        except (ValueError, TypeError):
            data = {}
    hide = data.get("hide")
    align = data.get("align")
    order = data.get("order") or {}
    mob_order = order.get("mobile")
    #  A dragged HEIGHT per non-desktop view (desktop's is the base, in the
    #  content_height_px column). A banner/hero that is right on a wide screen
    #  is often far too tall on a phone -- this lets each view be shrunk (or
    #  grown) without changing the others. Clamped the same as the base.
    height = data.get("height") or {}
    height_out = {}
    for v in NON_DESKTOP_VIEWS:
        px = height.get(v)
        try:
            if px and int(px) > 0:
                height_out[v] = max(60, min(2000, int(px)))
        except (ValueError, TypeError):
            pass
    return {
        "hide": [v for v in (hide or []) if v in PER_VIEW_VIEWS],
        "align": {v: a for v, a in (align or {}).items()
                  if v in PER_VIEW_VIEWS and a in SECTION_ALIGNS},
        #  A permutation of column indices for the MOBILE stack; validated
        #  against the real column count where it is read, so an out-of-date
        #  order (a column added or removed since) falls back to natural.
        "order": {"mobile": list(mob_order)} if isinstance(mob_order, list) else {},
        "height": height_out,
    }


def section_hidden_on(section, view):
    """Is the section hidden on this view? (Independent per view.)"""
    return view in view_overrides_of(section)["hide"]


def section_align_on(section, view):
    """The section's text alignment for a view; mobile inherits desktop when
    it has no override of its own. Empty string means 'no override' (the
    template leaves the theme's own alignment alone)."""
    align = view_overrides_of(section)["align"]
    if view in NON_DESKTOP_VIEWS:
        return align.get(view) or align.get("desktop") or ""
    return align.get("desktop") or ""


def section_view_classes(section):
    """The cms-sm-* / cms-view class string for a section's wrapper, built
    from its stored per-view overrides. Desktop values ride as plain classes
    (they are the base at every size); mobile values ride as cms-sm-* that
    win only at phone widths and in the Mobile editing canvas."""
    ov = view_overrides_of(section)
    out = []
    #  HIDE is independent per view (not base+override): hidden on one view
    #  leaves the others alone. Desktop keeps its historical class name.
    for view in ov["hide"]:
        out.append("cms-hide-desktop" if view == "desktop" else VIEW_PREFIX[view] + "hide")
    #  ALIGN and HEIGHT are base+override: desktop is the base class, each
    #  non-desktop view a prefixed override scoped to its width by CSS.
    for view, a in ov["align"].items():
        if not a:
            continue
        out.append("cms-align-%s" % a if view == "desktop" else VIEW_PREFIX[view] + "align-%s" % a)
    #  A dragged per-view height rides as a marker class; the pixel value
    #  itself travels as an inline --cms-content-height-<view>-px var (the
    #  template), which the class scopes to that view's width band.
    for view, px in ov["height"].items():
        if px:
            out.append(VIEW_PREFIX[view] + "has-custom-height")
    return " ".join(out)


def _write_view_overrides(db, section_id, data):
    #  Drop empty keys so a cleared override leaves no trace to read back.
    clean = {}
    if data.get("hide"):
        clean["hide"] = data["hide"]
    if data.get("align"):
        clean["align"] = data["align"]
    if data.get("order", {}).get("mobile"):
        clean["order"] = {"mobile": data["order"]["mobile"]}
    height = {v: px for v, px in (data.get("height") or {}).items() if px}
    if height:
        clean["height"] = height
    db.execute("UPDATE sections SET view_overrides = ? WHERE id = ?",
               (json.dumps(clean) if clean else None, section_id))
    db.commit()


def set_section_hidden(db, section_id, view, hidden):
    """Hide or show a section on one view, independently of the others."""
    if view not in PER_VIEW_VIEWS:
        return
    row = db.execute("SELECT view_overrides FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not row:
        return
    ov = view_overrides_of({"view_overrides": row["view_overrides"]})
    hide = set(ov["hide"])
    hide.discard(view) if not hidden else hide.add(view)
    ov["hide"] = [v for v in PER_VIEW_VIEWS if v in hide]
    _write_view_overrides(db, section_id, ov)


def set_section_align(db, section_id, view, align):
    """Set (or clear, with '') a section's text alignment for one view."""
    if view not in PER_VIEW_VIEWS:
        return
    row = db.execute("SELECT view_overrides FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not row:
        return
    ov = view_overrides_of({"view_overrides": row["view_overrides"]})
    if align in SECTION_ALIGNS:
        ov["align"][view] = align
    else:
        ov["align"].pop(view, None)
    _write_view_overrides(db, section_id, ov)


def section_height_override(section, view):
    """The section's dragged height override for a non-desktop view (px), or
    None. Desktop has no override here -- its height is the base
    content_height_px column."""
    return view_overrides_of(section)["height"].get(view)


#  Kept as an alias: some callers name the mobile one directly.
def section_mobile_height(section):
    return section_height_override(section, "mobile")


def set_section_height(db, section_id, view, px):
    """Set (or clear, with a falsy px) a section's dragged height for one view.
    Desktop is the BASE (the content_height_px column, so nothing about the
    stored desktop height changes shape); a non-desktop view is an override in
    view_overrides, applied only at that view's width -- so a tall hero can be
    cut down for a phone while the wider ones are left exactly as they were."""
    if view not in PER_VIEW_VIEWS:
        return
    row = db.execute("SELECT view_overrides FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not row:
        return
    try:
        px = max(60, min(2000, int(px))) if px else None
    except (ValueError, TypeError):
        px = None
    if view == "desktop":
        db.execute("UPDATE sections SET content_height_px = ? WHERE id = ?", (px, section_id))
        db.commit()
        return
    ov = view_overrides_of({"view_overrides": row["view_overrides"]})
    if px:
        ov["height"][view] = px
    else:
        ov["height"].pop(view, None)
    _write_view_overrides(db, section_id, ov)


def columns_mobile_order(section, n):
    """The stack order for a columns section on MOBILE, as a permutation of
    column indices. Natural order (0..n-1) unless the owner reordered it, and
    it reverts to natural if it no longer matches the column count."""
    perm = view_overrides_of(section)["order"].get("mobile")
    if perm and sorted(perm) == list(range(n)):
        return list(perm)
    return list(range(n))


def column_mobile_positions(section, n):
    """For each column index 0..n-1, its position in the mobile stack --
    the value that becomes its CSS `order` at phone widths."""
    perm = columns_mobile_order(section, n)
    return [perm.index(i) for i in range(n)]


def move_column_mobile_order(db, section_id, col_index, direction, n):
    """Swap a column one step earlier ('up') or later ('down') in the mobile
    stack, leaving the desktop left-to-right order untouched."""
    row = db.execute("SELECT view_overrides FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not row or n < 2:
        return
    ov = view_overrides_of({"view_overrides": row["view_overrides"]})
    perm = ov["order"].get("mobile")
    if not (perm and sorted(perm) == list(range(n))):
        perm = list(range(n))
    if col_index not in perm:
        return
    p = perm.index(col_index)
    q = p - 1 if direction == "up" else p + 1
    if 0 <= q < len(perm):
        perm[p], perm[q] = perm[q], perm[p]
    #  A natural order carries nothing -- keep the blob empty so "reset" is
    #  just moving everything back.
    ov["order"] = {} if perm == list(range(n)) else {"mobile": perm}
    _write_view_overrides(db, section_id, ov)


BANNER_POSITIONS = {
    "top-left": ("flex-start", "flex-start"), "top-center": ("flex-start", "center"), "top-right": ("flex-start", "flex-end"),
    "center-left": ("center", "flex-start"), "center-center": ("center", "center"), "center-right": ("center", "flex-end"),
    "bottom-left": ("flex-end", "flex-start"), "bottom-center": ("flex-end", "center"), "bottom-right": ("flex-end", "flex-end"),
}
BANNER_FONTS = {
    "default": "",
    "serif": "Georgia, 'Times New Roman', serif",
    "sans": "'Helvetica Neue', Arial, sans-serif",
    "mono": "'Courier New', monospace",
    "rounded": "'Trebuchet MS', 'Comic Sans MS', sans-serif",
    "elegant": "'Playfair Display', Georgia, serif",
}
BANNER_BOX_SHAPES = {
    "square": "0",
    "rounded": "8px",
    "large-rounded": "24px",
    "pill": "999px",
}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex_to_rgba(hex_color, opacity_pct):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    a = max(0, min(100, opacity_pct if opacity_pct is not None else 45)) / 100
    return f"rgba({r},{g},{b},{a:.2f})"


def _update_banner_overlay_style(content, form):
    """Applies the overlay text box's own styling — background color/
    opacity, text color/size/font/weight/style/alignment, and the whole
    box's position within the banner — on top of whatever text the admin
    has already typed into it. Position is stored on the outer .cms-banner
    div (it's the flex container the overlay sits inside); everything else
    lives on .cms-banner-overlay itself. Mirrors _update_banner_classes'
    "only touch known attributes, never the text children" approach."""
    soup, div = _banner_div(content)
    if div is None:
        return content
    overlay = div.find(class_="cms-banner-overlay")
    if overlay is None:
        overlay = soup.new_tag("div")
        overlay["class"] = "cms-banner-overlay"
        div.append(overlay)

    outer_props = _parse_style(div.get("style"))
    position = form.get("position", "")
    if position in BANNER_POSITIONS:
        align, justify = BANNER_POSITIONS[position]
        outer_props["align-items"] = align
        outer_props["justify-content"] = justify
    #  Framing the background PICTURE (not the text box): where its focal point
    #  sits (so an off-centre or portrait-orientation subject can be moved
    #  within the frame), whether it fills or shows whole, and how tall the
    #  banner stands (so a taller image gets the room it needs) -- all inline on
    #  .cms-banner, overriding the cover/center/min-height the stylesheet
    #  defaults to. The background-image itself is set elsewhere and preserved.
    bx = form.get("bg_pos_x", type=int)
    by = form.get("bg_pos_y", type=int)
    if bx is not None and by is not None:
        outer_props["background-position"] = f"{max(0, min(100, bx))}% {max(0, min(100, by))}%"
    bg_fit = form.get("bg_fit", "")
    if bg_fit in ("cover", "contain"):
        outer_props["background-size"] = bg_fit
    hero_h = form.get("hero_height", type=int)
    if hero_h:
        outer_props["min-height"] = f"{max(120, min(1200, hero_h))}px"
    else:
        outer_props.pop("min-height", None)
    outer_style = _style_str(outer_props)
    if outer_style:
        div["style"] = outer_style
    elif div.has_attr("style"):
        del div["style"]

    ov_props = _parse_style(overlay.get("style"))
    bg = (form.get("overlay_bg_color") or "").strip()
    opacity = form.get("overlay_opacity", type=int)
    if bg and HEX_RE.match(bg):
        ov_props["background"] = _hex_to_rgba(bg, opacity)
    text_color = (form.get("text_color") or "").strip()
    if text_color and HEX_RE.match(text_color):
        ov_props["color"] = text_color
    else:
        ov_props.pop("color", None)
    font_size = form.get("font_size", type=int)
    if font_size:
        ov_props["font-size"] = f"{max(10, min(96, font_size))}px"
    else:
        ov_props.pop("font-size", None)
    font_key = form.get("font_family", "default")
    if BANNER_FONTS.get(font_key):
        ov_props["font-family"] = BANNER_FONTS[font_key]
    else:
        ov_props.pop("font-family", None)
    if form.get("font_weight") == "bold":
        ov_props["font-weight"] = "700"
    else:
        ov_props.pop("font-weight", None)
    if form.get("font_style") == "italic":
        ov_props["font-style"] = "italic"
    else:
        ov_props.pop("font-style", None)
    text_align = form.get("text_align", "")
    if text_align in ("left", "center", "right"):
        ov_props["text-align"] = text_align
        # The button row (.cms-hero-actions) is a flex row, and text-align
        # cannot move a flex row -- so it reads --site-hero-justify instead
        # (see composition.css). Set it here, on the overlay the buttons sit
        # inside, from the SAME control, so the words and the buttons cannot
        # disagree ("centre the text but not the buttons" is the mismatch).
        ov_props["--site-hero-justify"] = {
            "left": "flex-start", "center": "center", "right": "flex-end",
        }[text_align]
    else:
        ov_props.pop("text-align", None)
        ov_props.pop("--site-hero-justify", None)
    box_padding = form.get("box_padding", type=int)
    if box_padding:
        padding = max(4, min(80, box_padding))
        ov_props["padding"] = f"{padding}px {padding + 8}px"
    else:
        ov_props.pop("padding", None)
    box_width = form.get("box_width", type=int)
    if box_width:
        # `width` (not just `max-width`) — the overlay is a flex item inside
        # .cms-banner, so with no explicit width it always shrink-wraps to
        # its longest line regardless of any cap, which made both the
        # slider and "Align" look broken (nothing to align/resize within).
        # An explicit width forces a real box other children/text-align
        # actually have room to work inside.
        ov_props["width"] = f"{max(20, min(100, box_width))}%"
    else:
        ov_props.pop("width", None)
    ov_props.pop("max-width", None)
    box_shape = form.get("box_shape", "")
    if box_shape in BANNER_BOX_SHAPES:
        ov_props["border-radius"] = BANNER_BOX_SHAPES[box_shape]
    else:
        ov_props.pop("border-radius", None)

    ov_style = _style_str(ov_props)
    if ov_style:
        overlay["style"] = ov_style
    elif overlay.has_attr("style"):
        del overlay["style"]

    return str(soup)


def banner_overlay_settings(content):
    """Read side of _update_banner_overlay_style — reconstructs the current
    form values (with sane defaults) from a banner's saved HTML, so the
    toolbar's controls reflect what's actually applied instead of always
    resetting to blank. Registered as a Jinja global (see app/__init__.py)
    so the banner_config_fields macro can call it directly."""
    soup, div = _banner_div(content)
    overlay = div.find(class_="cms-banner-overlay") if div is not None else None
    outer_props = _parse_style(div.get("style")) if div is not None else {}
    ov_props = _parse_style(overlay.get("style")) if overlay is not None else {}

    position = "center-center"
    pair = (outer_props.get("align-items", "center"), outer_props.get("justify-content", "center"))
    for key, val in BANNER_POSITIONS.items():
        if val == pair:
            position = key
            break

    bg_color, opacity = "#000000", 45
    bg = ov_props.get("background", "")
    m = re.match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", bg.replace(" ", ""))
    if m:
        bg_color = "#{:02x}{:02x}{:02x}".format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        opacity = round(float(m.group(4)) * 100)

    font_key = "default"
    font_family = ov_props.get("font-family", "")
    for key, stack in BANNER_FONTS.items():
        if stack and stack == font_family:
            font_key = key
            break

    return {
        "position": position,
        "overlay_bg_color": bg_color,
        "overlay_opacity": opacity,
        "text_color": ov_props.get("color", "#ffffff"),
        "font_size": re.sub(r"[^\d]", "", ov_props.get("font-size", "")) or "",
        "font_family": font_key,
        "font_weight": "bold" if ov_props.get("font-weight") in ("700", "bold") else "normal",
        "font_style": "italic" if ov_props.get("font-style") == "italic" else "normal",
        "text_align": ov_props.get("text-align", "center"),
        "box_padding": re.sub(r"[^\d]", "", (ov_props.get("padding", "").split()[0] if ov_props.get("padding") else "")) or "24",
        "box_shape": next((k for k, v in BANNER_BOX_SHAPES.items() if v == ov_props.get("border-radius")), "rounded"),
        "box_width": re.sub(r"[^\d]", "", ov_props.get("width", "")) or "80",
        #  Background-image framing (see _update_banner_overlay_style). Focal
        #  point defaults to centre (50/50), fit to cover, height to blank
        #  (the stylesheet's --site-hero-min stands).
        "bg_pos_x": (_bg_pos(outer_props.get("background-position", ""))[0]),
        "bg_pos_y": (_bg_pos(outer_props.get("background-position", ""))[1]),
        "bg_fit": (outer_props.get("background-size") if outer_props.get("background-size") in ("cover", "contain") else "cover"),
        "hero_height": re.sub(r"[^\d]", "", outer_props.get("min-height", "")) or "",
    }


def _bg_pos(value):
    """(x, y) percentages from a `background-position` like '30% 70%' -- default
    centre (50, 50) when unset or not a simple pair of percentages."""
    nums = re.findall(r"(\d+)%", value or "")
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return 50, 50


def _parse_style(style_str):
    props = {}
    for decl in (style_str or "").split(";"):
        if ":" not in decl:
            continue
        k, v = decl.split(":", 1)
        k = k.strip()
        if k:
            props[k] = v.strip()
    return props


def _style_str(props):
    return "; ".join(f"{k}:{v}" for k, v in props.items() if v)



#  Attributes the live editor adds to make a block editable. They belong
#  to the editing session, not to the page: contenteditable in stored
#  content is served to visitors, who can then type into a page that
#  cannot save what they typed.
EDITOR_ONLY_CLASSES = ("cms-block-editable",)


def strip_editor_markup(html):
    """Removes editing scaffolding from content on its way to storage.

    Inline editing saves a block by handing back its own outerHTML, which
    is the whole point -- the markup IS the stored value -- but that
    markup has been marked up in turn by the editor. Cleaned here rather
    than only in the browser so it holds for every route that stores
    content, including one written later.
    """
    if not html or ("contenteditable" not in html and "cms-block-editable" not in html):
        return html
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(attrs={"contenteditable": True}):
        del el["contenteditable"]
    for el in soup.find_all(class_=list(EDITOR_ONLY_CLASSES)):
        remaining = [c for c in (el.get("class") or []) if c not in EDITOR_ONLY_CLASSES]
        if remaining:
            el["class"] = remaining
        else:
            del el["class"]
    return str(soup)

def _card_div(content):
    soup = BeautifulSoup(content or '<div class="cms-card-shape"><p>Write here</p></div>', "html.parser")
    div = soup.find(class_="cms-card-shape") or soup.find("div")
    return soup, div


def _update_card_classes(content, shape, color):
    """Shape + optional solid background color. Any background-image
    already set (see _set_card_image) is left untouched — the two are
    independent, so reshaping a card never wipes out an image someone
    already uploaded, and vice versa."""
    soup, div = _card_div(content)
    if div is None:
        return content
    classes = [c for c in (div.get("class") or []) if c == "cms-card-shape" or not c.startswith("cms-card-")]
    if "cms-card-shape" not in classes:
        classes.insert(0, "cms-card-shape")
    shape = shape if shape in CARD_SHAPES else "rectangle"
    if shape != "rectangle":
        classes.append(f"cms-card-{shape}")
    div["class"] = classes
    props = _parse_style(div.get("style"))
    color = (color or "").strip()
    if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
        props["background-color"] = color
    else:
        props.pop("background-color", None)
    style = _style_str(props)
    if style:
        div["style"] = style
    elif div.has_attr("style"):
        del div["style"]
    return str(soup)



#  Schemes a button may point at. Everything else is dropped rather than
#  rewritten: an admin typing a link means a page, an email or a phone
#  number, and the one other thing that parses as a URL here is a script.
BUTTON_SCHEMES = ("http://", "https://", "mailto:", "tel:", "/", "#")

#  The optional heading above a tool: how it reads, and which tools get the
#  choice at all. Text, Card and Banner already carry a heading in their own
#  body, so they are the exceptions; every other tool can be given one.
HEADING_LEVELS = ("h2", "h3", "p")
HEADING_ALIGNS = ("left", "center", "right")
#  Section TYPES whose body already holds a heading -- no separate one.
_TYPES_WITH_BODY_HEADER = {"text", "card", "banner"}


def heading_level_of(value):
    return value if value in HEADING_LEVELS else "h2"


def heading_align_of(value):
    return value if value in HEADING_ALIGNS else "left"


def tool_allows_heading(section_type):
    """Whether a tool of this type can be given a separate heading above it
    -- everything except the three whose own body already has one."""
    return section_type not in _TYPES_WITH_BODY_HEADER


def apply_link_target(a_tag, new_tab):
    """Open a link in a NEW tab, or the CURRENT one. Stored on the <a> itself
    (target/rel) so the choice travels with the content and every link-bearing
    tool uses ONE convention -- no per-tool column, no auto rule based on
    http-vs-not. rel carries noopener/noreferrer whenever a link opens away,
    which is the safe default for target=_blank."""
    if new_tab:
        a_tag["target"] = "_blank"
        a_tag["rel"] = "noopener noreferrer"
    else:
        if a_tag.has_attr("target"):
            del a_tag["target"]
        if a_tag.has_attr("rel"):
            del a_tag["rel"]


def link_opens_new_tab(a_tag):
    """Read side of apply_link_target -- whether this <a> opens in a new tab."""
    return a_tag is not None and a_tag.get("target") == "_blank"


def _form_new_tab(form):
    """The 'open in new tab' choice from a submitted tool form."""
    return form.get("new_tab") in ("1", "on", "true")


def _normalize_button_href(link):
    """A button's link, tolerant of a scheme left off. An owner typing
    "reelpics.win" means https://reelpics.win, not a dead "#" -- the silent
    reset to "#" is exactly how a banner "lost its button link". A page path
    (/about), an anchor (#top), an email (mailto:) or a phone (tel:) are kept
    as they are; empty stays "#". Mirrors how block/CTA links are handled."""
    href = (link or "").strip()
    if not href:
        return "#"
    if href.startswith(BUTTON_SCHEMES):
        return href
    return "https://" + href


def card_button_settings(content):
    """Whether this card carries a button, and where it points.

    Read side of set_card_button, the same way card_style_settings is the
    read side of the shape/colour controls: the answer lives in the card's
    own markup, so the toolbar shows what is actually on the page even
    after somebody deletes the button by editing the card directly.
    """
    _, div = _card_div(content)
    button = div.find(class_="cms-card-btn") if div is not None else None
    return {
        "has_button": button is not None,
        "link": (button.get("href") or "") if button is not None else "",
        "text": button.get_text(strip=True) if button is not None else "",
        "new_tab": link_opens_new_tab(button),
    }


def set_card_button(content, enabled, link, new_tab=False):
    """Adds, updates or removes a card's button.

    A card could already hold a link -- the WYSIWYG toolbar makes one --
    but a link is underlined text, and every tool that wanted a real
    button so far grew its own (the pricing tier's, the call to action's,
    the file tool's). So this adds the missing thing rather than a fourth
    private one: one .cms-btn, which the others can be moved onto later.

    The text is not set here beyond a starter word. It is written on the
    page like every other piece of copy -- the button sits inside the
    card's own editable body, so it is already typed into rather than
    configured.
    """
    soup, div = _card_div(content)
    if div is None:
        return content
    button = div.find(class_="cms-card-btn")
    if not enabled:
        if button is not None:
            button.decompose()
        return str(soup)
    href = _normalize_button_href(link)
    if button is None:
        button = soup.new_tag("a")
        button["class"] = ["cms-btn", "cms-card-btn"]
        button.string = "Button"
        div.append(button)
    button["href"] = href
    apply_link_target(button, new_tab)
    return str(soup)

def _set_card_image(content, image_url):
    """Sets (or, when image_url is falsy, clears) the card's optional
    background image — independent of its solid color, so a card can show
    an image with the color as a fallback/tint behind transparent PNGs, or
    just a plain color with no image at all."""
    soup, div = _card_div(content)
    if div is None:
        return content
    props = _parse_style(div.get("style"))
    if image_url:
        props["background-image"] = f"url('{image_url}')"
    else:
        props.pop("background-image", None)
    style = _style_str(props)
    if style:
        div["style"] = style
    elif div.has_attr("style"):
        del div["style"]
    return str(soup)


def card_style_settings(content):
    """Read side of _update_card_classes/_set_card_image — the actual
    current shape/color/image state, so the config toolbar's controls
    reflect what's really applied instead of a hardcoded swatch. Registered
    as a Jinja global (see app/__init__.py) for the card_config_fields
    macro, same pattern as banner_overlay_settings."""
    soup, div = _card_div(content)
    classes = div.get("class") or [] if div is not None else []
    shape = next((c[len("cms-card-"):] for c in classes if c.startswith("cms-card-") and c != "cms-card-shape"), "rectangle")
    props = _parse_style(div.get("style")) if div is not None else {}
    return {
        "shape": shape,
        "color": props.get("background-color", ""),
        "has_image": "background-image" in props,
    }


def _reset_card_style(content):
    """Back to a plain default card: no shape modifier, no background
    color override, no background image — the one-click undo for however
    many individual shape/color/image changes an admin has made."""
    content = _update_card_classes(content, "rectangle", "")
    content = _set_card_image(content, None)
    return content


def _banner_div(content):
    soup = BeautifulSoup(content or '<div class="cms-banner"><div class="cms-banner-overlay"></div></div>', "html.parser")
    div = soup.find(class_="cms-banner") or soup.find("div")
    return soup, div


def set_banner_button(content, enabled, link, new_tab=False):
    """Adds, updates or removes a banner's button -- the same shape the
    Card tool's button takes (set_card_button), so a hero the generator
    made (which ships a `.cms-hero-actions` button) is managed by the same
    control an owner would use to add one by hand. The label is written on
    the page like every other word; this governs the link and whether the
    button is there at all.
    """
    soup, div = _banner_div(content)
    overlay = div.find(class_="cms-banner-overlay") if div is not None else None
    if overlay is None:
        return content
    actions = overlay.find(class_="cms-hero-actions")
    button = actions.find("a", class_="cms-btn") if actions is not None else None
    if not enabled:
        if actions is not None:
            actions.decompose()
        return str(soup)
    href = _normalize_button_href(link)
    if actions is None:
        actions = soup.new_tag("p")
        actions["class"] = ["cms-hero-actions"]
        overlay.append(actions)
    if button is None:
        button = soup.new_tag("a")
        button["class"] = ["cms-btn"]
        button.string = "Get in touch"
        actions.append(button)
    button["href"] = href
    apply_link_target(button, new_tab)
    return str(soup)


def banner_button_settings(content):
    """Whether a banner carries a button and where it points -- the read
    side of set_banner_button, so the control shows what is on the page."""
    _, div = _banner_div(content)
    button = None
    if div is not None:
        actions = div.find(class_="cms-hero-actions")
        button = actions.find("a", class_="cms-btn") if actions is not None else None
    return {"has_button": button is not None,
            "link": button.get("href", "") if button is not None else "",
            "new_tab": link_opens_new_tab(button)}


def _set_banner_image(content, image_url):
    """Same idea as _set_card_image — Banner never had its own image-change
    route before (only ever set once, at creation, to the placeholder), so
    this is the first thing that lets an admin (or the Generate button)
    replace a banner's background after the fact without editing raw HTML."""
    soup, div = _banner_div(content)
    if div is None:
        return content
    props = _parse_style(div.get("style"))
    if image_url:
        props["background-image"] = f"url('{image_url}')"
    else:
        props.pop("background-image", None)
    style = _style_str(props)
    if style:
        div["style"] = style
    elif div.has_attr("style"):
        del div["style"]
    return str(soup)


def _banner_dom_response(content):
    """The class/style attributes JS needs to apply a banner-update's
    result directly to the live .cms-banner/.cms-banner-overlay elements —
    lets the config form submit via fetch instead of a full page reload
    (which would otherwise reset the "Text box style" <details> back to
    closed, and drop the admin's place in the page, every time a select or
    the opacity slider changes)."""
    soup, div = _banner_div(content)
    overlay = div.find(class_="cms-banner-overlay") if div is not None else None
    figure = div.find(class_="cms-banner-portrait") if div is not None else None
    actions = overlay.find(class_="cms-hero-actions") if overlay is not None else None
    return {
        "class": " ".join(div.get("class") or []) if div is not None else "cms-banner",
        "style": div.get("style", "") if div is not None else "",
        "overlay_style": overlay.get("style", "") if overlay is not None else "",
        #  The portrait is a child, not an attribute, and the in-place
        #  update carried only attributes -- so choosing a portrait did
        #  nothing on screen until a refresh. Empty string means "none":
        #  the JS removes what is there.
        "portrait_html": str(figure) if figure is not None else "",
        #  The button is a child too -- adding, re-pointing or removing it
        #  did nothing on screen until a refresh for the same reason. Empty
        #  string means "no button": the JS removes what is there.
        "actions_html": str(actions) if actions is not None else "",
    }


def _accordion_panels(content):
    soup = BeautifulSoup(content or BLOCK_LIBRARY["image-accordion"][1], "html.parser")
    return soup, soup.find_all(class_="cms-accordion-panel")


def _set_accordion_panel_image(content, index, image_url):
    """Same pattern as _set_card_image/_set_banner_image, aimed at one
    panel (by position) instead of the section's single div — each of the
    5 panels has its own independent background image."""
    soup, panels = _accordion_panels(content)
    if index < 0 or index >= len(panels):
        return content
    div = panels[index]
    props = _parse_style(div.get("style"))
    if image_url:
        props["background-image"] = f"url('{image_url}')"
    else:
        props.pop("background-image", None)
    style = _style_str(props)
    if style:
        div["style"] = style
    elif div.has_attr("style"):
        del div["style"]
    return str(soup)


#  How the same 5 panels are laid out. The panels themselves — their
#  images, captions and markup — are identical in all three; only the
#  container's class changes, so switching style can never lose content.
#  Content saved before this existed carries no style class at all, which
#  the CSS reads as "panels" (see site-base.css).
ACCORDION_STYLES = (
    ("panels", "Panels (hover to expand)"),
    ("carousel", "Carousel (swipe / arrows)"),
    ("masonry", "Masonry (staggered grid)"),
    #  Two more, and the same rule as the first three: the PANELS are
    #  identical in all five and only the container's class changes, so
    #  switching display can never lose a picture or a caption.
    ("coverflow", "Cover flow (centre one, angled sides)"),
    ("deck", "Deck (a stack you click through)"),
)
ACCORDION_STYLE_PREFIX = "cms-accordion-style-"


ACCORDION_LIGHTBOX_CLASS = "cms-accordion-lightbox"


def accordion_settings(content):
    """The gallery's current display style and click-to-enlarge state,
    for the config form."""
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-image-accordion")
    classes = (box.get("class") or []) if box is not None else []
    style = next(
        (key for key, _ in ACCORDION_STYLES if f"{ACCORDION_STYLE_PREFIX}{key}" in classes),
        "panels",
    )
    panels = len(soup.find_all(class_="cms-accordion-panel"))
    return {
        "style": style,
        "lightbox": ACCORDION_LIGHTBOX_CLASS in classes,
        "panels": panels,
    }


MIN_ACCORDION_PANELS = 2
MAX_ACCORDION_PANELS = 12


def _accordion_panel_count(content, delta):
    """Adds or removes one panel at the end. Bounded rather than free: one
    panel isn't an accordion, and past a dozen the hover display gives each
    panel a slice too thin to read. A new panel starts on the placeholder
    image with a numbered caption — the same state a brand-new accordion's
    panels start in, so there is no second "empty panel" shape to style."""
    soup = BeautifulSoup(content or BLOCK_LIBRARY["image-accordion"][1], "html.parser")
    box = soup.find(class_="cms-image-accordion")
    if box is None:
        return content
    panels = soup.find_all(class_="cms-accordion-panel")
    if delta > 0:
        if len(panels) >= MAX_ACCORDION_PANELS:
            return content
        new_panel = BeautifulSoup(
            '<div class="cms-accordion-panel" tabindex="0" '
            "style=\"background-image:url('/static/img/placeholder.svg')\">"
            f'<span class="cms-accordion-caption">Panel {len(panels) + 1}</span></div>',
            "html.parser",
        )
        box.append(new_panel)
    elif delta < 0:
        if len(panels) <= MIN_ACCORDION_PANELS:
            return content
        panels[-1].decompose()
    return str(soup)


def _set_accordion_lightbox(content, enabled):
    """Click-to-enlarge is a behaviour, not a layout — it rides on top of
    whichever of the three displays is chosen, so it gets its own class
    rather than being a fourth style. Kept separate from the style class
    for the same reason: switching display must not silently turn it off."""
    soup = BeautifulSoup(content or BLOCK_LIBRARY["image-accordion"][1], "html.parser")
    box = soup.find(class_="cms-image-accordion")
    if box is None:
        return content
    classes = [c for c in (box.get("class") or []) if c != ACCORDION_LIGHTBOX_CLASS]
    if enabled:
        classes.append(ACCORDION_LIGHTBOX_CLASS)
    box["class"] = classes
    return str(soup)


def _set_accordion_style(content, style):
    """Swaps the container's style class, leaving every panel untouched."""
    if style not in dict(ACCORDION_STYLES):
        return content
    soup = BeautifulSoup(content or BLOCK_LIBRARY["image-accordion"][1], "html.parser")
    box = soup.find(class_="cms-image-accordion")
    if box is None:
        return content
    classes = [c for c in (box.get("class") or []) if not c.startswith(ACCORDION_STYLE_PREFIX)]
    classes.append(f"{ACCORDION_STYLE_PREFIX}{style}")
    box["class"] = classes
    return str(soup)


def _set_accordion_captions(content, captions):
    """Rewrites all 5 captions in one pass — the config form submits every
    caption field together (like Divider's style selects), rather than one
    request per panel, since they're plain text with no independent
    async action (upload/generate) the way each panel's image has."""
    soup, panels = _accordion_panels(content)
    for i, panel in enumerate(panels):
        if i >= len(captions):
            break
        caption_el = panel.find(class_="cms-accordion-caption")
        if caption_el is not None:
            caption_el.string = captions[i]
    return str(soup)


def apply_accordion_form(content):
    """Applies one whole submit of the Image Accordion config form to
    `content` and returns the new markup. Shared by the section-level and
    Columns-cell routes so the two can't drift — the form is identical in
    both places, and it carries the tool's entire state (every caption,
    the display style, the click-to-enlarge flag, and any panel +/- that
    was pressed).

    Order matters: captions are applied FIRST so a caption typed in the
    same submit as a "remove panel" click still lands on the panels that
    survive."""
    count = request.form.get("panel_count", type=int) or 5
    count = max(0, min(MAX_ACCORDION_PANELS, count))
    content = _set_accordion_captions(
        content, [request.form.get(f"caption_{i}", "") for i in range(count)]
    )
    op = (request.form.get("op") or "").strip()
    if op in ("add_panel", "remove_panel"):
        content = _accordion_panel_count(content, 1 if op == "add_panel" else -1)
    if request.form.get("style"):
        content = _set_accordion_style(content, request.form.get("style"))
        #  Only meaningful alongside a style field, i.e. a real submit of
        #  the tool's config form — an unchecked checkbox sends nothing,
        #  so its absence has to mean "off" rather than "unchanged".
        content = _set_accordion_lightbox(content, request.form.get("lightbox") == "1")
    return content


def _save_card_image_file():
    """The picture for a Card or a Banner: uploaded, or chosen from the
    Media Library.

    A library pick is a URL, not a filename, and is never trusted as one:
    it is checked against what is actually IN the library and the value
    used is the library's own. That is the same rule the other upload
    helper follows -- there are two of these, which is one more than
    there should be, and until they are one the check has to be in both.
    """
    picked = (request.form.get("library_url") or "").strip()
    if picked:
        known = {item["url"]: item for item in _list_media(image_only=True)}
        if picked not in known:
            return None, ("That picture is not in your Media Library any more "
                          "— choose another.", 400)
        return picked, None

    file = request.files.get("image")
    if not file or file.filename == "":
        return None, ("Please choose an image file.", 400)
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        return None, ("Please upload a PNG, JPG, GIF, WEBP, or SVG image.", 400)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name))
    return f"/static/uploads/{unique_name}", None


IMAGE_WIDTH_PX = {"small": (400, 300), "medium": (800, 600), "large": (1200, 800), "full": (1600, 900)}
BANNER_SIZE_PX = (1600, 600)
CARD_SIZE_PX = (800, 800)
ACCORDION_PANEL_SIZE_PX = (500, 700)
#  The Media Player renders a full-width landscape player, so its clips
#  have to be asked for in that shape — the generation Tool this was
#  built against defaults to portrait if nothing says otherwise. 832x480
#  is 16:9 at a size a text-to-video model can actually hold together.
VIDEO_SIZE_PX = (832, 480)


MAX_GENERATE_COUNT = 4


def _generate_and_save_images(db, width, height):
    """Returns (images, error) — reads `prompt` and `count` (1-4, default
    1) from the current request. Every image generated is saved as a
    normal upload (so everything downstream treats it exactly like a
    manually-uploaded file) AND recorded in generated_images — kept
    around and reusable/deletable from the Image Library regardless of
    whether it ends up applied anywhere. Stops at the first failure and
    returns whatever succeeded before that, with the error, rather than
    discarding partial results (generation is slow enough that losing 2
    good images because a 3rd failed would be a bad trade)."""
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return [], "Please describe the image you want."
    count = request.form.get("count", type=int) or 1
    count = max(1, min(MAX_GENERATE_COUNT, count))
    images = []
    for _ in range(count):
        try:
            image_bytes = ai_image.generate_image(db, prompt, width=width, height=height)
        except ai_image.ImageGenError as e:
            return images, (str(e) if not images else f"Generated {len(images)}, then: {e}")
        unique_name = f"{uuid.uuid4().hex}.png"
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
            f.write(image_bytes)
        url = f"/static/uploads/{unique_name}"
        cur = db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
        db.commit()
        images.append({"id": cur.lastrowid, "url": url})
    return images, None


def _generate_and_save_video(db):
    """Returns (url, error) — reads `prompt` from the current request.
    Unlike images, always exactly one clip: generation is slow (minutes,
    not seconds) and there's no video-library equivalent to browse
    several candidates in afterward, so pick-of-N isn't worth the cost."""
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return None, "Please describe the video you want."
    try:
        video_bytes = ai_video.generate_video(db, prompt, width=VIDEO_SIZE_PX[0], height=VIDEO_SIZE_PX[1])
    except ai_video.VideoGenError as e:
        return None, str(e)
    unique_name = f"{uuid.uuid4().hex}.mp4"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(video_bytes)
    return f"/static/uploads/{unique_name}", None


def _apply_image_to_slot(db, section_id, col_index, kind, url):
    """The one place that actually applies a chosen image URL (freshly
    generated, or picked from the Library) to a section or a Columns
    cell — shared by both the picker (after multi-generate) and the
    Library "Use this image" flow, so there's exactly one implementation
    of "what does applying an image to an Image/Banner/Card slot mean"."""
    if col_index is None:
        section = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not section:
            return False
        if kind == "image":
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (url, section_id))
        elif kind == "banner":
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (_set_banner_image(section["content"], url), section_id))
        elif kind == "card":
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (_set_card_image(section["content"], url), section_id))
        else:
            return False
        db.commit()
        return True

    db2, section = _columns_section_or_404(section_id)
    if not section:
        return False
    row_index = request.args.get("row", type=int)
    cells = _get_columns_cells(section)
    slot = _cell_slot(cells, col_index, row_index)
    if slot is None:
        return False
    container, idx = slot
    if kind == "image":
        cell = _normalize_cell(container[idx], "image")
        cell["type"] = "image"
        cell["content"] = url
    elif kind == "banner":
        cell = _normalize_cell(container[idx], "banner")
        cell["type"] = "banner"
        cell["content"] = _set_banner_image(cell.get("content", ""), url)
        cell.setdefault("tool_name", "Banner")
    elif kind == "card":
        cell = _normalize_cell(container[idx], "card")
        cell["type"] = "card"
        cell["content"] = _set_card_image(cell.get("content", ""), url)
        cell.setdefault("tool_name", "Card")
    else:
        return False
    container[idx] = cell
    _save_columns_cells(db2, section_id, cells)
    return True


MEDIA_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _list_media(image_only=False):
    """Every file sitting in UPLOAD_FOLDER, newest first, enriched with
    prompt/created_at from generated_images where available. Uploads have
    no DB row of their own (they're just saved straight to disk by ~9
    different upload routes), so the filesystem is the source of truth
    for "what exists" and the DB is only extra metadata layered on top —
    this is what lets the Library show uploads and AI generations side
    by side without having to retrofit every upload call site."""
    db = get_db()
    gen_rows = {
        row["url"].rsplit("/", 1)[-1]: row
        for row in db.execute("SELECT * FROM generated_images ORDER BY id DESC").fetchall()
    }
    folder = current_app.config["UPLOAD_FOLDER"]
    items = []
    if os.path.isdir(folder):
        for filename in os.listdir(folder):
            path = os.path.join(folder, filename)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if image_only and ext not in MEDIA_IMAGE_EXTS:
                continue
            gen = gen_rows.get(filename)
            items.append({
                "filename": filename,
                "url": f"/static/uploads/{filename}",
                "is_image": ext in MEDIA_IMAGE_EXTS,
                "prompt": gen["prompt"] if gen else None,
                "source": "AI generated" if gen else "Uploaded",
                "created_at": gen["created_at"] if gen else None,
                "mtime": os.path.getmtime(path),
            })
    items.sort(key=lambda it: it["created_at"] or "", reverse=False)
    items.sort(key=lambda it: it["mtime"], reverse=True)
    for item in items:
        #  An upload is the owner's own file and theirs to delete. What
        #  follows below is not.
        item["owned_by"] = None
        item["can_delete"] = True
    return items + _installed_template_media(db, image_only=image_only)


def _installed_template_media(db, image_only=False):
    """The pictures every INSTALLED template brought with it.

    The Media Library used to list uploads only, and on a site whose
    pictures all came from its template that means an empty screen headed
    "Media Library" -- which reads as "you have no pictures" while
    seventy-seven of them are on disk and on the page.

    They are listed and NOT deletable, and that is the honest pair: they
    are on screen because an owner looking for a picture should find every
    picture, and they are locked because each belongs to a template that
    would be left with a hole in it. Deleting the template removes them,
    which is where that decision belongs.
    """
    themes = os.path.join(current_app.static_folder, "themes")
    if not os.path.isdir(themes):
        return []
    names = {row["slug"]: row["name"]
             for row in db.execute("SELECT slug, name FROM templates").fetchall()}
    out = []
    for slug in sorted(os.listdir(themes)):
        folder = os.path.join(themes, slug, "media")
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder)):
            path = os.path.join(folder, filename)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(filename)[1].lower()
            #  Same rule the uploads listing uses: everything, unless the
            #  caller asked for pictures only.
            if image_only and ext not in MEDIA_IMAGE_EXTS:
                continue
            out.append({
                "filename": filename,
                "url": f"/static/themes/{slug}/media/{filename}",
                "is_image": ext in MEDIA_IMAGE_EXTS,
                "prompt": None,
                "source": "From the %s template" % (names.get(slug) or slug),
                "owned_by": names.get(slug) or slug,
                "can_delete": False,
                "created_at": None,
                "mtime": os.path.getmtime(path),
            })
    return out




#  ---------------------------------------------------------------------
#  Table + Video Gallery tool state
#  ---------------------------------------------------------------------
#  Both tools shipped as a tool tile plus starter markup with no dedicated
#  editing form, so the only way to change a table's shape or a gallery's
#  clips was the raw "Edit HTML" escape hatch — exactly what CLAUDE.md's
#  tool-usage rule exists to prevent (same gap Image Accordion had). The
#  two are fixed differently on purpose:
#
#  * A Table's content IS text — its cells stay contenteditable, so its
#    structure edits (add/remove row/column, header row on/off, style)
#    happen in the live DOM and ride the normal WYSIWYG save, the same way
#    the old table-style button already did. Nothing to write here beyond
#    reading the current shape back out for the form's own controls.
#  * A Video Gallery's content is pure structure — a thumbnail URL and a
#    data attribute derived from a YouTube id, no free text — so it's
#    locked out of contenteditable and rebuilt server-side from the
#    submitted clip list, the same way the Menu tool is.


#  ---------------------------------------------------------------------
#  FAQ tool
#  ---------------------------------------------------------------------
#  Built on <details>/<summary>, which means the open/close behaviour, the
#  keyboard support and the screen-reader semantics are the browser's
#  rather than ours — no JS at all. "One at a time" is the same story: the
#  `name` attribute makes a set of <details> mutually exclusive natively,
#  so an accordion that closes its siblings costs one attribute instead of
#  an event handler.
FAQ_STYLES = (
    ("list", "List (divided rows)"),
    ("cards", "Cards (separated)"),
    ("plain", "Plain (no borders)"),
)
FAQ_STYLE_PREFIX = "cms-faq-style-"
MIN_FAQ_ITEMS = 1
MAX_FAQ_ITEMS = 15



#  What an answer may contain. Deliberately tiny: an FAQ answer is two or
#  three sentences, and every formatting option beyond this is a way to
#  make one answer look unlike the rest. Written as text and converted
#  here, never entered as HTML -- the tool has to be able to read an
#  answer back out to edit it, and it cannot do that with whatever markup
#  somebody pasted in.
FAQ_FORMATTING_HELP = "**bold**, *italic*, [words](/a-page), or lines starting with - for a list"


def faq_markdown(text):
    """The small formatting vocabulary an FAQ answer may use.

    Escaped first and converted second, so the input is text throughout
    and no tag can arrive by being typed. Links are held to the same
    schemes a button may use, for the same reason.
    """
    escaped = html_escape((text or "").strip())
    if not escaped:
        return ""

    def link(match):
        label, href = match.group(1), match.group(2).strip()
        if not href.startswith(BUTTON_SCHEMES):
            return match.group(0)  # left as the literal text it was
        return '<a href="' + href + '">' + label + "</a>"

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, escaped)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)

    #  Consecutive "- " lines become one list; everything else is a
    #  paragraph-ish line break, which is all a short answer needs.
    lines, html, bullets = out.split("\n"), [], []

    def flush():
        if bullets:
            html.append("<ul>" + "".join("<li>" + b + "</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        else:
            flush()
            if stripped:
                html.append(stripped)
    flush()
    if not html:
        return ""
    if len(html) == 1 and not html[0].startswith("<ul>"):
        return html[0]
    return "".join(
        part if part.startswith("<ul>") else "<p>" + part + "</p>" for part in html
    )

def faq_group_name(name, questions):
    """The accordion group for one FAQ block, derived from its own words.

    `<details name=...>` makes everything sharing a name mutually
    exclusive, so the name has to be unique per BLOCK — two FAQ blocks on
    one page sharing it would behave as a single accordion, and opening a
    question in the second would silently close one in the first.

    It used to be `uuid4().hex[:8]`, regenerated on every rebuild. Unique,
    but random: two installs of the same template produced pages differing
    by that one token, which was the last thing standing between two hosts
    and byte-identical output. Deriving it is the same rule this file
    already applies to a question's id — the slug of its own words —
    rather than a second convention.

    The name and the questions, because `data-faq-name` exists precisely
    to tell two sets on one page apart. Two blocks matching on both are
    the same set of questions shown twice, and the app has nothing else to
    distinguish them by.
    """
    sep = chr(31)
    seed = sep.join([(name or "").strip()] + [(q or "").strip() for q in questions])
    return "cms-faq-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def build_faq(items, style="list", one_at_a_time=True, name=""):
    """Rebuilds the whole block from the question/answer list — the same
    derived-markup rule the Menu and Video Gallery tools follow, so the
    stored HTML can never drift from what the form says."""
    style = style if style in dict(FAQ_STYLES) else "list"
    group = (' name="%s"' % faq_group_name(name, [i.get("q") for i in items[:MAX_FAQ_ITEMS]])
             if one_at_a_time else "")
    rows = []
    taken = set()
    for item in items[:MAX_FAQ_ITEMS]:
        q_source = (item.get("q") or "").strip()
        q = html_escape(q_source) or "Your question here"
        #  Both: the source, so the tool can hand it back to be edited,
        #  and the rendered form, so the page shows what it means. Same
        #  reasoning as the pricing tier's data-flag -- a class is
        #  styling, and the form still has to read the answer back.
        a_source = (item.get("a") or "").strip() or "Your answer here."
        a = faq_markdown(a_source) or html_escape(a_source)
        #  Each question keeps an id of its own, for life. Another FAQ
        #  block elsewhere on the site can then show this question by
        #  reference rather than by copying its words, which is what lets
        #  a wording change on the FAQ page reach every page repeating it.
        #  Unlike the group name above, this one MUST survive a rebuild —
        #  regenerate it and every reference to it breaks.
        #  Stored id wins, for life. Without one, the slug of the
        #  question's own words rather than a random token — the rule the
        #  document-shaped FAQ already follows, and the reason a starter
        #  block is the same markup on every install instead of differing
        #  by eight characters generated at import time.
        fid = (item.get("id") or "").strip() or faq_slug(q_source or "question", taken)
        taken.add(fid)
        rows.append(
            f'<details class="cms-faq-item" id="faq-{html_escape(fid)}" data-faq-id="{html_escape(fid)}"{group}>'
            f'<summary class="cms-faq-q">{q}</summary>'
            f'<div class="cms-faq-a" data-md="{html_escape(a_source, quote=True)}">{a}</div>'
            "</details>"
        )
    if not rows:
        #  The starter question is a question like any other, so it gets an
        #  id like any other. Without one it could not be mirrored until it
        #  had been saved once -- meaning a brand new FAQ page offered
        #  nothing to a block trying to show its questions.
        rows.append(
            f'<details class="cms-faq-item" data-faq-id="{faq_slug("Your question here", set())}"{group}>'
            '<summary class="cms-faq-q">Your question here</summary>'
            '<div class="cms-faq-a">Your answer here.</div></details>'
        )
    body = chr(10) + chr(10).join(rows) + chr(10)
    #  What this set of questions is called. A page can hold more than one
    #  -- house rules and delivery, say -- and a reader elsewhere has to be
    #  able to tell them apart. The page's title alone cannot: two sets on
    #  one page would both answer to it.
    label = f' data-faq-name="{html_escape((name or "").strip(), quote=True)}"' if (name or "").strip() else ""
    return f'<div class="cms-faq {FAQ_STYLE_PREFIX}{style}"{label}>' + body + "</div>"


def faq_settings(content):
    """Current questions, answers, style and grouping — for the config
    form. Answers are read as plain text: this tool never stores markup an
    admin would have to hand-edit."""
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-faq")
    if box is None:
        return {"items": [], "style": "document", "one_at_a_time": True, "is_reader": False,
                "name": "", "md": "", "intro": "",
                "mirror_source": None, "mirror_ids": [], "show_contents": False}
    classes = box.get("class") or []
    #  FAQ_VIEWS carries the old three styles plus "document", so a block
    #  written before the document view existed still reads correctly.
    style = next(
        (key for key, _ in FAQ_VIEWS if f"{FAQ_STYLE_PREFIX}{key}" in classes), "list"
    )
    items, grouped = [], False
    for det in box.find_all(class_="cms-faq-item"):
        if det.get("name"):
            grouped = True
        q_el = det.find(class_="cms-faq-q")
        a_el = det.find(class_="cms-faq-a")
        items.append({
            "id": det.get("data-faq-id") or "",
            "q": q_el.get_text() if q_el else "",
            #  What was typed, not what it turned into — editing has to
            #  start from the same text the admin wrote.
            "a": (a_el.get("data-md") if a_el and a_el.has_attr("data-md")
                  else (a_el.get_text() if a_el else "")),
        })
    source = box.get("data-faq-source")
    #  The document is the authority once a block has one: what is
    #  rendered below it is a view of this, not the other way round.
    md = box.get("data-faq-md")
    if md is not None:
        parsed = parse_faq_document(md)
        items = parsed["items"]
        intro = parsed["intro"]
    else:
        #  Written before the document existed. Its questions ARE a
        #  document — headings and answers — so one is reconstructed
        #  rather than showing an empty box under a page full of
        #  questions. Saving once stores it properly.
        md, intro = faq_document_source(content), ""
    return {
        "md": md,
        #  The same document, as something to edit on the page. Built here
        #  so the toolbar never has to render one thing and store another.
        "editor_html": faq_editor_html(md),
        "intro": intro,
        #  What kind of FAQ block this is. A reader that has not been
        #  pointed anywhere yet is still a reader — keyed on the class, so
        #  a freshly dropped one gets the reader's controls rather than
        #  being mistaken for an empty set of questions.
        "is_reader": "cms-faq-mirror" in classes,
        "name": box.get("data-faq-name") or "",
        "items": items, "style": style, "one_at_a_time": grouped,
        #  A mirror holds no words of its own — only which questions it
        #  shows and where they live.
        "mirror_source": int(source) if (source or "").isdigit() else None,
        "mirror_ids": [i for i in (box.get("data-faq-ids") or "").split(",") if i],
        "show_contents": box.get("data-faq-contents") == "1",
    }



#  An FAQ is a document, not a row-at-a-time form.
#
#  It was built as a list of question/answer pairs, each typed into its
#  own pair of boxes. That is fine for three questions and unusable for
#  forty — and forty is what a real FAQ page is. Nobody writes one that
#  way either: they write it, or are handed it, as a document.
#
#  So the tool holds one Markdown document, which can be pasted in whole.
#  Every heading is a question and everything under it is that answer,
#  which is how a written FAQ already looks. How it is SHOWN is then a
#  separate choice — read straight through as a document, or folded into
#  rows that open — and the same text serves both.

#  Reads an FAQ however it was typed, and stores whatever was typed --
#  this only decides how it is READ, so nobody's text is rewritten under
#  them.
#
#  The plain shape needs no syntax: a question, its answer underneath, a
#  blank line before the next.
#
#      Do you deliver?
#      Within five miles, yes.
#
#  Marked-up shapes win when present -- lines beginning with #, "Q:", or
#  numbered -- because they say explicitly where each question starts,
#  which is what lets an answer run to several paragraphs.

FAQ_MARKER_RES = (
    re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$"),        # # Question
    re.compile(r"^\s*Q\s*[:.\)]\s*(.+?)\s*$", re.I),        # Q: Question
    re.compile(r"^\s*\d{1,3}\s*[\.\)]\s+(.+?)\s*$"),        # 1. Question
)
#  "A:" opens an answer in the same documents that use "Q:", and carries
#  no information of its own once the question above it is understood.
FAQ_ANSWER_PREFIX_RE = re.compile(r"^\s*A\s*[:.\)]\s*", re.I)


def _marked_question(line):
    for pattern in FAQ_MARKER_RES:
        found = pattern.match(line)
        if found:
            return found.group(1).strip()
    return None


def normalise_faq_source(text):
    """Whatever was typed, as one canonical document.

    Returns the same text rewritten so every question is a `# ` line,
    which is the single shape everything downstream reads. Only used for
    reading — see the note above about not rewriting what was typed.
    """
    lines = (text or "").splitlines()
    if any(_marked_question(line) is not None for line in lines):
        out = []
        for line in lines:
            question = _marked_question(line)
            if question is not None:
                out.append(f"# {question}")
            else:
                out.append(FAQ_ANSWER_PREFIX_RE.sub("", line))
        return "\n".join(out)

    #  Nothing marked: a blank line separates one question from the next,
    #  and the first line of each block is the question.
    #
    #  A question is a line with an answer underneath it. That one rule
    #  also settles the introduction, which would otherwise become the
    #  first question: a paragraph on its own at the top has no answer
    #  under it, so it is not a question. Only leading blocks count as
    #  introduction -- a lone line further down is a question somebody
    #  has not answered yet, which is worth being told about rather than
    #  silently turning into prose.
    blocks, current = [], []
    for line in lines:
        if line.strip():
            current.append(line)
        else:
            if current:
                blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    first_question = next((i for i, b in enumerate(blocks) if len(b) > 1), None)
    if first_question is None:
        first_question = 0  # nothing has an answer; read them all as questions

    out = []
    for index, block in enumerate(blocks):
        if index < first_question:
            out.extend(block)
            out.append("")
            continue
        out.append("# " + block[0].strip())
        out.append("")
        out.extend(FAQ_ANSWER_PREFIX_RE.sub("", b) for b in block[1:])
        out.append("")
    return chr(10).join(out).strip()


FAQ_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")

#  "document" reads top to bottom; the rest fold each answer away until
#  its question is clicked. The stored text is identical either way.
FAQ_VIEWS = (
    ("document", "Document — read straight through"),
    ("list", "Expandable rows"),
    ("cards", "Expandable cards"),
    ("plain", "Expandable, no lines"),
)


def faq_slug(text, taken):
    """A question's id, derived from its own words.

    Derived rather than stored, so a document can be pasted in whole and
    still be referenced question by question — there is nowhere to hide a
    generated id in text somebody is going to edit by hand. The trade is
    that rewording a question changes its id, and a Reader showing it
    will fall back to the next question rather than following the change.
    That is the right way round: a reworded question is usually a
    different question, and the alternative is invisible ids cluttering
    the document.
    """
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "q"
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    taken.add(slug)
    return slug


def parse_faq_document(md):
    """{intro, items} from a Markdown FAQ.

    Anything before the first heading is an introduction and stays as
    one — a real FAQ often opens with a line about who to ask if the
    answer is not here, and losing it on paste would be a bad surprise.
    """
    #  Read whatever was typed, in whichever shape it was typed — see
    #  normalise_faq_source. Nothing downstream needs to know there was
    #  more than one shape.
    md = normalise_faq_source(md)
    intro, items = [], []
    question, buffer, taken = None, [], set()

    def flush():
        if question is not None:
            items.append({
                "id": faq_slug(question, taken),
                "q": question,
                "a": "\n".join(buffer).strip(),
            })

    for line in (md or "").splitlines():
        heading = FAQ_HEADING_RE.match(line)
        if heading:
            flush()
            question, buffer = heading.group(1).strip(), []
        elif question is None:
            intro.append(line)
        else:
            buffer.append(line)
    flush()
    return {"intro": "\n".join(intro).strip(), "items": items}


def build_faq_document(md, view="document", one_at_a_time=True, name=""):
    """The stored block: the document, plus how it currently reads.

    Both, deliberately. The Markdown is what the author edits and what
    another tool reads questions out of; the rendered form is what the
    page shows and what a search filters. Keeping only the first would
    mean re-parsing on every render and give search nothing to match
    against; keeping only the second would mean reading the document back
    out of its own presentation, which is what made editing forty
    questions painful in the first place.
    """
    view = view if view in dict(FAQ_VIEWS) else "document"
    parsed = parse_faq_document(md)
    group = (' name="%s"' % faq_group_name(name, [i["q"] for i in parsed["items"]])
             if one_at_a_time and view != "document" else "")

    rows = []
    for item in parsed["items"]:
        q = html_escape(item["q"])
        a = faq_markdown(item["a"])
        anchor = html_escape(item["id"], quote=True)
        if view == "document":
            rows.append(
                f'<section class="cms-faq-item" id="faq-{anchor}" data-faq-id="{anchor}">'
                f'<h3 class="cms-faq-q">{q}</h3>'
                f'<div class="cms-faq-a">{a}</div></section>'
            )
        else:
            rows.append(
                f'<details class="cms-faq-item" id="faq-{anchor}" data-faq-id="{anchor}"{group}>'
                f'<summary class="cms-faq-q">{q}</summary>'
                f'<div class="cms-faq-a">{a}</div></details>'
            )
    if not rows:
        rows.append('<p class="cms-faq-empty">Nothing here yet — write or paste '
                    'your questions into this tool. Start each one with #.</p>')

    intro = f'<div class="cms-faq-intro">{faq_markdown(parsed["intro"])}</div>' if parsed["intro"] else ""
    label = f' data-faq-name="{html_escape(name.strip(), quote=True)}"' if (name or "").strip() else ""
    return (f'<div class="cms-faq {FAQ_STYLE_PREFIX}{view}"{label} '
            f'data-faq-md="{html_escape(md or "", quote=True)}">'
            + intro + "".join(rows) + "</div>")


def faq_document_source(content):
    """The Markdown a block was written from.

    Blocks written before this existed have none, so their questions are
    turned back into a document — headings and answers, which is what they
    always were underneath.
    """
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-faq")
    if box is None:
        return ""
    if box.has_attr("data-faq-md"):
        return box["data-faq-md"]
    lines = []
    for det in box.find_all(class_="cms-faq-item"):
        q_el = det.find(class_="cms-faq-q")
        a_el = det.find(class_="cms-faq-a")
        if q_el is None:
            continue
        answer = (a_el.get("data-md") if a_el is not None and a_el.has_attr("data-md")
                  else (a_el.get_text() if a_el is not None else ""))
        lines.append(f"Q. {q_el.get_text().strip()}")
        lines.append("")
        lines.append((answer or "").strip())
        lines.append("")
    return "\n".join(lines).strip()


#  Checking an FAQ document before it is parsed.
#
#  The dialect is deliberately tiny, which is what makes pasting a real
#  FAQ into it plausible — and also what makes it easy to paste something
#  that does not fit. A document written with "Q:" prefixes, or with
#  underlined headings, or straight out of a word processor as HTML, is
#  not obviously wrong to look at; it simply produces no questions. Saving
#  that silently and showing an empty FAQ is the worst outcome, because
#  the page looks broken and the cause is invisible.
#
#  So it is checked first. Anything that would produce no usable FAQ is an
#  error and refuses the save, with the rule that would fix it. Anything
#  that will work but probably is not what was meant is a warning, and
#  saves.

#  Underlined (setext) headings — real Markdown, not read here.
FAQ_SETEXT_RE = re.compile(r"^\s{0,3}(=+|-{3,})\s*$")
#  "Q: something" or "1. something" — how an FAQ usually arrives when it
#  was not written as Markdown.
FAQ_PSEUDO_Q_RE = re.compile(r"^\s*(?:Q\s*[:.\)]|\d+\s*[\.\)])\s*\S", re.I)
FAQ_HTML_RE = re.compile(r"<\s*/?\s*(p|div|br|h[1-6]|ul|ol|li|span|strong|em|b|i|a)\b[^>]*>", re.I)
FAQ_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]*)\)")

#  Shown whenever something is wrong, so the fix is always to hand rather
#  than somewhere else in the documentation.
FAQ_RULES = [
    "Mark each question with the Q. Question button; everything under it is that answer.",
    "An answer can be several paragraphs or a list — it runs until the next question.",
    "Anything above the first question is an introduction.",
    "Pasting an FAQ in keeps its formatting; headings in it become questions.",
]


def check_faq_document(md):
    """Problems with an FAQ document, worst first.

    Each is {level, message}: "error" refuses the save, "warning" saves
    but says so. The message names the line where it can, because "a
    question has no answer" is not much help in a document of forty.
    """
    problems = []
    text = md or ""
    lines = text.splitlines()
    parsed = parse_faq_document(text)

    if not text.strip():
        problems.append({"level": "error", "message": "There is nothing here yet."})
        return problems

    if not parsed["items"]:
        if any(line.strip() in ("#", "##", "###") for line in lines):
            problems.append({"level": "error", "message":
                             "A # here has no question after it. Write the question "
                             "on the same line, or drop the # entirely — it is not "
                             "needed."})
        else:
            problems.append({"level": "error", "message":
                             "No questions found. Mark each question with the "
                             "Q. Question button, and write its answer underneath."})
        return problems

    #  A heading with nothing under it renders as a question that opens on
    #  nothing, which reads as a fault on the published page.
    for item in parsed["items"]:
        if not item["q"].strip():
            problems.append({"level": "error", "message":
                             "One question is empty — a # on a line by itself. "
                             "Write the question after the #, or delete the line."})
        elif not item["a"].strip():
            problems.append({"level": "error", "message":
                             f'"{item["q"][:60]}" has no answer. Write it on the '
                             "lines underneath the question."})

    #  Everything past here is survivable, and worth saying anyway.
    seen = {}
    for item in parsed["items"]:
        key = item["q"].strip().lower()
        if key and key in seen:
            problems.append({"level": "warning", "message":
                             f'"{item["q"][:60]}" is asked twice. Both will be shown.'})
        seen[key] = True

    for number, line in enumerate(lines[1:], start=2):
        if FAQ_SETEXT_RE.match(line):
            problems.append({"level": "warning", "message":
                             f"Line {number} underlines the line above it, which is "
                             "shown as typed rather than turned into a heading. "
                             "Underlining is not needed here."})
            break

    for number, line in enumerate(lines, start=1):
        if FAQ_HTML_RE.search(line):
            problems.append({"level": "warning", "message":
                             f"Line {number} contains HTML, which is shown as text "
                             "rather than applied. Use **bold**, *italic* or "
                             "[words](/a-page) instead."})
            break

    for number, line in enumerate(lines, start=1):
        if line.count("**") % 2:
            problems.append({"level": "warning", "message":
                             f"Line {number} opens **bold** without closing it, so "
                             "the stars will be shown as typed."})
            break

    for match in FAQ_LINK_RE.finditer(text):
        href = match.group(1).strip()
        if href and not href.startswith(BUTTON_SCHEMES):
            problems.append({"level": "warning", "message":
                             f'The link to "{href[:40]}" will be shown as plain text '
                             "— a link has to start with /, http:// or https://, "
                             "mailto: or tel:."})
            break

    return problems


def faq_document_errors(md):
    """Just the problems that refuse a save."""
    return [p for p in check_faq_document(md) if p["level"] == "error"]


def faq_editor_html(md):
    """The document as something to edit on a page rather than in a box.

    The inverse of the serialiser in faq-editor.js, and deliberately the
    same small vocabulary: a question is a heading, an answer is
    paragraphs and lists. Rendering it this way means the editor shows the
    FAQ roughly as it will read, and what comes back out is the same Q./A.
    document that was stored — the editor is a way of writing it, not a
    different thing to store.
    """
    def as_blocks(text):
        #  A single line comes back bare from faq_markdown; in an editor it
        #  still has to be a block of its own, or it merges into whatever
        #  is next to it the moment somebody puts the cursor in it.
        rendered = faq_markdown(text)
        if not rendered:
            return ""
        return rendered if rendered.startswith(("<p", "<ul")) else "<p>" + rendered + "</p>"

    parsed = parse_faq_document(md)
    out = []
    if parsed["intro"]:
        out.append(as_blocks(parsed["intro"]))
    for item in parsed["items"]:
        out.append("<h3>" + html_escape(item["q"]) + "</h3>")
        out.append(as_blocks(item["a"]) or "<p></p>")
    return "".join(out) or "<p></p>"

def build_faq_mirror(source_id, ids, style="list", one_at_a_time=True, show_contents=False):
    """A FAQ block that shows questions written somewhere else.

    Stores references, never words. The questions are resolved when the
    page is rendered, so editing one on the FAQ page updates every block
    repeating it, and there is no second copy to fall out of step.
    """
    style = style if style in dict(FAQ_STYLES) else "list"
    classes = f"cms-faq {FAQ_STYLE_PREFIX}{style} cms-faq-mirror"
    grouped = ' data-faq-grouped="1"' if one_at_a_time else ""
    #  A reader's display parts. Stored on the block, so two readers of the
    #  same questions can present them differently — which is the whole
    #  reason reading is a separate tool from writing.
    contents = ' data-faq-contents="1"' if show_contents else ""
    return (f'<div class="{classes}" data-faq-source="{int(source_id)}" '
            f'data-faq-ids="{",".join(html_escape(i) for i in ids)}"'
            f'{grouped}{contents}></div>')


def faq_sources(db, exclude_section_id=None):
    """Every FAQ on the site whose questions are its own, with its page.

    These are what a mirror can point at. A mirror is never itself a
    source — questions have one home, and a chain of mirrors would make
    "where is this actually written" unanswerable.
    """
    rows = db.execute(
        "SELECT s.id, s.content, p.title AS page_title, p.slug AS page_slug "
        "FROM sections s JOIN pages p ON p.id = s.page_id "
        "WHERE s.content LIKE '%cms-faq%' AND s.content NOT LIKE '%cms-faq-mirror%' "
        "ORDER BY p.nav_order, p.title"
    ).fetchall()
    sources = []
    for row in rows:
        if exclude_section_id and row["id"] == exclude_section_id:
            continue
        settings = faq_settings(row["content"])
        items = [i for i in settings["items"] if i.get("id")]
        if items:
            sources.append({
                "section_id": row["id"],
                "name": settings["name"] or row["page_title"],
                "page_title": row["page_title"],
                "page_slug": row["page_slug"],
                #  Named sets are told apart by their name; an unnamed one
                #  falls back to its page, which reads correctly for the
                #  common case of a single set on a page called FAQ.
                "label": (f'{settings["name"]} ({row["page_title"]})'
                          if settings["name"] else row["page_title"]),
                "items": items,
            })
    return sources


def faq_mirror_items(db, content):
    """The questions a mirror actually shows, in the order they are written.

    A block asked for a number of questions, so it keeps that number. When
    one is deleted on the FAQ page the slot is filled by the next question
    not already shown, rather than the block quietly shrinking — a row
    vanishing from a page nobody was editing is the kind of change that is
    noticed weeks later, if at all.

    Resolved on every render and never stored: storing it would be the
    second copy this whole thing exists to avoid. The substitution does
    reach the toolbar's tickboxes though, so what is ticked and what is on
    the page never disagree, and the next save writes the corrected list
    back on its own.
    """
    settings = faq_settings(content)
    if not settings["is_reader"]:
        return None
    if settings["mirror_source"] is None:
        return []  # a reader with nowhere to read from yet
    row = db.execute("SELECT content FROM sections WHERE id = ?",
                     (settings["mirror_source"],)).fetchone()
    available = [i for i in faq_settings(row["content"])["items"] if i.get("id")] if row else []
    order = {item["id"]: n for n, item in enumerate(available)}
    by_id = {item["id"]: item for item in available}

    kept = [by_id[i] for i in settings["mirror_ids"] if i in by_id]
    shown = {item["id"] for item in kept}
    for item in available:
        if len(kept) >= len(settings["mirror_ids"]):
            break
        if item["id"] not in shown:
            kept.append(item)
            shown.add(item["id"])
    #  Source order, so a substitute arrives where it is written rather
    #  than tacked on the end.
    return sorted(kept, key=lambda item: order.get(item["id"], 0))


def resolve_faq_mirror(db, content):
    """A mirror's markup for display, questions and all."""
    items = faq_mirror_items(db, content)
    if items is None:
        return content
    if not items:
        #  Same shape as the Contact tool's empty state: a tool with
        #  nothing in it says so, rather than rendering an empty band
        #  nobody can see the cause of.
        return ('<div class="cms-faq cms-faq-empty">None defined — '
                'choose questions in this tool, or write some on the page they come from.</div>')
    settings = faq_settings(content)
    #  Rebuilt as a small document of just the chosen questions, so a
    #  reader presents them exactly as a source does — same views, same
    #  markup, so search and contents links behave identically either side.
    gap = chr(10) + chr(10)
    doc = gap.join("# " + item["q"] + gap + item["a"] for item in items)
    body = build_faq_document(doc, settings["style"], settings["one_at_a_time"])
    if not settings.get("show_contents"):
        return body
    #  A contents list is a display choice, so it belongs to the reader
    #  rather than to the questions. Built from the same items that were
    #  just rendered, so it can never name one that is not below it.
    links = "".join(
        '<li><a href="#faq-' + item["id"] + '" data-faq-jump="' + item["id"] + '">'
        + html_escape(item["q"]) + "</a></li>"
        for item in items
    )
    return '<ol class="cms-faq-contents">' + links + "</ol>" + body


def apply_faq_form(content):
    """One submit carries every question and answer, the style, the
    one-at-a-time flag, and any add/remove that was pressed. Shared by the
    section and Columns-cell routes."""
    form = request.form
    #  "Where do these questions come from" is the first decision, because
    #  everything else on this bar depends on the answer.
    source = (form.get("faq_source") or "").strip()
    if source.isdigit():
        picked = [v for k, v in form.items(multi=True) if k == "faq_pick"]
        return build_faq_mirror(int(source), picked, form.get("faq_style"),
                                form.get("one_at_a_time") == "1",
                                form.get("show_contents") == "1")

    #  One document, one view, one name — the whole tool in one submit.
    return build_faq_document(form.get("faq_md", ""), form.get("faq_style"),
                              form.get("one_at_a_time") == "1", form.get("faq_name", ""))


#  ---------------------------------------------------------------------
#  Buy button
#  ---------------------------------------------------------------------
#  The button posts to this site, which creates a Stripe Checkout Session
#  server-side and redirects. The price id is the only thing the markup
#  carries — never an amount, because an amount in the page is a number a
#  visitor can edit before it is charged. Stripe is the only authority on
#  what anything costs.
BUY_STYLES = (
    ("button", "Button only"),
    ("card", "Card with name and price"),
)


def build_buy_button(price_id, label="Buy now", style="button", name="", price_text=""):
    style = style if style in dict(BUY_STYLES) else "button"
    label = html_escape((label or "Buy now").strip() or "Buy now")
    price_id = html_escape((price_id or "").strip(), quote=True)
    #  Two classes, two jobs: cms-buy-btn is this tool's identity, read
    #  back by buy_button_settings; cms-action-btn is the shared look that
    #  the Email sign-up also wears. Keeping them separate is what stops
    #  one tool's styling from being another tool's name.
    body = f'<button type="submit" class="cms-buy-btn cms-action-btn">{label}</button>'
    if style == "card":
        heading = html_escape((name or "").strip())
        price = html_escape((price_text or "").strip())
        body = (
            '<div class="cms-buy-card">'
            + (f'<h3 class="cms-buy-name">{heading}</h3>' if heading else "")
            + (f'<p class="cms-buy-price">{price}</p>' if price else "")
            + body
            + "</div>"
        )
    return (
        f'<form class="cms-buy cms-buy-style-{style}" method="post" action="/checkout" '
        f'data-price-id="{price_id}">'
        f'<input type="hidden" name="price_id" value="{price_id}">'
        f"{body}</form>"
    )


def buy_button_settings(content):
    soup = BeautifulSoup(content or "", "html.parser")
    form = soup.find(class_="cms-buy")
    if form is None:
        return {"price_id": "", "label": "Buy now", "style": "button", "name": "", "price_text": ""}
    classes = form.get("class") or []
    style = next((k for k, _ in BUY_STYLES if f"cms-buy-style-{k}" in classes), "button")
    btn = form.find(class_="cms-buy-btn")
    name_el = form.find(class_="cms-buy-name")
    price_el = form.find(class_="cms-buy-price")
    return {
        "price_id": form.get("data-price-id") or "",
        "label": btn.get_text() if btn else "Buy now",
        "style": style,
        "name": name_el.get_text() if name_el else "",
        "price_text": price_el.get_text() if price_el else "",
    }


def apply_buy_button_form(content):
    """One submit rebuilds the button.

    The product name and price on a card are looked up from Stripe HERE,
    server-side, rather than carried in hidden fields filled by the
    browser. The first attempt did the latter and lost them: the select
    carries an inline onchange that submits the form, inline handlers run
    before listeners attached afterwards, so the form was posted before
    the fields were filled — producing a card with an empty name and
    price, which renders as a bare button in a box.

    Reading them here removes the race, removes the JavaScript, and means
    a card always shows what Stripe currently charges rather than a copy
    that quietly went stale.
    """
    from . import integrations

    form = request.form
    price_id = (form.get("price_id") or "").strip()
    name = price_text = ""
    if price_id:
        catalogue, _ = integrations.stripe_catalogue_cached(get_db())
        match = next((i for i in catalogue if i["price_id"] == price_id), None)
        if match:
            name = match["name"]
            if match["amount"] is not None:
                price_text = f"{match['amount'] / 100:.2f} {match['currency']}"
    return build_buy_button(price_id, form.get("label"), form.get("buy_style"), name, price_text)


def table_settings(content):
    """Current shape of the (first) table in `content`, for the config
    form's own controls. Read-only: every table edit is applied to the
    live DOM by inline-editor.js and saved as the section's HTML."""
    soup = BeautifulSoup(content or "", "html.parser")
    table = soup.find("table")
    if table is None:
        return {"style": "cms-table", "rows": 0, "cols": 0, "has_header": False}
    classes = table.get("class") or []
    style = next((c for c in TABLE_STYLES if c in classes), "cms-table")
    head_row = table.find("thead")
    body_rows = table.find("tbody").find_all("tr") if table.find("tbody") else [
        tr for tr in table.find_all("tr") if not tr.find_parent("thead")
    ]
    cols = max(
        [len(tr.find_all(["td", "th"])) for tr in table.find_all("tr")] or [0]
    )
    return {
        "style": style,
        "rows": len(body_rows),
        "cols": cols,
        "has_header": head_row is not None,
    }


VIDEO_GALLERY_LAYOUTS = (
    ("auto", "Fit automatically"),
    ("2", "2 across"),
    ("3", "3 across"),
    ("4", "4 across"),
)
MAX_VIDEO_GALLERY_CLIPS = 12

#  Kept here rather than in routes/public.py (which had its own copy for
#  the Media Player tool) so the gallery builder — a service — doesn't
#  have to import from a route module, which the layering rule forbids.
YOUTUBE_URL_RE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})"
)


def youtube_id(url):
    """The 11-character video id out of any normal YouTube URL shape, or
    a bare id pasted on its own. None if it's neither."""
    url = (url or "").strip()
    if not url:
        return None
    m = YOUTUBE_URL_RE.search(url)
    if m:
        return m.group(1)
    return url if re.fullmatch(r"[\w-]{11}", url) else None


#  A YouTube thumbnail is the one part of a gallery that would otherwise be
#  fetched from a third party on every page load, by every visitor, before
#  anyone has clicked anything — the same exposure self-hosting the fonts
#  removed (see CLAUDE.md), and the reason the player itself already uses
#  youtube-nocookie. So the thumbnail is pulled once, at save time, into
#  the site's own uploads, and the markup points at that copy: a visitor
#  who never presses play never talks to Google at all.
YOUTUBE_THUMB_MAX_BYTES = 2 * 1024 * 1024
YOUTUBE_THUMB_TIMEOUT_S = 6
#  Real Chrome UA: img.youtube.com serves a tiny "video unavailable" grey
#  image to some non-browser clients.
YOUTUBE_THUMB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _local_youtube_thumbnail(video_id):
    """Local URL of `video_id`'s thumbnail, downloading it first if this
    site hasn't already got it. None if it can't be fetched — the caller
    falls back to the placeholder rather than emitting a remote URL,
    since a missing picture is a much smaller problem than quietly
    reinstating the third-party request this exists to remove.

    The filename is derived from the video id rather than randomised (the
    usual rule for uploads) precisely so the same video is only ever
    fetched and stored once, however many galleries use it. That's safe
    here for the same reason the id is safe to put in a URL: it is
    matched against a strict 11-character pattern first, and is not a
    client-supplied filename."""
    if not video_id or not re.fullmatch(r"[\w-]{11}", video_id):
        return None
    folder = current_app.config["UPLOAD_FOLDER"]
    name = f"yt-{video_id}.jpg"
    local_url = f"/static/uploads/{name}"
    path = os.path.join(folder, name)
    if os.path.exists(path):
        return local_url
    request_ = urllib.request.Request(
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        headers={"User-Agent": YOUTUBE_THUMB_UA},
    )
    try:
        with urllib.request.urlopen(request_, timeout=YOUTUBE_THUMB_TIMEOUT_S) as resp:
            if not (resp.headers.get_content_type() or "").startswith("image/"):
                return None
            data = resp.read(YOUTUBE_THUMB_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if not data or len(data) > YOUTUBE_THUMB_MAX_BYTES:
        return None
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return local_url


def build_video_gallery(clips, layout="auto"):
    """Rebuilds a gallery's whole markup from the submitted clip list —
    one thumbnail per clip, in order. A clip with no usable YouTube link
    is still kept as an empty slot (so an admin can add three and fill
    them in one at a time) and hidden from real visitors by CSS, the same
    way the editor's own chrome is."""
    layout = layout if layout in dict(VIDEO_GALLERY_LAYOUTS) else "auto"
    layout_class = "" if layout == "auto" else f" cms-video-gallery-{layout}"
    parts = []
    for clip in clips[:MAX_VIDEO_GALLERY_CLIPS]:
        vid = youtube_id(clip.get("url"))
        src = (clip.get("src") or "").strip()
        caption = html_escape(clip.get("caption", "").strip())
        caption_html = (
            f'<span class="cms-video-caption">{caption}</span>' if caption else ""
        )
        if src:
            #  An uploaded clip is its own thumbnail — no separate poster
            #  image to generate, store or keep in sync. The "#t=0.1" is
            #  load-bearing, not decoration: preload="metadata" alone gives
            #  the browser the dimensions but leaves the tile painted black,
            #  because nothing has told it to decode a frame. A media
            #  fragment makes it seek to 0.1s and paint THAT, which is the
            #  poster. data-video-src (what the popup player reads) stays
            #  clean, so playback still starts at zero.
            esc = html_escape(src, quote=True)
            parts.append(
                f'<div class="cms-video-thumb" data-video-src="{esc}">'
                f'<video src="{esc}#t=0.1" preload="metadata" muted playsinline></video>'
                f'<span class="cms-play-icon">&#9658;</span>{caption_html}</div>'
            )
        elif vid:
            thumb = _local_youtube_thumbnail(vid) or "/static/img/placeholder.svg"
            parts.append(
                f'<div class="cms-video-thumb" data-youtube-id="{vid}">'
                f'<img src="{thumb}" alt="Video thumbnail">'
                f'<span class="cms-play-icon">&#9658;</span>{caption_html}</div>'
            )
        else:
            parts.append(
                '<div class="cms-video-thumb cms-video-thumb-empty">'
                f'<span class="cms-play-icon">&#9658;</span>{caption_html}</div>'
            )
    if not parts:
        parts.append(
            '<div class="cms-video-thumb cms-video-thumb-empty">'
            '<span class="cms-play-icon">&#9658;</span></div>'
        )
    return (
        f'<div class="cms-video-gallery{layout_class}">\n'
        + "\n".join(parts)
        + "\n</div>"
    )


def video_gallery_settings(content):
    """The gallery's current clips/layout, for the config form. A clip's
    stored id is turned back into a full watch URL so the admin sees (and
    edits) the same kind of link they pasted in."""
    soup = BeautifulSoup(content or "", "html.parser")
    gallery = soup.find(class_="cms-video-gallery")
    if gallery is None:
        return {"layout": "auto", "clips": []}
    classes = gallery.get("class") or []
    layout = next(
        (key for key, _ in VIDEO_GALLERY_LAYOUTS
         if key != "auto" and f"cms-video-gallery-{key}" in classes),
        "auto",
    )
    clips = []
    for thumb in gallery.find_all(class_="cms-video-thumb"):
        vid = thumb.get("data-youtube-id") or ""
        caption_el = thumb.find(class_="cms-video-caption")
        clips.append({
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
            "src": thumb.get("data-video-src") or "",
            "caption": caption_el.get_text() if caption_el else "",
        })
    return {"layout": layout, "clips": clips}


def set_video_gallery_clip_src(content, index, src):
    """Points one clip at an uploaded video file, replacing whatever it
    held (a YouTube id or another upload). Rebuilds through the same
    builder as every other edit rather than patching the markup, so an
    uploaded clip is structurally identical to one built from scratch."""
    state = video_gallery_settings(content)
    clips = state["clips"]
    if index < 0 or index >= len(clips):
        return content
    clips[index] = {"url": "", "src": src, "caption": clips[index].get("caption", "")}
    return build_video_gallery(clips, state["layout"])


def video_gallery_form_clips(form, count_key="clip_count"):
    """Reads the config form's per-clip fields back into the list
    build_video_gallery expects, applying whichever add/remove button was
    pressed (`op`) — one submit, one rebuild, so the clip list can never
    drift out of sync with the markup."""
    count = form.get(count_key, type=int) or 0
    count = max(0, min(MAX_VIDEO_GALLERY_CLIPS, count))
    clips = [
        {
            "url": form.get(f"clip_url_{i}", ""),
            #  Hidden field, not typed: an uploaded clip's path is set by
            #  the upload route, and has to survive every later rebuild of
            #  the gallery (a caption edit, a layout change, an add/remove)
            #  or the upload would silently vanish on the next submit.
            "src": form.get(f"clip_src_{i}", ""),
            "caption": form.get(f"clip_caption_{i}", ""),
        }
        for i in range(count)
    ]
    op = (form.get("op") or "").strip()
    if op == "add" and len(clips) < MAX_VIDEO_GALLERY_CLIPS:
        clips.append({"url": "", "src": "", "caption": ""})
    elif op.startswith("remove_"):
        try:
            index = int(op.split("_", 1)[1])
        except ValueError:
            index = -1
        if 0 <= index < len(clips):
            clips.pop(index)
    return clips


#  The Video Gallery starter is built by the same function that rebuilds it
#  on every edit, so a brand-new gallery and an edited one can never drift
#  into two different markup shapes. Three empty slots rather than sample
#  videos: a novice shouldn't have to work out why someone else's video is
#  in their gallery before they can replace it.
BLOCK_LIBRARY["video-gallery"] = ("html", build_video_gallery([{}, {}, {}]))

#  Same reasoning as the gallery starter: produced by the very function
#  every later edit goes through, so a new FAQ and an edited one can
#  never be two different shapes. Three real questions rather than empty
#  rows — an admin should see what the tool does before typing.
BLOCK_LIBRARY["buy-button"] = ("html", build_buy_button("", "Buy now", "button"))
BLOCK_LIBRARY["shop"] = ("html", '<div class="cms-shop" data-columns="3" data-description="1"></div>')

#  Every declared block gets its starter content from its own defaults,
#  so the tool menu and the block registry cannot drift apart.
from . import blocks as _blocks  # noqa: E402  (circular-safe: blocks imports nothing from here)

for _key in _blocks.BLOCKS:
    BLOCK_LIBRARY[f"block:{_key}"] = ("html", _blocks.starter(_key))

#  ---------------------------------------------------------------------
#  Search tool
#
#  A search box you drop on a page, rather than a behaviour welded to one
#  kind of page. It filters whatever on that page has said it is
#  searchable — today the FAQ tools, which mark each question — so the
#  same tool works on a page holding one FAQ or three, and a page holding
#  none simply has nothing to filter (which the tool says, while editing,
#  instead of sitting there looking broken).

SEARCH_STYLES = (
    ("bar", "Box with a border"),
    ("pill", "Rounded pill"),
    ("plain", "Underline only"),
)
SEARCH_STYLE_PREFIX = "cms-search-style-"
SEARCH_DEFAULT_PLACEHOLDER = "Search the questions"


def build_search(style="bar", placeholder="", show_count="1"):
    """The tool's markup is the control itself.

    Stored complete rather than as a marker, for the same reason the FAQ
    tools store their questions: what is on the page is what is in the
    database, so nothing has to be reconstructed to be shown, and the
    settings are read back off the markup that carries them.
    """
    style = style if style in dict(SEARCH_STYLES) else "bar"
    placeholder = (placeholder or "").strip() or SEARCH_DEFAULT_PLACEHOLDER
    count = "1" if str(show_count) == "1" else "0"
    return (
        '<div class="cms-search-tool ' + SEARCH_STYLE_PREFIX + style + '"'
        ' data-search-tool data-show-count="' + count + '">'
        '<label class="cms-search-box">'
        '<span class="cms-search-icon" aria-hidden="true">&#128269;</span>'
        '<input type="search" placeholder="' + html_escape(placeholder, quote=True) + '"'
        ' aria-label="' + html_escape(placeholder, quote=True) + '">'
        "</label>"
        '<p class="cms-search-count" hidden></p>'
        "</div>"
    )


def search_settings(content):
    """Style, wording and count flag, read back off the markup."""
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-search-tool")
    if box is None:
        return {"style": "bar", "placeholder": SEARCH_DEFAULT_PLACEHOLDER, "show_count": True}
    classes = box.get("class") or []
    style = next(
        (key for key, _ in SEARCH_STYLES if SEARCH_STYLE_PREFIX + key in classes), "bar"
    )
    field = box.find("input")
    return {
        "style": style,
        "placeholder": (field.get("placeholder") if field else "") or SEARCH_DEFAULT_PLACEHOLDER,
        "show_count": box.get("data-show-count", "1") == "1",
    }


def apply_search_form(form):
    """One submit rebuilds the control, like every other derived tool."""
    return build_search(
        form.get("search_style"),
        form.get("search_placeholder", ""),
        "1" if form.get("show_count") else "0",
    )


#  A reader arrives pointing nowhere: which questions it shows is the
#  first thing to choose, and choosing it is what its toolbar is for.
BLOCK_LIBRARY["faq-reader"] = (
    "html",
    '<div class="cms-faq ' + FAQ_STYLE_PREFIX + 'list cms-faq-mirror" '
    'data-faq-source="" data-faq-ids=""></div>',
)
BLOCK_LIBRARY["search"] = ("html", build_search())
#  A blog tool arrives pointing nowhere, like a reader: which blog it
#  shows is the first thing to choose, and its toolbar is where that
#  happens (including starting one, since a site's first blog has to be
#  creatable from the place it is first wanted).
from .blog import build_blog as _build_blog  # noqa: E402
BLOCK_LIBRARY["blog"] = ("html", _build_blog(None))
#  The contact form is a marker, not markup: what it draws depends on a
#  captcha question generated per page load, so a stored copy would be a
#  stale challenge nobody could answer.
BLOCK_LIBRARY["contact-form"] = ("html", '<div class="cms-contact-form-tool"></div>')
#  A marker, never a number — see build_basket.
from .cart import build_basket as _build_basket  # noqa: E402
BLOCK_LIBRARY["basket"] = ("html", _build_basket())
#  A marker, never a number — see build_basket.
from .cart import build_basket as _build_basket  # noqa: E402
BLOCK_LIBRARY["basket"] = ("html", _build_basket())

BLOCK_LIBRARY["faq"] = ("html", build_faq([
    {"q": "How long does it take?", "a": "Most projects are finished within two weeks of the first call."},
    {"q": "What does it cost?", "a": "Every quote is fixed up front — you will never see a surprise line on an invoice."},
    {"q": "Do you offer a guarantee?", "a": "Yes. If you are not happy with the result, we will put it right at no charge."},
]))



#  Page types are deliberately few, and none of them is a feature.
#
#  An FAQ page was briefly one of these, and it was the wrong shape. It
#  made "can this page do X" a property of the page rather than of what
#  was put on it: the questions could not live anywhere else, a site could
#  not have two sets of them, and every later feature would have had to
#  ask which kind of page it was standing on. What an FAQ page actually is
#  is an ordinary page with an FAQ Content tool on it -- and once that is
#  true, none of those limits exist.
#
#  Blog went the same way afterwards and for the same reasons, which is
#  why the list below is shorter than it was: a site can now have several
#  blogs, shown on whichever pages it likes, rather than one blog that IS
#  a page. When tempted to add a type here for a feature, add a tool.
PAGE_TYPES = (
    ("standard", "Standard page"),
    #  Newsletter is a marker now, not a kind of page, and the difference
    #  is worth stating because it used to be the latter and the comment
    #  here defended it as such.
    #
    #  It once meant three things the page could not choose: kept out of
    #  the navigation, listed in the public archive, sendable to a list.
    #  Two of those turned out not to be about newsletters at all. A page
    #  is in a menu because somebody ticked it -- a Menu is a list you
    #  build -- so nothing had to be excluded by kind. And whether people
    #  can read a page is now `pages.is_public`, a question every page
    #  has: an issue can go only to the list, or be readable and linkable
    #  like anything else.
    #
    #  What is left is the third: this page shows its own Subject,
    #  Preview and Send while being edited, and is listed on the
    #  Newsletters screen. That is a marker about what the OWNER sees,
    #  it can be switched on or off on any page from the page's own
    #  settings, and nothing about the site branches on it.
    ("newsletter", "Newsletter — a page you can also send to your email list"),
)


#  What "create a Blog page" means now that a blog is not a kind of page:
#  an ordinary page with the tools already on it, arranged the way that
#  kind of page usually starts. The choice is a starting layout, not a
#  behaviour — so the page can be changed into anything afterwards, and
#  nothing later has to ask what it was created as.
#  THE SAME LIST THE GENERATOR PICKS FROM.
#
#  The AI Theme Generator had its own private set of page arrangements
#  -- landing, about, simple -- which meant it could make a shape by
#  hand that an owner could not choose when creating a page. That is the
#  rule this app has about tools, applied to arrangements: if the
#  machine can make it, a person can pick it.
#
#  So the arrangements live here, with the ones that were already here,
#  and `theme_generator.LAYOUTS` reads this list rather than keeping a
#  second copy that can disagree.
PAGE_LAYOUTS = (
    ("standard", "Standard page", "An empty page to build up yourself."),
    ("landing", "Front page",
     "A banner, a short introduction, some numbers, three cards, a quote and "
     "a closing call to action."),
    ("story", "Story",
     "A banner, a longer piece of writing, and a closing call to action."),
    ("poster", "Poster",
     "A tall picture with a few words on it, one block of writing, and nothing "
     "else. For a place with one thing to say."),
    ("showcase", "Showcase",
     "A banner, a short introduction, and a row of pictures to look through."),
    #  Three more ways a front page can be arranged. Offered here, not
    #  only inside the generator, because an arrangement the AI can
    #  choose has to be one an owner can choose too -- otherwise the
    #  tool makes pages nobody can make.
    ("editorial", "Editorial",
     "A title page with no photograph, a story in two parts, a picture "
     "band between them, and a quiet close. For writing, coaching or a "
     "studio, where the voice is the product."),
    ("catalogue", "Catalogue",
     "A banner, a short introduction, your prices in three options, what "
     "is included, and a closing call to action. For a venue, a shop or "
     "a practice with packages."),
    ("process", "Process",
     "A banner, a short introduction, the steps of working together in "
     "order, some numbers, a quote and a closing call to action. For "
     "trades, clinics or anything booked in advance."),
    ("newsletter", "Newsletter",
     "A page to write an issue on, then send to your email list."),
    ("blog", "Blog", "A page showing your posts. Starts a blog if you have none."),
    ("faq", "FAQ", "Questions and answers, plus a search box to find one."),
    ("contact", "Contact", "A form people can write to you with."),
)


def build_block(key):
    """One declared block's markup, from its own defaults.

    The generator and the new-page screen both need this, and building
    it twice is how the two come to disagree about what a Numbers block
    starts as.
    """
    from . import blocks
    return blocks.build(key, dict(blocks.BLOCKS[key].get("defaults") or {}))


def starter_page_sections(db, layout, page_title="Page"):
    """The tools a new page starts with, for the layout that was chosen.

    This is what replaced the page types. Choosing "Blog" no longer marks
    the page as a blog forever; it drops a Blog tool on an ordinary page,
    already pointed at a blog. Everything after that is ordinary editing —
    the tools can be removed, added to, or moved to another page, and
    nothing anywhere has to remember what the page was created as.

    Returns (type, title, content) triples in page order.
    """
    if layout == "blog":
        from .blog import build_blog, create_blog, get_blog_by_slug, slugify
        #  A blog page needs a blog. Reuse one already named after this
        #  page if it exists (creating the same page twice should not
        #  quietly make a second blog with a suffixed address).
        existing = get_blog_by_slug(db, slugify(page_title))
        blog_id = existing["id"] if existing else create_blog(db, page_title)
        return [("html", "", build_blog(blog_id))]

    if layout == "faq":
        return [
            ("text", "", "<p>The questions we are asked most often. If yours is not "
                         "here, get in touch and we will answer it.</p>"),
            ("html", "", build_search()),
            (BLOCK_LIBRARY["faq"][0], "", BLOCK_LIBRARY["faq"][1]),
        ]

    if layout == "newsletter":
        #  Something to type over, rather than an empty page and a blank
        #  stare. A newsletter is mostly one piece of writing, so it
        #  starts as one Text tool with the shape of an issue already in
        #  it -- and every other tool can be added around it afterwards,
        #  the same as any page.
        return [
            ("text", "", "<h2>Hello</h2>"
                         "<p>Write your issue here. Everything on this page can be sent "
                         "to your list, or you can send one section of it &mdash; add a "
                         "second one below and pick which goes out.</p>"
                         "<p>Anything you can put on a page you can put in here: a "
                         "picture, a link, a list. What arrives in an inbox is a plainer "
                         "version of it, because email cannot do everything a browser "
                         "can &mdash; the Preview shows exactly what lands.</p>"),
        ]

    #  The arrangements the generator also uses. A page created by hand
    #  gets the same shape, with the words left to be written -- which is
    #  what a starting arrangement is.
    if layout in ("landing", "story", "poster", "showcase",
                  "editorial", "catalogue", "process"):
        #  The same starter the Banner tool itself uses, so a shape
        #  picked by hand opens with the same banner a generated one
        #  does -- one definition, in db.py, read by both.
        from ..db import BANNER_TOOL_STARTER
        out = [("banner", "", BANNER_TOOL_STARTER)]
        out.append(("text", "", "<h2>A heading</h2><p>Write your introduction here.</p>"))
        if layout == "landing":
            out += [
                ("html", "", build_block("stats")),
                ("columns", "", json.dumps({"columns": ["", "", ""]})),
                ("html", "", build_block("testimonial")),
                ("html", "", build_block("cta")),
            ]
        elif layout == "editorial":
            out += [
                ("text", "", "<h2>And then</h2><p>Carry the story on here.</p>"),
                ("html", "", build_block("testimonial")),
                ("html", "", build_block("cta")),
            ]
        elif layout == "catalogue":
            out += [
                ("html", "", build_block("pricing")),
                ("columns", "", json.dumps({"columns": ["", "", ""]})),
                ("html", "", build_block("cta")),
            ]
        elif layout == "process":
            out += [
                ("html", "", build_block("timeline")),
                ("html", "", build_block("stats")),
                ("html", "", build_block("testimonial")),
                ("html", "", build_block("cta")),
            ]
        elif layout == "story":
            out.append(("html", "", build_block("cta")))
        elif layout == "showcase":
            out.append((BLOCK_LIBRARY["image-accordion"][0], "",
                        BLOCK_LIBRARY["image-accordion"][1]))
        return out

    if layout == "contact":
        return [
            ("text", "", "<p>Send us a message and we will get back to you.</p>"),
            ("html", "", BLOCK_LIBRARY["contact-form"][1]),
        ]

    return []


#  How many across. Anything more than four makes a phone-sized card
#  unreadable, and the grid already reflows below that on narrow screens.
SHOP_COLUMNS = (("2", "Two across"), ("3", "Three across"), ("4", "Four across"))


def build_shop(columns="3", show_description="1"):
    """A marker, not the storefront itself.

    A shop cannot be saved as HTML the way a Card can: what it shows is
    whatever is for sale right now, and a copy frozen into a section would
    still be advertising last month's prices. So the section stores only
    the settings, and the products are read live at render time — the same
    approach the Menu tool takes for pages.
    """
    columns = columns if columns in dict(SHOP_COLUMNS) else "3"
    described = "1" if show_description in ("1", 1, True, "on") else "0"
    return (f'<div class="cms-shop" data-columns="{columns}" '
            f'data-description="{described}"></div>')


def shop_settings(content):
    soup = BeautifulSoup(content or "", "html.parser")
    block = soup.find(class_="cms-shop")
    if block is None:
        return {"columns": "3", "show_description": True}
    return {
        "columns": block.get("data-columns") or "3",
        "show_description": (block.get("data-description") or "1") != "0",
    }


def apply_shop_form():
    form = request.form
    return build_shop(form.get("columns"), form.get("show_description") or "0")
