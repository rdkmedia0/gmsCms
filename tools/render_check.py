"""Prove the renderer did not move.

    docker compose exec -T web python - < tools/render_check.py > before.txt
    ...make the change...
    docker compose exec -T web python - < tools/render_check.py > after.txt
    diff before.txt after.txt

Every tool is rendered TWICE by this app: once by the section chain in
public/page.html and once by render_cell, because a section is typed by
the tool it holds instead of being a container for one. Nineteen tools
have two implementations, thirty-three routes exist in pairs, and the two
copies have already drifted — the Image tool grew a Caption and a Width
select as a section and neither as a cell.

Unifying them is the fix, and this is the net underneath it: a page built
from the tools table itself, every tool laid out once as its own section
and once as a cell of a Columns block, hashed whole and block by block in
both the visitor and the editing view. The only acceptable outcome of the
refactor is that this output does not change. A tool added later is
covered without anyone remembering to add it here.

Runs against a throwaway database and signs in by writing the session
rather than by password, so the dev site is untouched.
"""
import sys, os, io, json, hashlib, re

sys.path.insert(0, "/app")
#  Its OWN database, forced. setdefault was the bug: the container already
#  exports DATA_DIR, so this script quietly built its page in the live
#  site instead of a scratch copy — a real page, thirty real sections, in
#  somebody's actual database. A checking tool that edits the thing it is
#  checking is worse than no tool.
#
#  Under the mounted data directory rather than /tmp, because a rebuild
#  wipes the container's /tmp and the page would be recreated with new row
#  ids each run — which made this compare two databases instead of two
#  renderings. The path is inside the gitignored data/ directory.
os.environ["DATA_DIR"] = "/app/data/.render-check"
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

from app import create_app                       # noqa: E402
from app.db import get_db                        # noqa: E402
from app.services.sections import BLOCK_LIBRARY  # noqa: E402

app = create_app()
app.config["WTF_CSRF_ENABLED"] = False
app.config["SERVER_NAME"] = "localhost"
app.config["PREFERRED_URL_SCHEME"] = "http"


def starter_for(tool):
    """What dropping this tool on a page produces — the same resolution
    _resolve_tool_content does, without needing a request."""
    if tool["block_key"] and tool["block_key"] in BLOCK_LIBRARY:
        return BLOCK_LIBRARY[tool["block_key"]]
    if tool["starter_content"] is not None:
        return tool["section_type"], tool["starter_content"]
    if tool["section_type"] == "columns":
        return "columns", json.dumps({"columns": [""] * 2})
    return tool["section_type"], ""


with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()["id"]
    tools = db.execute("SELECT * FROM content_tools ORDER BY id").fetchall()

    row = db.execute("SELECT id FROM pages WHERE slug = 'every-tool'").fetchone()
    if not row:
        db.execute("INSERT INTO pages (title, slug, page_type, nav_order) "
                   "VALUES ('Every tool', 'every-tool', 'standard', 999)")
        db.commit()
        row = db.execute("SELECT id FROM pages WHERE slug = 'every-tool'").fetchone()
    page_id = row["id"]
    #  Built once and reused. Rebuilding every run gives the sections new
    #  autoincrement ids, and those ids reach into ids and URLs all over
    #  the markup — so two runs of an UNCHANGED app disagreed, which makes
    #  the net useless. Delete the page to force a rebuild after adding a
    #  tool.
    already = db.execute("SELECT COUNT(*) FROM sections WHERE page_id = ?",
                         (page_id,)).fetchone()[0]

    pos, cells = 0, []
    for tool in (() if already else tools):
        s_type, content = starter_for(tool)
        db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (page_id, s_type, tool["name"], content, pos))
        pos += 1
        if s_type != "columns":
            cells.append({"type": s_type, "content": content, "tool_name": tool["name"]})
    if not already:
        db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                   "VALUES (?, 'columns', 'Every tool as cells', ?, ?)",
                   (page_id, json.dumps({"columns": cells}), pos))
        db.commit()

    #  Fix the settings the PAGE reads, so this measures the renderer and
    #  not the machine it runs on. The Email sign-up tool warns its owner
    #  when the site cannot send or has no postal address, which is right
    #  -- and it made this check's output depend on whether somebody had
    #  filled those in, so two runs of an unchanged app disagreed. A
    #  fixture decides what it is measuring.
    for key, value in (("smtp_host", "smtp.example"), ("smtp_username", "checker"),
                       ("smtp_password", "x"), ("to_email", "owner@example.com"),
                       ("legal_business", "Render Check GmbH"),
                       ("legal_address", "1 Test Street" + chr(10) + "0000 Nowhere")):
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()
    covered = len(tools)

