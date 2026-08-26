"""Custom content-tool packaging — export/import for admin-created Tools
panel entries (content_tools rows with is_builtin=0), following the same
"a JSON blob is the portable unit" idea Template Packages use for
pages/manifests. A toolkit is one or more tools bundled together; a
single tool is just a toolkit of one. Never touches builtin tools (those
ship with the app itself, not admin-created) and never imports a tool
whose name already exists — see import_tools for the exact rule.
"""
import json

TOOLKIT_FIELDS = ("name", "icon", "section_type", "block_key", "starter_content")


def export_tools(db, tool_ids):
    """Bundles the given custom (non-builtin) tool ids into one portable
    dict, ready for json.dumps and a file download. Silently skips any id
    that doesn't exist or is builtin — exporting is never how a builtin
    tool could leak into someone else's site."""
    if not tool_ids:
        return {"tools": []}
    placeholders = ",".join("?" * len(tool_ids))
    rows = db.execute(
        f"SELECT name, icon, section_type, block_key, starter_content FROM content_tools "
        f"WHERE id IN ({placeholders}) AND is_builtin = 0",
        tool_ids,
    ).fetchall()
    return {"tools": [dict(r) for r in rows]}


def import_tools(db, data):
    """Imports whichever tools in `data["tools"]` don't already exist by
    name (case-insensitive — "Callout" and "callout" are the same tool to
    an admin picking from the panel) — "only import missing tools" means
    a conflicting name is skipped entirely, never overwritten, so
    re-importing the same toolkit twice (or importing a template package
    whose bundled tools overlap ones already installed) is always safe to
    repeat. Returns (imported_names, skipped_names)."""
    tools = (data or {}).get("tools") or []
    if not tools:
        return [], []
    existing_names = {
        (r["name"] or "").strip().lower()
        for r in db.execute("SELECT name FROM content_tools").fetchall()
    }
    max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM content_tools").fetchone()[0]
    imported, skipped = [], []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = (tool.get("name") or "").strip()
        if not name:
            continue
        if name.strip().lower() in existing_names:
            skipped.append(name)
            continue
        section_type = tool.get("section_type") or "html"
        max_pos += 1
        db.execute(
            "INSERT INTO content_tools (name, icon, section_type, block_key, starter_content, is_builtin, position) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (name, tool.get("icon") or "🧰", section_type, tool.get("block_key"), tool.get("starter_content"), max_pos),
        )
        existing_names.add(name.strip().lower())
        imported.append(name)
    return imported, skipped


def export_all_custom_tools(db):
    """Every admin-created tool on this site right now — used both by the
    standalone "export all my tools" action and by Template Packages
    bundling whatever custom tools exist alongside a saved/exported
    template (see services/packages.py's _build_package_dir)."""
    ids = [r["id"] for r in db.execute("SELECT id FROM content_tools WHERE is_builtin = 0").fetchall()]
    return export_tools(db, ids)
