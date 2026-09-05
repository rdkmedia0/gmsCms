"""Does a tool offer the same controls wherever it is standing?

The whole "one renderer per tool" item was about this one question, and
it was always answered by reading. This answers it by rendering: every
tool is put on a page BOTH as a section of its own and as a cell of a
Columns section, the editor's panel is pulled out of each, and the two
are compared with the things that legitimately differ taken out --
the ids, the URLs, and the column index inside them.

What is left after that removal is the tool talking: its label, its
fields, its options, its hints, its buttons. If those differ, the same
tool is a different tool depending on where somebody dropped it, which
is exactly the complaint this item existed to close.

Run inside the container:

    docker compose exec -T web python /tmp/pc2.py
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")
DATA_DIR = tempfile.mkdtemp(prefix="parity-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import bootstrap                                     # noqa: E402
from app.services.sections import BLOCK_LIBRARY               # noqa: E402
from app.routes.admin import _list_tools                      # noqa: E402

app = create_app()
client = app.test_client()


def starter_for(tool):
    """What dropping this tool produces, without needing a request."""
    if tool["block_key"] and tool["block_key"] in BLOCK_LIBRARY:
        return BLOCK_LIBRARY[tool["block_key"]]
    if tool["starter_content"] is not None:
        return tool["section_type"], tool["starter_content"]
    if tool["section_type"] == "columns":
        return "columns", json.dumps({"columns": [""] * 2})
    return tool["section_type"], ""


with app.app_context():
    db = get_db()
    bootstrap.clear_generated_password_flag(db)
    uid = db.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()["id"]
    tools = [t for t in _list_tools(db) if t["section_type"] != "columns"]
    #  A page each. On a shared page the panels can only be told apart by
    #  their label, and several tools appear in more than one starter --
    #  four Text panels, three Menus -- so the pairing guessed. One tool
    #  per page means the two panels on it are that tool's, twice.
    pages = []
    for position, tool in enumerate(tools):
        slug = "parity-%d" % position
        cur = db.execute("INSERT INTO pages (title, slug, page_type, nav_order) "
                         "VALUES (?, ?, 'standard', ?)", (tool["name"], slug, 900 + position))
        page_id = cur.lastrowid
        section_type, content = starter_for(tool)
        section_id = db.execute(
            "INSERT INTO sections (page_id, type, title, content, position) "
            "VALUES (?, ?, '', ?, 0)", (page_id, section_type, content)).lastrowid
        cell = {"type": section_type, "content": content, "tool_name": tool["name"]}
        columns_id = db.execute(
            "INSERT INTO sections (page_id, type, title, content, position) "
            "VALUES (?, 'columns', '', ?, 1)",
            (page_id, json.dumps({"columns": [cell, ""]}))).lastrowid
        pages.append({"name": tool["name"], "slug": slug,
                      "section": section_id, "columns": columns_id})
    db.commit()

with client.session_transaction() as s:
    s["user_id"] = uid
client.get("/admin/view-mode/editing?next=/")


def panels(markup):
    """(label, controls) for every tool panel on the page.

    By LABEL, not by position: a tool in a cell brings its Columns
    section's own panel with it, so the panels do not alternate section,
    cell, section, cell -- a first version compared every tool against
    the next one along and reported all 33 as different, which is the
    sort of result that should make you check the check.

    And the controls are taken by COUNTING the divs, because they
    contain divs of their own: a regex that stops at the first
    </div></div> takes half of one panel in a section and half of the
    next thing in a cell.
    """
    out = []
    for match in re.finditer(r'<span class="cms-tool-header-label">(.*?)</span>', markup, re.S):
        opened = markup.find('<div class="cms-tool-header-controls">', match.end())
        if opened < 0:
            continue
        i = opened + len('<div class="cms-tool-header-controls">')
        depth = 1
        while depth and i < len(markup):
            nxt_open = markup.find("<div", i)
            nxt_close = markup.find("</div>", i)
            if nxt_close < 0:
                break
            if 0 <= nxt_open < nxt_close:
                depth += 1
                i = nxt_open + 4
            else:
                depth -= 1
                i = nxt_close + 6
        label = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        out.append((label, markup[opened:i]))
    return out


def bare(panel):
    """One panel with everything container-specific taken out.

    An id, a URL and the column inside it are the two containers being
    two containers -- that is not what is being compared. Whitespace goes
    too, since one list of controls emits it differently from nineteen
    inline ones.
    """
    text = re.sub(r'(action|href|data-[a-z-]+-url|data-save-url)="[^"]*"', '', panel)
    #  Which FIELD the corner is stored in is the last real asymmetry
    #  between the two containers, and it is storage rather than
    #  controls: a section has its own corner AND its tool's, so the
    #  tool's is `tool_corner_style`, while a cell has only the tool's
    #  and calls it `corner_style`. The control is the same control; it
    #  writes to a differently-named field. That is the residue of
    #  "sections as pure containers" -- see BOW.md -- and it is
    #  invisible to whoever is using it.
    #  Same for the tool's palette-colour control: a section writes
    #  `tool_text_color`, a cell writes `text_color`. Same control, same
    #  reason.
    text = re.sub(r'data-(corner|shadow|color)-field="[^"]*"', '', text)
    #  And whether removing the tool asks first, which SHOULD differ:
    #  removing a tool that is its own section deletes the section, and
    #  that cannot be undone, while clearing a cell leaves the cell. The
    #  same red x, two different consequences, correctly asked about
    #  differently.
    text = re.sub(r'data-confirm="[^"]*"', '', text)
    text = text.replace("cms-tool-remove-form cms-delete-form", "cms-tool-remove-form")
    text = re.sub(r'title="(Delete this section|Remove this tool)"', '', text)
    text = re.sub(r'\b(id|for|form)="[^"]*"', '', text)
    text = re.sub(r"/sections/\d+(/columns/\d+)?", "", text)
    text = re.sub(r"\s+", " ", re.sub(r">\s+<", "><", text))
    return text.strip()


failures = []


def check(name, ok, detail=""):
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


same, compared, unpaired = 0, 0, []
for page in pages:
    name, slug = page["name"], page["slug"]
    markup = client.get("/" + slug).get_data(as_text=True)
    #  The Columns section brings its own panel; the tool's two are the
    #  ones whose label is the tool's.
    #  By POSITION, not by label. The page holds exactly three panels in
    #  this order -- the tool as a section, the Columns section itself,
    #  then the tool in its cell -- and a label cannot tell them apart:
    #  "Media Player (Audio / Video / YouTube)" is displayed as "Media
    #  Player", and a Text tool's label matches the empty cell beside it.
    #  Found by the URLs a panel carries, which name the section and the
    #  column it belongs to. Not by label (two tools share one) and not
    #  by position (the page shell renders the header's own tools first).
    #  A Text panel carries no URL at all -- its save URL is on the body,
    #  not on the toolbar -- so that one falls back to the first panel
    #  inside its own section element.
    found_here = panels(markup)
    as_section = [c for _l, c in found_here if "/sections/%d/" % page["section"] in c]
    as_cell = [c for _l, c in found_here if "/sections/%d/columns/0" % page["columns"] in c]

    def first_panel_in(section_id):
        at = markup.find('id="section-%d"' % section_id)
        if at < 0:
            return None
        opened = markup.find('<div class="cms-tool-header-controls">', at)
        return next((c for _l, c in panels(markup[at:])), None) if opened >= 0 else None

    if not as_section:
        one = first_panel_in(page["section"])
        as_section = [one] if one is not None else []
    if not as_cell:
        #  A cell with no URLs of its own: take the panel that sits
        #  inside the Columns section and is not the Columns' own.
        #  Bounded by the NEXT section, or the footer's own tools get
        #  counted as this Columns section's cells.
        at = markup.find('id="section-%d"' % page["columns"])
        stop = markup.find('id="section-', at + 10)
        slice_ = markup[at:stop if stop > 0 else len(markup)]
        #  The FIRST panel inside it: a Columns section has no tool panel
        #  of its own -- it is a frame, and the panels inside it belong to
        #  its cells.
        inside = [c for _l, c in panels(slice_)]
        as_cell = [inside[0]] if inside else []
    if len(as_section) != 1 or len(as_cell) != 1:
        unpaired.append("%s (%d as a section, %d as a cell)"
                        % (name, len(as_section), len(as_cell)))
        continue
    mine = [as_section[0], as_cell[0]]
    compared += 1
    if bare(mine[0]) == bare(mine[1]):
        same += 1
        continue
    failures.append(name)
    print("%-58s FAILED" % ("%s offers the same controls in both" % name))
    a, b = bare(mine[0]), bare(mine[1])
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            print("      as a section: ...%s" % a[max(0, i - 50):i + 90])
            print("      as a cell   : ...%s" % b[max(0, i - 50):i + 90])
            break
    else:
        print("      one is longer: %d vs %d" % (len(a), len(b)))

check("every tool's panel appears in both containers", not unpaired, ", ".join(unpaired))
check("every tool offers the same controls in both places", same == compared,
      "%d of %d" % (same, compared))

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d tools compared, %d differ" % (compared, compared - same))
sys.exit(1 if failures else 0)
