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
                       layout_key="landing", kit=tg.brand_kit(brief=""), fill_scope="none",
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
                         layout_key="simple", kit=tg.brand_kit(brief=""), fill_scope="none",
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
                          layout_key="landing", kit=tg.brand_kit(brief="a corner bakery"), fill_scope="all", use_ai_images=False)
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
                          layout_key="simple", kit=tg.brand_kit(brief="x"), fill_scope="all",
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
                    kit=tg.brand_kit(brief="something"), fill_scope="all", use_ai_images=False)
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
                    kit=tg.brand_kit(brief="something"), fill_scope="all", use_ai_images=False)
        check("prose instead of content is refused", False, "it went through")
    except tg.ThemeGenError as e:
        check("prose instead of content is refused", True)
        check("...and says what to try", "again" in str(e) or "simplify" in str(e),
              str(e))

    try:
        tg.generate(db, static_folder, name="Nope", layout_key="simple",
                    kit=tg.brand_kit(brief=""), fill_scope="all", use_ai_images=False)
        check("no brief is refused before anything is spent", False, "it went through")
    except tg.ThemeGenError as e:
        check("no brief is refused before anything is spent",
              "describe" in str(e).lower(), str(e))

    try:
        tg.generate(db, static_folder, name="Nope", layout_key="nonsense",
                    kit=tg.brand_kit(brief="x"), fill_scope="none", use_ai_images=False)
        check("an unknown layout is refused", False, "it went through")
    except tg.ThemeGenError:
        check("an unknown layout is refused", True)

    print()
    print("One kit, read by everything in the run")
    print("-" * 70)
    #  Each call used to be independent, which is exactly why independent
    #  calls read like different companies: one page formal and one
    #  chatty, a photograph in three styles.
    kit = tg.brand_kit(brief="a corner bakery", tone="expert", voice="i",
                       reading="simple", language="German",
                       fonts="cormorant-jost", shape="soft", shadow="subtle",
                       image_budget="3")
    check("the kit keeps what it was given",
          kit["language"] == "German" and kit["voice"] == "i"
          and kit["fonts"] == "cormorant-jost", str(kit)[:120])
    check("...and refuses what it was not",
          tg.brand_kit(tone="nonsense", fonts="nope", shape="nope")["tone"] == "warm")
    check("...and there is ONE image direction for the whole run",
          bool(kit["image_direction"]) and "consistent" in kit["image_direction"],
          kit["image_direction"])

    REPLIES["content"] = json.dumps(ANSWER)
    prompt = tg._prompt(kit, tg._SCHEMAS["landing"])
    check("the prompt says which language", "German" in prompt, prompt[:120])
    check("...and the tone, and who is speaking",
          "expert" in prompt.lower() and '"I"' in prompt, prompt[:200])
    #  Facts a model does not have are facts it must not invent: a price
    #  or an opening time it made up is one the owner has to find and
    #  correct, and may not.
    check("...and forbids inventing facts the owner has",
          "opening hours" in prompt and "telephone" in prompt)

    print()
    print("The look travels with the template, not over the site")
    print("-" * 70)
    looked = tg.generate(db, static_folder, name="Looked", layout_key="simple",
                         kit=kit, fill_scope="all", use_ai_images=False)
    db.commit()
    man = json.load(io.open(os.path.join(
        static_folder, "themes", looked, "manifest.json"), encoding="utf-8"))
    check("the package carries the shape", man.get("shape_override") == "soft", str(man))
    check("...the shadow", man.get("shadow_override") == "subtle")
    check("...and the fonts, as a LOCAL stylesheet",
          (man.get("google_fonts_url") or "").startswith("/static/fonts/"),
          str(man.get("google_fonts_url")))
    check("...never a live Google Fonts URL",
          "fonts.googleapis.com" not in json.dumps(man))

    print()
    print("Looking costs nothing")
    print("-" * 70)
    #  The plan is worked out without asking anybody anything. If it ever
    #  starts calling the provider, this goes red: the stub records it.
    asked = {"n": 0}
    real = assistant._call_provider
    assistant._call_provider = lambda db, m, t: (asked.__setitem__("n", asked["n"] + 1),
                                                 {"content": REPLIES["content"]})[1]
    shown = tg.plan(kit, "landing", "A plan", "Home")
    assistant._call_provider = real
    check("the plan asks the provider nothing", asked["n"] == 0, str(asked["n"]))
    check("...and says how many sections", shown["sections"] == 4, str(shown))
    check("...how many pictures", shown["pictures"] >= 1, str(shown))
    check("...and what it will cost", shown["calls"] >= 1, str(shown))
    check("...in the language it will write",
          shown["language"] == "German", str(shown["language"]))
    blank = tg.plan(tg.brand_kit(brief="", image_budget="0"), "simple",
                    "Nothing", "Home", use_ai_images=False)
    check("a run that asks nobody says so", blank["calls"] == 0 and not blank["writes"],
          str(blank))
    #  The flaw this check found: the plan promised a picture without
    #  knowing whether the run could make one. It reads the same answers
    #  the run does now.
    no_pics = tg.plan(kit, "landing", "No pictures", "Home", use_ai_images=False)
    check("...and a plan promises no picture the run will not make",
          no_pics["pictures"] == 0 and no_pics["placeholders"] >= 1, str(no_pics))
    check("...counting only the words as its cost", no_pics["calls"] == 1, str(no_pics))

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
shutil.rmtree(DATA_DIR, ignore_errors=True)
sys.exit(1 if failures else 0)
