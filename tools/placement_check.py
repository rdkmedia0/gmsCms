"""Every tool, in every place a tool can be put.

    docker compose exec -T web python - < tools/placement_check.py

A tool must work wherever it is placed. Sections and tools are added,
removed and moved around whatever space is free, so none of them may
depend on being in one particular kind of slot. This asks all 180
combinations -- 30 tools across six containers -- three questions each:

    renders   the tool's own block is in that container
    header    the editor gives it a tool header, to move or remove it by
    saves     every form the editor rendered for it round-trips

Containers: a section of its own, a cell of a Columns block, a row inside
one of those cells, the header and sidebar zones, and the footer FOUR
ways -- because a footer is not one shape. It can be empty, with the
tool's own section the first thing in it; or it can have any of the three
starting layouts applied first, with the tool dropped into a cell of what
the preset built, which is how the Contacts tool actually lives there.

Everything is placed through the app's OWN routes -- the ones the editor
calls when somebody drops a tool on a page -- because a harness that
writes the stored JSON by hand only proves the harness can write JSON.
One tool at a time, so what appears is unambiguously what was just placed.

Three false alarms while writing it, all worth knowing, because each
looked exactly like a catastrophic app bug:

  * Marking tools by injecting a span into their starter content reported
    Image, Media Player and File as "does not render" everywhere. Their
    content is a URL, not markup, so the marker was never rendered.
  * Posting to /columns/N/split-rows 404s. The route is /columns/N/rows,
    so every row placement silently did nothing and every tool looked
    unmanageable in a row.
  * Holding the active template's id in a variable reported all three
    ZONES broken for all 30 tools. The first content edit forks the
    builtin and makes the copy active (see fork_active_builtin), so the id
    goes stale and the zone sections get created on a template nobody is
    rendering. It is re-read every time now.

The lesson each time: a uniform failure across every tool is nearly
always the harness, because thirty tools do not break in the same way on
the same day.
"""

import sys
import re
import traceback

sys.path.insert(0, "/app")
#  Its OWN database, forced — the same lesson render_check.py records, and
#  learned again the same way. This script deletes every section on the
#  page it works with, between each of 570 placements. Pointed at a real
#  site that wipes the site, and it did: a container being used for
#  something else lost its content mid-run, and the page open in a browser
#  went on posting to sections that no longer existed.
#
#  Under the mounted data directory rather than /tmp so a rebuild does not
#  discard it. The path is inside the gitignored data/ directory.
import os  # noqa: E402
os.environ["DATA_DIR"] = "/app/data/.placement-check"
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

from bs4 import BeautifulSoup      # noqa: E402
from app import create_app         # noqa: E402
from app.db import get_db          # noqa: E402

app = create_app()
app.config["SERVER_NAME"] = "localhost"
H = {"Origin": "http://localhost", "X-Inline-Edit": "1"}
BASE = "http://localhost"

with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()["id"]
    row = db.execute("SELECT id FROM templates WHERE is_active = 1").fetchone()
    if row is None:
        row = db.execute("SELECT id FROM templates ORDER BY id LIMIT 1").fetchone()
        db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (row["id"],))
        db.commit()
    tid = row["id"]
    tools = [dict(t) for t in db.execute("SELECT * FROM content_tools ORDER BY id")]
    home = db.execute("SELECT id FROM pages WHERE is_home = 1").fetchone()["id"]

c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = uid
#  From THIS database's own file, not the container's. The scratch
#  DATA_DIR above has its own first-run password, and reading the main
#  one meant the password change failed, every admin POST redirected to
#  /admin/account, and every single create was quietly refused -- so the
#  check reported "does not render" for things that render perfectly
#  well. A fresh install insists on that change before it will do
#  anything else; a harness that skips it tests nothing.
#  This scratch database is kept between runs, and changing the password
#  now deletes the file it was written in -- so on every run after the
#  first there is nothing to read, because the password is already the one
#  set below. Absence is the expected state, not a failure.
PASSWORD_NOTE = os.path.join(os.environ["DATA_DIR"], "initial-admin-password.txt")
if os.path.exists(PASSWORD_NOTE):
    gen = re.search(r"password:\s*(\S+)",
                    open(PASSWORD_NOTE, encoding="utf-8").read()).group(1)
    c.post("/admin/account", data={"current_password": gen, "new_password": "Matrix-2026!",
           "confirm_password": "Matrix-2026!"}, headers={"Origin": BASE}, base_url=BASE)
c.get("/admin/view-mode/editing?next=/", base_url=BASE)

