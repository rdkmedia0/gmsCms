"""What sits behind a page: a colour, a picture, or both.

Two levels. The site's own choice covers every page; a page may answer
differently for itself. The colour is stored the way other palette-linked
colours are -- "role:primary" follows the palette, "#rrggbb" stays put --
and the text, bands and cards are worked out from whichever it is, so any
choice stays readable (see palette.page_colours).
"""
import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ROLES = ("primary", "secondary", "accent", "light", "dark")
ROLE_PREFIX = "role:"

#  What a picture brings with it. The first of each is the default: a soft
#  pale wash keeps ordinary dark text readable over most photographs.
OVERLAYS = (("light", "Pale wash"), ("none", "None"), ("medium", "Dim"),
            ("dark", "Dim strongly"), ("tint", "Brand colour"))
SURFACES = (("plain", "Straight on it"), ("panels", "On panels"),
            ("veil", "On one soft column"))
ATTACHMENTS = (("fixed", "Stays still"), ("scroll", "Scrolls with the page"))

#  A page that wants no picture while the rest of the site has one.
NO_PICTURE = "none"

SITE_KEYS = {"bg_image": "site_bg_image", "bg_overlay": "site_bg_overlay",
             "bg_surface": "site_bg_surface", "bg_attach": "site_bg_attach"}


def stored_colour(choice, custom=""):
    """What to store for a swatch choice; None for automatic."""
    if choice in ROLES:
        return ROLE_PREFIX + choice
    custom = (custom or "").strip()
    if choice == "custom" and HEX_RE.match(custom):
        return custom.lower()
    return None


def colour_choice(value):
    """(choice, hex) for the swatches, read back from a stored value."""
    value = value or ""
    if value.startswith(ROLE_PREFIX) and value[len(ROLE_PREFIX):] in ROLES:
        return value[len(ROLE_PREFIX):], ""
    if HEX_RE.match(value):
        return "custom", value.lower()
    return "", ""


def picked(value, options):
    return value if value in dict(options) else options[0][0]


def site_picture(db):
    """The site-wide picture and how it is shown."""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?, ?, ?)",
        tuple(SITE_KEYS.values())).fetchall()
    stored = {r["key"]: r["value"] for r in rows}
    return {field: stored.get(key) or "" for field, key in SITE_KEYS.items()}


def for_page(db, page):
    """`page` as a dict with the picture it should actually be drawn with."""
    shown = dict(page)
    own = shown.get("bg_image")
    if own == NO_PICTURE:
        shown["bg_image"] = None
    elif not own:
        site = site_picture(db)
        if site["bg_image"]:
            shown.update(site)
    return shown
