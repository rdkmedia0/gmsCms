"""What the Theme Generator makes, and what it must never touch.

It used to append sections to whichever page you picked. Generating was
therefore an edit to a live site, and undoing it meant deleting the
sections it added, one at a time. It writes a Template Package now and
installs it WITHOUT activating it, so what comes back is something to
look at first.

Five things this asks, and each of them is a way the feature could go
wrong quietly:

  * does it produce a real template, and leave the site alone -- the
    active look, the pages, the site's name?
  * is what it produces built from real TOOLS? The moment a generator
    invents a class of its own, what it makes stops being editable, and
    nothing on screen says so.
  * does it write no CSS? A look is a palette, fonts, a shape and a
    shadow -- values the controls already carry. Rules are not its job.
  * does it refuse in the owner's terms when the AI cannot answer --
    including the empty reply a small self-hosted model gives?
  * are two runs two templates, rather than one overwriting the other?

The provider is stubbed throughout: this is about what the generator
does with an answer, not about getting one.

Run inside the container:

    docker compose exec -T web python tools/theme_generator_check.py
"""
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="themegen-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                            # noqa: E402
from app.db import get_db                                             # noqa: E402
from app import assistant                                             # noqa: E402
from app.services import theme_generator as tg                        # noqa: E402

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


ANSWER = {
    "hero_headline": "Bread, every morning",
    "hero_subtext": "Baked before six.",
    "intro_heading": "Who we are",
    "intro_body": "A bakery on the corner.",
    "features": [{"title": "Sourdough", "body": "Slow."},
                 {"title": "Pastry", "body": "Butter."},
                 {"title": "Cakes", "body": "To order."}],
    "cta_headline": "Come in",
    "cta_subtext": "We open at seven.",
}

REPLIES = {"content": ""}
assistant._call_provider = lambda db, messages, tools: {"content": REPLIES["content"]}
assistant.is_configured = lambda db: True

app = create_app()

