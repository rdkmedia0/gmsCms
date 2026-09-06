"""Patterns: a section you built, saved to drop onto other pages.

A pattern is one section captured whole -- its type, its content and every
styling column that decides how it looks (corners, depth, colour, width,
background, heading, and the per-tool file/media settings) -- so putting it
on another page recreates exactly what you made, not a blank starting
point. It composes only from the tools the section already used, because
it IS that section; there is no bespoke markup here.

Kept local to this install: a pattern reuses the site's own uploads and
tools, so it is a within-site convenience rather than a travelling
package. What travels between installs is a Template Package; a pattern is
the smaller, everyday "save this bit and use it again" alongside it.
"""

#  Everything about a section EXCEPT where it lives (page/zone/position) and
#  the columns the database maintains itself. A whitelist, so a column
#  added later is captured only once it is considered here -- never leaked
#  by accident.
_SKIP = {"id", "page_id", "template_id", "zone", "position",
         "updated_at", "changed_seq"}


def _section_columns(db):
    return [r["name"] for r in db.execute("PRAGMA table_info(sections)").fetchall()
            if r["name"] not in _SKIP]


def list_patterns(db):
    rows = db.execute(
        "SELECT id, name, section_type FROM patterns ORDER BY id DESC").fetchall()
    return [{"id": r["id"], "name": r["name"], "type": r["section_type"]} for r in rows]


def save_pattern(db, section_id, name):
    """Capture a section as a named pattern. Replaces one of the same name,
    so re-saving after a tweak updates it rather than piling up copies."""
    import json
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Give the pattern a name so you can find it later.")
    row = db.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    if not row:
        raise ValueError("That section no longer exists.")
    cols = _section_columns(db)
    data = {c: row[c] for c in cols}
    existing = db.execute("SELECT id FROM patterns WHERE name = ?", (name,)).fetchone()
    if existing:
        db.execute("UPDATE patterns SET section_type = ?, data_json = ? WHERE id = ?",
                   (row["type"], json.dumps(data), existing["id"]))
        pid = existing["id"]
    else:
        cur = db.execute("INSERT INTO patterns (name, section_type, data_json) "
                         "VALUES (?, ?, ?)", (name, row["type"], json.dumps(data)))
        pid = cur.lastrowid
    db.commit()
    return pid


def delete_pattern(db, pattern_id):
    db.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
    db.commit()


def insert_pattern(db, pattern_id, page_id, before_id=None):
    """Create a NEW section on `page_id` from a saved pattern, positioned
    like section_new (before a given section, else appended). Only columns
    that still exist are written, so a pattern saved before a schema change
    still applies. Returns the new section id, or None if the pattern or
    page is gone."""
    import json
    p = db.execute("SELECT data_json FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
    if not p:
        return None
    try:
        data = json.loads(p["data_json"])
    except (ValueError, TypeError):
        return None
    if not db.execute("SELECT 1 FROM pages WHERE id = ?", (page_id,)).fetchone():
        return None
    cols = set(_section_columns(db))
    data = {k: v for k, v in data.items() if k in cols}
    data.setdefault("type", "text")

    before = db.execute(
        "SELECT position FROM sections WHERE id = ? AND page_id = ?",
        (before_id, page_id)).fetchone() if before_id else None
    if before:
        position = before["position"]
        db.execute("UPDATE sections SET position = position + 1 "
                   "WHERE page_id = ? AND position >= ?", (page_id, position))
    else:
        row = db.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p "
                         "FROM sections WHERE page_id = ?", (page_id,)).fetchone()
        position = row["p"]

    names = list(data.keys())
    placeholders = ", ".join(["page_id", "position"] + names)
    values = [page_id, position] + [data[n] for n in names]
    db.execute("INSERT INTO sections (%s) VALUES (%s)"
               % (placeholders, ", ".join(["?"] * len(values))), values)
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.commit()
    return new_id
