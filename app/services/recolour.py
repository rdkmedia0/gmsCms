"""Make hand-coloured items follow the palette, and undo it.

Applying a palette changes the site's colour variables, but anything saved
with a fixed colour of its own -- a banner's background, a heading coloured
from the text ribbon, a section's background -- never reads them, so the
old colours stayed put. Applying a palette now moves those onto the
variables too. What was there is saved first, and one Undo restores it.
"""
import json
import re

from bs4 import BeautifulSoup

from . import colour_choice
from .sections import _parse_style, _style_str

SNAPSHOT_KEY = "recolour_undo"

#  A colour written out, as against one that reads a variable.
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(")
#  A darkening or lightening wash. It belongs to no palette, so it stays.
NEUTRAL = re.compile(r"^rgba?\(\s*(?:0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\b")


def _fixed(value):
    return bool(value) and "var(" not in value and bool(LITERAL.search(value))


def _write_style(el, props):
    style = _style_str(props)
    if style:
        el["style"] = style
    elif el.has_attr("style"):
        del el["style"]


def recolour_html(html):
    """The same markup with its fixed colours handed to the palette; the
    original string when there was nothing to change."""
    if not html or not LITERAL.search(html):
        return html
    soup = BeautifulSoup(html, "html.parser")
    changed = False
    for el in soup.find_all(True):
        if el.has_attr("color") and el.name == "font":
            del el["color"]
            changed = True
        if not el.has_attr("style"):
            continue
        classes = el.get("class") or []
        props = _parse_style(el["style"])
        before = dict(props)
        if _fixed(props.get("color")):
            del props["color"]
        if "cms-banner" in classes:
            if _fixed(props.get("background-color")):
                props["background-color"] = colour_choice.ROLES["primary"][0]
                props["--cms-banner-ink"] = colour_choice.ROLES["primary"][1]
        elif "cms-card-shape" in classes:
            if _fixed(props.get("background-color")):
                props["background-color"], props["color"] = colour_choice.ROLES["light"]
        elif "cms-banner-overlay" in classes:
            box = props.get("background", "")
            if _fixed(box) and not NEUTRAL.match(box):
                props["background"] = colour_choice.with_opacity(
                    colour_choice.ROLES["dark"][0], colour_choice.read(box)[2])
        if props != before:
            changed = True
            _write_style(el, props)
    return str(soup) if changed else html


def _recolour_json(node):
    if isinstance(node, list):
        return [_recolour_json(item) for item in node]
    if isinstance(node, dict):
        out = {key: _recolour_json(value) for key, value in node.items()}
        if isinstance(out.get("content"), str):
            out["content"] = recolour_html(out["content"])
        for key in ("menu_bg_color", "menu_text_color"):
            if _fixed(out.get(key)):
                out[key] = ""
        return out
    return node


def recolour_content(content):
    """Section content: markup, or the JSON a Columns section keeps."""
    if content and content.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(content)
        except ValueError:
            return recolour_html(content)
        new = _recolour_json(data)
        return content if new == data else json.dumps(new)
    return recolour_html(content)


def follow_palette(db, template, before):
    """Hand every fixed colour on this template's site to the palette.

    `before` is the template row as it stood before the palette was
    applied; it and every row changed here go into the undo snapshot.
    Returns how many sections changed. The caller commits.
    """
    changed = []
    rows = db.execute(
        "SELECT id, content, bg_color, border_color FROM sections "
        "WHERE page_id IS NOT NULL OR template_id = ?", (template["id"],)).fetchall()
    for row in rows:
        content = recolour_content(row["content"])
        bg = colour_choice.ROLES["light"][0] if _fixed(row["bg_color"]) else row["bg_color"]
        border = "var(--site-line)" if _fixed(row["border_color"]) else row["border_color"]
        if (content, bg, border) == (row["content"], row["bg_color"], row["border_color"]):
            continue
        changed.append(dict(row))
        db.execute("UPDATE sections SET content = ?, bg_color = ?, border_color = ? WHERE id = ?",
                   (content, bg, border, row["id"]))
    #  Background choices that already follow the palette ("role:...") stay.
    pages = [dict(r) for r in db.execute(
        "SELECT id, bg_color FROM pages WHERE bg_color LIKE '#%'").fetchall()]
    db.execute("UPDATE pages SET bg_color = NULL WHERE bg_color LIKE '#%'")
    db.execute("UPDATE templates SET zone_style_overrides = NULL, ink_color = NULL, "
               "ground_color = CASE WHEN ground_color LIKE 'role:%' THEN ground_color END "
               "WHERE id = ?", (template["id"],))
    snapshot = {
        "template_id": template["id"],
        "template": {k: before[k] for k in
                     ("color_overrides", "zone_style_overrides", "ground_color", "ink_color")},
        "sections": changed,
        "pages": pages,
    }
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
               (SNAPSHOT_KEY, json.dumps(snapshot)))
    return len(changed)


def can_undo(db, template_id):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (SNAPSHOT_KEY,)).fetchone()
    try:
        return bool(row) and json.loads(row["value"])["template_id"] == template_id
    except (ValueError, KeyError, TypeError):
        return False


def undo(db, template_id):
    """Puts back what the last palette change replaced. The caller commits."""
    if not can_undo(db, template_id):
        return False
    snapshot = json.loads(db.execute(
        "SELECT value FROM settings WHERE key = ?", (SNAPSHOT_KEY,)).fetchone()["value"])
    t = snapshot["template"]
    db.execute("UPDATE templates SET color_overrides = ?, zone_style_overrides = ?, "
               "ground_color = ?, ink_color = ? WHERE id = ?",
               (t["color_overrides"], t["zone_style_overrides"], t["ground_color"],
                t["ink_color"], template_id))
    for s in snapshot["sections"]:
        db.execute("UPDATE sections SET content = ?, bg_color = ?, border_color = ? WHERE id = ?",
                   (s["content"], s["bg_color"], s["border_color"], s["id"]))
    for p in snapshot["pages"]:
        db.execute("UPDATE pages SET bg_color = ? WHERE id = ?", (p["bg_color"], p["id"]))
    db.execute("DELETE FROM settings WHERE key = ?", (SNAPSHOT_KEY,))
    return True