#  Settle the site before measuring anything. The FIRST content edit on a
#  site running a builtin forks it into the site's own copy and activates
#  that copy (see fork_active_builtin) -- which can rewrite the page the
#  edit was made on. Left to happen mid-run, the first placement gets its
#  section pulled out from under it and reports "does not render" for
#  something that renders perfectly well. So it is done here, once,
#  deliberately, and thrown away.
c.post("/admin/pages/%d/sections/new" % home, data={"type": "blank", "next": "/"},
       headers=H, base_url=BASE)
with app.app_context():
    _db = get_db()
    _db.execute("DELETE FROM sections WHERE page_id = ?", (home,))
    _db.commit()

#  The footer is asked four ways, not one. A footer is not a fixed shape:
#  it can be empty, it can hold a plain section somebody added, or it can
#  have one of the three starting layouts applied — and a tool has to work
#  in all of them. "footer" below is the bare case (nothing there, the
#  tool's own section is the first thing in it); the three preset cases
#  apply the layout first and then drop the tool into a cell of what the
#  preset built, which is how the Contacts tool actually lives.
#  A Columns block is not one shape either. It can be divided into one
#  through six cells, each cell can be split into rows, and a tool can sit
#  in any of them -- in the body or in a side rail. `bodyN@i` is N columns
#  with the tool in cell i; `bodyNrM@j` divides cell 0 into M rows and puts
#  the tool in row j; `side...` is the same inside the sidebar zone. The
#  ends matter as much as the middle: first and last are where an
#  off-by-one shows up.
CONTAINERS = ("section", "cell", "row", "header", "sidebar",
              "footer", "foot:simple", "foot:centered", "foot:columns",
              "body1@0", "body3@0", "body3@1", "body3@2", "body6@5",
              "body2r4@0", "body2r4@3",
              "side3@0", "side3@2", "side2r4@3")


def active_template():
    """Re-read every time. The first content edit forks the builtin and
    makes the copy active, so an id fetched once goes stale and the zone
    sections land on a template nobody is rendering."""
    with app.app_context():
        r = get_db().execute("SELECT id FROM templates WHERE is_active = 1").fetchone()
    return r["id"] if r else tid


def wipe():
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM sections WHERE page_id = ?", (home,))
        db.execute("DELETE FROM sections WHERE template_id = ?", (active_template(),))
        db.commit()


#  `bodyN@i` is N columns with the tool in cell i; `bodyNrM@j` divides
#  cell 0 into M rows and puts it in row j; `side...` is the same inside
#  the sidebar zone.
DIVIDED = re.compile(r"^(body|side)(\d+)(?:r(\d+))?@(\d+)$")


def high_water():
    with app.app_context():
        r = get_db().execute("SELECT COALESCE(MAX(id), 0) AS n FROM sections").fetchone()
    return r["n"]


def created_since(mark):
    """The section just made, or None if the app refused to make one.

    Taking "the newest section" on its own was wrong: a create the app
    declines -- a sidebar already holds its one top-level section, say --
    then looked like a success, and the check went on to examine some
    other section entirely and report whatever it found there.
    """
    with app.app_context():
        r = get_db().execute("SELECT id FROM sections ORDER BY id DESC LIMIT 1").fetchone()
    sid = r["id"] if r else None
    return sid if (sid is not None and sid > mark) else None


def zone_wipe(zone):
    """A sidebar takes ONE top-level section and refuses a second, so its
    zone is emptied before asking for one."""
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM sections WHERE template_id = ? AND zone = ?",
                   (active_template(), zone))
        db.commit()


def new_body_section(kind, columns=None):
    mark = high_water()
    data = {"type": kind, "next": "/"}
    if columns:
        data["columns"] = str(columns)
    c.post("/admin/pages/%d/sections/new" % home, data=data, headers=H, base_url=BASE)
    return created_since(mark)


def new_zone_section(zone):
    zone_wipe(zone)
    mark = high_water()
    c.post("/admin/templates/%d/%s/sections/new" % (active_template(), zone),
           data={"type": "blank", "next": "/"}, headers=H, base_url=BASE)
    return created_since(mark)


def set_tool(sid, tool, col=None, row=None):
    if col is None:
        url = "/admin/sections/%d/set-tool" % sid
    else:
        url = "/admin/sections/%d/columns/%d/set-tool" % (sid, col)
        if row is not None:
            url += "?row=%d" % row
    c.post(url, data={"tool_id": tool["id"], "next": "/"}, headers=H, base_url=BASE)


