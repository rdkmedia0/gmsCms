"""The Palette Library: a colour palette saved on its own, reusable on any
template, exportable and importable.

A palette here is just its three role colours -- primary, secondary,
accent -- the same three every template and every built-in COLOR_PRESET
is keyed on (see palette.color_scheme_choices, which lists these alongside
the built-ins and the templates' own). It carries no template, no fonts,
no shape: colours only, which is exactly the thing you want to try on more
than one look without dragging a whole template behind it.

Stored in its own `palettes` table -- deliberately NOT on a template,
because it belongs to no single one. Applying a library palette is the
same act as applying any other colour scheme (palette-preset), so there
is no separate "apply" here; this module only saves, lists, removes, and
moves palettes in and out as small JSON files.
"""
import io
import re
import json

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ROLES = ("primary", "secondary", "accent")


def _clean_hex(value):
    value = (value or "").strip()
    #  A 3-digit hex is expanded, so what is stored is always a full 6.
    if re.match(r"^#[0-9a-fA-F]{3}$", value):
        value = "#" + "".join(c * 2 for c in value[1:])
    return value if _HEX.match(value) else None


def _clean_name(name):
    return (name or "").strip()[:60]


def list_palettes(db):
    """Every saved palette, newest first, as dicts with the three roles."""
    rows = db.execute(
        "SELECT id, name, primary_color, secondary_color, accent_color "
        "FROM palettes ORDER BY id DESC").fetchall()
    return [{"id": r["id"], "name": r["name"], "primary": r["primary_color"],
             "secondary": r["secondary_color"], "accent": r["accent_color"]}
            for r in rows]


def save_palette(db, name, primary, secondary, accent):
    """Save (or, when the name already exists, replace) a palette. Raises
    ValueError, in the owner's words, when a colour is not a hex value --
    a palette that cannot be applied should never be stored."""
    name = _clean_name(name)
    if not name:
        raise ValueError("Give the palette a name so you can find it later.")
    cols = {}
    for role, value in (("primary", primary), ("secondary", secondary), ("accent", accent)):
        clean = _clean_hex(value)
        if not clean:
            raise ValueError("Each colour needs to be a hex value like #2563eb.")
        cols[role] = clean
    existing = db.execute("SELECT id FROM palettes WHERE name = ?", (name,)).fetchone()
    if existing:
        db.execute("UPDATE palettes SET primary_color = ?, secondary_color = ?, "
                   "accent_color = ? WHERE id = ?",
                   (cols["primary"], cols["secondary"], cols["accent"], existing["id"]))
        pid = existing["id"]
    else:
        cur = db.execute("INSERT INTO palettes (name, primary_color, secondary_color, "
                         "accent_color) VALUES (?, ?, ?, ?)",
                         (name, cols["primary"], cols["secondary"], cols["accent"]))
        pid = cur.lastrowid
    db.commit()
    return pid


def delete_palette(db, palette_id):
    db.execute("DELETE FROM palettes WHERE id = ?", (palette_id,))
    db.commit()


def export_palette(db, palette_id):
    """One palette as the small JSON object a file carries, or None."""
    r = db.execute("SELECT name, primary_color, secondary_color, accent_color "
                   "FROM palettes WHERE id = ?", (palette_id,)).fetchone()
    if not r:
        return None
    return {"gmscms_palette": 1, "name": r["name"], "primary": r["primary_color"],
            "secondary": r["secondary_color"], "accent": r["accent_color"]}


def import_palette(db, raw):
    """Read a palette out of the JSON text of an uploaded/pasted file and
    save it. Tolerant of shape -- any object with three hex roles will do,
    whether it came from export_palette or was written by hand -- but a
    colour that is not a hex value is refused rather than stored."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        raise ValueError("That file isn't a palette gmsCms can read.")
    if not isinstance(data, dict):
        raise ValueError("That file isn't a palette gmsCms can read.")
    name = _clean_name(data.get("name")) or "Imported palette"
    return save_palette(db, name, data.get("primary"),
                        data.get("secondary"), data.get("accent"))


def effective_roles(template):
    """The three role colours a template is ACTUALLY showing -- its palette
    base colours with any admin overrides applied on top -- as {primary,
    secondary, accent}. This is what "save the current colours" captures,
    so a palette tweaked by hand can be kept and reused. Missing/odd
    palettes return {} rather than a half answer."""
    from .palette import _match_palette_roles
    if not template or not template["palette_json"]:
        return {}
    try:
        palette = json.loads(template["palette_json"])
        overrides = json.loads(template["color_overrides"] or "{}")
    except (ValueError, TypeError):
        return {}
    base = {c.get("slug"): c.get("color") for c in palette if c.get("slug")}
    roles = _match_palette_roles(palette)
    out = {}
    for role in _ROLES:
        slug = roles.get(role)
        if not slug:
            continue
        colour = _clean_hex(overrides.get(slug) or base.get(slug))
        if colour:
            out[role] = colour
    return out if len(out) == 3 else {}