client = app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = uid
    sess["username"] = "baseline"

#  Everything above this line is the app booting — including, on the very
#  first run against a fresh database, the initial-admin banner. The check
#  output starts here, so a diff never trips over it.
print("--- render check ---")
print("tools covered: %d (each rendered as a section AND as a cell)" % covered)
def normalise(html):
    """Take the row ids out before hashing.

    The page is rebuilt each run, so its sections get new autoincrement
    ids, and those ids are in every data-section-id, every panel id and
    every URL. Hashing them compares the database, not the renderer.
    """
    html = re.sub(r"/sections/\d+", "/sections/N", html)
    html = re.sub(r"section_id=\d+", "section_id=N", html)
    html = re.sub(r'(data-section-id|data-tool-id|data-blog-id)="\d*"',
                  lambda m: m.group(1) + '="N"', html)
    html = re.sub(r'id="(section|tool-panel)-\d+"',
                  lambda m: 'id="' + m.group(1) + '-N"', html)
    html = re.sub(r"#section-\d+", "#section-N", html)
    #  The Contact Form mints a fresh captcha per request — a different
    #  arithmetic question and a timestamped token. Genuinely per-request,
    #  so it is normalised rather than treated as the renderer moving.
    html = re.sub(r"What is \w+ plus \w+\?", "What is N plus N?", html)
    html = re.sub(r'(name="captcha_token" value=")[^"]*"',
                  lambda m: m.group(1) + 'N"', html)
    #  Stylesheets are linked with ?v=<mtime> so a browser picks up an
    #  edit. Editing any CSS file therefore moves the whole-page hash --
    #  by a ten-digit number, so even the byte count stays the same,
    #  which reads exactly like the renderer moving while nothing
    #  rendered differently at all. It cost a real investigation once.
    #  This check is about markup, and a cache-buster is not markup.
    html = re.sub(r"[?]v=[0-9]+", "?v=N", html)
    #  What is IN the picture library is site state, not rendering. The
    #  editing view lists every uploaded file and every picture the active
    #  template brought, in a JSON block and again as <option> rows -- so
    #  uploading anything, or deleting a stray theme folder, moved the
    #  whole-page hash while nothing rendered differently at all. It cost
    #  two investigations. The LIST is normalised; that the picker exists,
    #  and its shape, still is not.
    html = re.sub(r'(<script type="application/json" id="cms-media-images">).*?(</script>)',
                  lambda m: m.group(1) + "[N]" + m.group(2), html, flags=re.S)
    html = re.sub(r'\s*<option value="/static/(?:uploads|themes)/[^"]*">[^<]*</option>',
                  "", html)
    return html


for mode in ("viewing", "editing"):
    client.get("/admin/view-mode/%s?next=/" % mode)
    body = normalise(client.get("/every-tool").get_data().decode("utf-8", "replace"))
    #  --dump <dir> writes the normalised markup out beside the hashes.
    #  A hash that moves says only THAT something moved; twice now that
    #  has cost an hour of guessing at what. Keep a dump next to a
    #  recorded baseline and the next move is a diff instead.
    if "--dump" in sys.argv:
        where = sys.argv[sys.argv.index("--dump") + 1]
        os.makedirs(where, exist_ok=True)
        with io.open(os.path.join(where, mode + ".html"),
                     "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
    print("%-8s whole page  %s  %d bytes"
          % (mode, hashlib.sha256(body.encode()).hexdigest()[:20], len(body)))
    #  Per-block hashes as well, so a diff names the tool that moved
    #  rather than only saying the page changed.
    #  `[^"]*` matters more than it looks. Anchoring the class attribute
    #  at the closing quote only found a block whose class was EXACTLY
    #  "block block-x" -- so every Image (which carries its width, its
    #  cut-out and its animation as classes) and every tool sitting in a
    #  column (which carries cms-column-body) fell straight through the
    #  net. The one tool this check names in its own docstring as having
    #  drifted was the one it was not hashing.
    for m in re.finditer(r'<section class="block block-([a-z]+)[^"]*"', body):
        start = m.start()
        end = body.find('<section class="block block-', start + 10)
        chunk = body[start:end if end > 0 else start + 4000]
        print("   %-8s block-%-10s %s" % (mode, m.group(1),
              hashlib.sha256(chunk.encode()).hexdigest()[:16]))