with app.app_context():
    db = get_db()
    static_folder = app.static_folder

    print()
    print("It makes a template, and leaves the site alone")
    print("-" * 70)
    before_active = db.execute(
        "SELECT slug FROM templates WHERE is_active = 1").fetchone()
    before_pages = db.execute("SELECT COUNT(*) c FROM pages").fetchone()["c"]
    before_count = db.execute("SELECT COUNT(*) c FROM templates").fetchone()["c"]
    before_name = db.execute(
        "SELECT value FROM settings WHERE key = 'site_title'").fetchone()

    slug = tg.generate(db, static_folder, name="A Checker Look",
                       layout_key="landing", brief="", fill_scope="none",
                       use_ai_images=False)
    db.commit()

    row = db.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
    check("a template row exists", row is not None, slug)
    check("...under the name that was given",
          row is not None and row["name"] == "A Checker Look",
          row["name"] if row else "-")
    check("...and it is one more than before",
          db.execute("SELECT COUNT(*) c FROM templates").fetchone()["c"]
          == before_count + 1)

    #  The whole point of the change.
    check("it is NOT active", row is not None and not row["is_active"])
    after_active = db.execute(
        "SELECT slug FROM templates WHERE is_active = 1").fetchone()
    check("...so whatever was active still is",
          (after_active["slug"] if after_active else None)
          == (before_active["slug"] if before_active else None))
    check("...and no page was written",
          db.execute("SELECT COUNT(*) c FROM pages").fetchone()["c"] == before_pages)
    check("...and it is deletable, not a builtin",
          row is not None and not row["is_builtin"])

    #  A package MAY carry an identity. This one must not invent one: the
    #  site's name is the site's, and a generator is the most likely
    #  thing here to overwrite it by accident.
    after_name = db.execute(
        "SELECT value FROM settings WHERE key = 'site_title'").fetchone()
    check("the site's own name is untouched",
          (after_name["value"] if after_name else None)
          == (before_name["value"] if before_name else None))
    pkg = os.path.join(static_folder, "themes", slug)
    manifest = io.open(os.path.join(pkg, "manifest.json"), encoding="utf-8").read()
    check("...and the package does not carry a business name",
          "business_name" not in manifest and "tagline" not in manifest)

    print()
    print("What it makes is built from tools")
    print("-" * 70)
    import json
    page_dir = os.path.join(pkg, "pages")
    check("it ships a page", os.path.isdir(page_dir) and bool(os.listdir(page_dir)))
    data = json.load(io.open(
        os.path.join(page_dir, sorted(os.listdir(page_dir))[0]), encoding="utf-8"))
    kinds = [s[0] for s in data["sections"]]
    check("...whose sections are real types", kinds and all(
        k in ("banner", "text", "columns", "card", "image", "html") for k in kinds),
          ", ".join(kinds))
    check("...including a Columns of Cards, not invented markup",
          "columns" in kinds, ", ".join(kinds))
    check("...and nothing landed as a raw Embed", "html" not in kinds,
          ", ".join(kinds))

    body = " ".join(s[2] or "" for s in data["sections"])
    #  The classes a real tool produces. Anything else is a class this
    #  generator invented, and a look built on one cannot be edited with
    #  the controls the owner has.
    known = ("cms-banner", "cms-banner-overlay", "cms-card", "cms-columns")
    import re
    used = set(re.findall(r'class="([a-z0-9 -]+)"', body))
    stray = sorted({c for group in used for c in group.split()
                    if c.startswith("cms-") and c not in known})
    check("no class it invented", not stray, ", ".join(stray))
    check("no stylesheet travels with it",
          not os.path.isfile(os.path.join(pkg, "theme.css")))
    check("...and no rule is hidden in the markup",
          "<style" not in body and "@media" not in body)

    print()
    print("Two runs are two templates")
    print("-" * 70)
    second = tg.generate(db, static_folder, name="A Checker Look",
                         layout_key="simple", brief="", fill_scope="none",
                         use_ai_images=False)
    db.commit()
    check("the same name twice does not collide", second != slug,
          "%s vs %s" % (slug, second))
    check("...and both are there",
          db.execute("SELECT COUNT(*) c FROM templates WHERE name = ?",
                     ("A Checker Look",)).fetchone()["c"] == 2)

    print()
    print("The words, when there are words")
    print("-" * 70)
    REPLIES["content"] = json.dumps(ANSWER)
    written = tg.generate(db, static_folder, name="Bakery Look",
                          layout_key="landing", brief="a corner bakery",
                          fill_scope="all", use_ai_images=False)
    db.commit()
    wdir = os.path.join(static_folder, "themes", written, "pages")
    wdata = json.load(io.open(
        os.path.join(wdir, sorted(os.listdir(wdir))[0]), encoding="utf-8"))
    wbody = " ".join(s[2] or "" for s in wdata["sections"])
    check("the AI's words are in the page", "Bread, every morning" in wbody)
    check("...and so are its cards", "Sourdough" in wbody and "Cakes" in wbody)

    #  Words are words. A stray "<" in a headline is a headline.
    REPLIES["content"] = json.dumps(dict(ANSWER, hero_headline="Bread & <b>butter</b>"))
    escaped = tg.generate(db, static_folder, name="Escaped Look",
                          layout_key="simple", brief="x", fill_scope="all",
                          use_ai_images=False)
    db.commit()
    edir = os.path.join(static_folder, "themes", escaped, "pages")
    ebody = json.load(io.open(os.path.join(edir, sorted(os.listdir(edir))[0]),
                              encoding="utf-8"))["sections"][0][2]
    check("what the model wrote is escaped, not injected",
          "&lt;b&gt;" in ebody and "<b>" not in ebody, ebody[:120])

    print()
    print("When it cannot be done, it says why")
    print("-" * 70)
    #  A small self-hosted model asked for JSON very often returns
    #  nothing at all. Relayed as an empty reply it reads as the button
    #  doing nothing.
    REPLIES["content"] = ""
    try:
        tg.generate(db, static_folder, name="Nope", layout_key="simple",
                    brief="something", fill_scope="all", use_ai_images=False)
        check("an empty reply is refused", False, "it went through")
    except tg.ThemeGenError as e:
        said = str(e)
        check("an empty reply is refused", True)
        check("...in the owner's terms, with a way round",
              "nothing" in said.lower() and ("larger" in said or "blank" in said),
              said)

    REPLIES["content"] = "I'm afraid I can't do that."
    try:
        tg.generate(db, static_folder, name="Nope", layout_key="simple",
                    brief="something", fill_scope="all", use_ai_images=False)
        check("prose instead of content is refused", False, "it went through")
    except tg.ThemeGenError as e:
        check("prose instead of content is refused", True)
        check("...and says what to try", "again" in str(e) or "simplify" in str(e),
              str(e))

    try:
        tg.generate(db, static_folder, name="Nope", layout_key="simple",
                    brief="", fill_scope="all", use_ai_images=False)
        check("no brief is refused before anything is spent", False, "it went through")
    except tg.ThemeGenError as e:
        check("no brief is refused before anything is spent",
              "describe" in str(e).lower(), str(e))

    try:
        tg.generate(db, static_folder, name="Nope", layout_key="nonsense",
                    brief="x", fill_scope="none", use_ai_images=False)
        check("an unknown layout is refused", False, "it went through")
    except tg.ThemeGenError:
        check("an unknown layout is refused", True)

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
shutil.rmtree(DATA_DIR, ignore_errors=True)
sys.exit(1 if failures else 0)