def place(tool, where):
    m = DIVIDED.match(where)
    if m:
        side, cols, rows, index = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        if side == "body":
            sid = new_body_section("columns", cols)
        else:
            sid = new_zone_section("sidebar")
            if sid:
                c.post("/admin/sections/%d/divide" % sid,
                       data={"columns": str(cols), "next": "/"}, headers=H, base_url=BASE)
        if sid is None:
            return None
        if rows:
            c.post("/admin/sections/%d/columns/0/rows" % sid,
                   data={"rows": rows, "next": "/"}, headers=H, base_url=BASE)
            set_tool(sid, tool, col=0, row=index)
        else:
            set_tool(sid, tool, col=index)
        return sid
    if where == "section":
        sid = new_body_section("blank")
        if sid:
            set_tool(sid, tool)
        return sid
    if where in ("cell", "row"):
        sid = new_body_section("columns", 2)
        if sid is None:
            return None
        if where == "row":
            c.post("/admin/sections/%d/columns/0/rows" % sid,
                   data={"rows": "2", "next": "/"}, headers=H, base_url=BASE)
            set_tool(sid, tool, col=0, row=0)
        else:
            set_tool(sid, tool, col=0)
        return sid
    if where.startswith("foot:"):
        #  Apply the starting layout the way the Dashboard does, then put
        #  the tool in the first cell of what it built.
        preset = where.split(":", 1)[1]
        tpl = active_template()
        c.post("/admin/templates/%d/apply-footer-layout" % tpl,
               data={"preset": preset, "force": "1", "next": "/"}, headers=H, base_url=BASE)
        with app.app_context():
            row = get_db().execute(
                "SELECT id, type FROM sections WHERE template_id = ? AND zone = 'footer' "
                "ORDER BY position LIMIT 1", (tpl,)).fetchone()
        if row is None:
            return None
        if row["type"] == "columns":
            set_tool(row["id"], tool, col=0)
        else:
            set_tool(row["id"], tool)
        return row["id"]
    sid = new_zone_section(where)
    if sid:
        set_tool(sid, tool)
    return sid


def look(sid):
    html = c.get("/", base_url=BASE).get_data().decode("utf-8", "replace")
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("#section-%d" % sid) or soup.select_one('[data-section-id="%d"]' % sid)
    if node is None:
        for cand in soup.select(".cms-section"):
            if ("/sections/%d/" % sid) in str(cand):
                node = cand
                break
    if node is None:
        return "absent", False, None
    renders = bool(node.select_one("[class*=block-]")) or bool(node.select_one(".cms-column-body"))
    header = bool(node.select_one(".cms-tool-header-label"))
    forms = [f for f in node.select("form.cms-block-config-form, form.cms-inline-form") if f.get("action")]
    forms = [f for f in forms if "/set-tool" not in f["action"] and "/sections/new" not in f["action"]
             and "/columns/0/rows" not in f["action"] and "/delete" not in f["action"]]
    if not forms:
        return renders, header, None
    ok = True
    for form in forms:
        data = {}
        for el in form.find_all(["input", "select", "textarea"]):
            name = el.get("name")
            if not name or el.get("type") == "file":
                continue
            if el.get("type") == "checkbox" and not el.has_attr("checked"):
                continue
            data[name] = el.get_text() if el.name == "textarea" else (el.get("value") or "")
        r = c.post(form["action"], data=data, headers=H, base_url=BASE)
        if r.status_code >= 400:
            ok = False
        elif r.status_code == 302 and "dashboard" in (r.headers.get("Location") or ""):
            ok = False
    return renders, header, ok


results = {}
for tool in tools:
    for where in CONTAINERS:
        wipe()
        try:
            sid = place(tool, where)
            results[(tool["name"], where)] = look(sid) if sid else ("absent", False, None)
        except Exception as exc:  # noqa: BLE001
            #  Said out loud. Swallowing this and letting it read as "does
            #  not render" is how a NameError in the harness spent an hour
            #  looking like six broken containers.
            traceback.print_exc()
            results[(tool["name"], where)] = ("error:" + type(exc).__name__, False, None)

print("%-18s %s" % ("", " ".join("%-10s" % w for w in CONTAINERS)))
broken = []
for tool in tools:
    cells = []
    for where in CONTAINERS:
        renders, header, saves = results[(tool["name"], where)]
        if isinstance(renders, str) and renders.startswith("error:"):
            mark, why = renders[:10], "the harness raised " + renders[6:]
        elif renders is not True:
            mark, why = "NO RENDER", "does not render"
        elif not header:
            mark, why = "no header", "no tool header"
        elif saves is False:
            mark, why = "NO SAVE", "cannot save"
        else:
            mark, why = "ok", None
        if why:
            broken.append((tool["name"], where, why))
        cells.append("%-10s" % mark)
    print("%-18s %s" % (tool["name"][:17], " ".join(cells)))

print()
print("broken: %d of %d" % (len(broken), len(tools) * len(CONTAINERS)))
counts = {}
for _n, where, why in broken:
    counts[(where, why)] = counts.get((where, why), 0) + 1
for (where, why), n in sorted(counts.items(), key=lambda kv: -kv[1]):
    print("   %-12s %-18s %d tools" % (where, why, n))
