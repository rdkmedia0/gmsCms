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
                       kit=tg.brand_kit(brief=""), fill_scope="none",
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
                         kit=tg.brand_kit(brief=""), fill_scope="none",
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
                          kit=tg.brand_kit(brief="a corner bakery"), fill_scope="all", use_ai_images=False)
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
                          kit=tg.brand_kit(brief="x"), fill_scope="all",
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
        tg.generate(db, static_folder, name="Nope",
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
        tg.generate(db, static_folder, name="Nope",
                    kit=tg.brand_kit(brief="something"), fill_scope="all", use_ai_images=False)
        check("prose instead of content is refused", False, "it went through")
    except tg.ThemeGenError as e:
        check("prose instead of content is refused", True)
        check("...and says what to try", "again" in str(e) or "simplify" in str(e),
              str(e))

    try:
        tg.generate(db, static_folder, name="Nope",
                    kit=tg.brand_kit(brief=""), fill_scope="all", use_ai_images=False)
        check("no brief is refused before anything is spent", False, "it went through")
    except tg.ThemeGenError as e:
        check("no brief is refused before anything is spent",
              "describe" in str(e).lower(), str(e))

    #  There is no "unknown layout" to refuse any more: nobody picks
    #  one. A shape the model invents is dropped in design() and the page
    #  name decides instead -- checked above.

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
    looked = tg.generate(db, static_folder, name="Looked",
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
    shown = tg.plan(db, kit, "A plan", pages_wanted=["Home"])
    assistant._call_provider = real
    check("the plan asks the provider nothing", asked["n"] == 0, str(asked["n"]))
    check("...and says how many sections", shown["sections"] == 4, str(shown))
    check("...how many pictures", shown["pictures"] >= 1, str(shown))
    check("...and what it will cost", shown["calls"] >= 1, str(shown))
    check("...in the language it will write",
          shown["language"] == "German", str(shown["language"]))
    blank = tg.plan(db, tg.brand_kit(brief="", image_budget="0"), "Nothing",
                    pages_wanted=["Home"], use_ai_images=False)
    check("a run that asks nobody says so", blank["calls"] == 0 and not blank["writes"],
          str(blank))
    #  The flaw this check found: the plan promised a picture without
    #  knowing whether the run could make one. It reads the same answers
    #  the run does now.
    no_pics = tg.plan(db, kit, "No pictures", pages_wanted=["Home"],
                      use_ai_images=False)
    check("...and a plan promises no picture the run will not make",
          no_pics["pictures"] == 0 and no_pics["placeholders"] >= 1, str(no_pics))
    check("...counting only the words as its cost", no_pics["calls"] == 1, str(no_pics))

    print()
    print("A site, not a page")
    print("-" * 70)
    check("pages are read one per line",
          tg.page_list("Home" + chr(10) + "About" + chr(10) + "Contact")
          == ["Home", "About", "Contact"])
    check("...or separated by commas",
          tg.page_list("Home, About, Contact") == ["Home", "About", "Contact"])
    check("...and the same one twice is once",
          tg.page_list("Home" + chr(10) + "home" + chr(10) + "About") == ["Home", "About"])
    #  Guessed from the name, and SHOWN in the plan before it runs -- a
    #  guess somebody can see and change is worth ten they cannot.
    check("the first page is the front page", tg.layout_for("Anything", 0) == "landing")
    check("an About page gets the story layout", tg.layout_for("About us", 1) == "about")
    check("...and anything else the small one", tg.layout_for("Contact", 2) == "simple")

    REPLIES["content"] = json.dumps(ANSWER)
    three = tg.generate(db, static_folder, name="Three Pager",
                        kit=tg.brand_kit(brief="a corner bakery"),
                        fill_scope="all", use_ai_images=False,
                        pages_wanted=["Home", "About", "Contact"])
    db.commit()
    made = sorted(os.listdir(os.path.join(static_folder, "themes", three, "pages")))
    check("three pages asked for, three pages made", len(made) == 3, ", ".join(made))
    check("...in the order they were asked for",
          made[0].startswith("00-home") and made[1].startswith("01-about"),
          ", ".join(made))

    print()
    print("Keeping the words, and saying them differently")
    print("-" * 70)
    page_id = db.execute(
        "INSERT INTO pages (title, slug, is_public) VALUES ('Opening', 'opening', 1)"
    ).lastrowid
    db.execute("INSERT INTO sections (page_id, type, title, content, position) "
               "VALUES (?, 'text', '', ?, 0)",
               (page_id, "<h2>We open at seven</h2><p>Every day except Sunday. "
                         "Call 044 123 45 67.</p>"))
    db.commit()

    kept = tg.generate(db, static_folder, name="Same Words", mode="reskin",
                       kit=tg.brand_kit(brief=""), fill_scope="none",
                       use_ai_images=False)
    db.commit()
    kdir = os.path.join(static_folder, "themes", kept, "pages")
    kbody = " ".join(
        sec[2] or "" for f in os.listdir(kdir)
        for sec in json.load(io.open(os.path.join(kdir, f), encoding="utf-8"))["sections"])
    check("a re-skin keeps every word",
          "We open at seven" in kbody and "044 123 45 67" in kbody, kbody[:100])

    #  A rewrite that loses a fact is the failure this mode must not
    #  have. The stub returns the right NUMBER of lines and keeps the
    #  number, which is what the prompt demands.
    REPLIES["content"] = json.dumps({"lines": [
        "Doors open at seven", "Every day but Sunday. Ring 044 123 45 67."]})
    said = tg.generate(db, static_folder, name="Said Differently", mode="rewrite",
                       kit=tg.brand_kit(brief="", tone="plain"),
                       fill_scope="all", use_ai_images=False)
    db.commit()
    rdir = os.path.join(static_folder, "themes", said, "pages")
    rbody = " ".join(
        sec[2] or "" for f in os.listdir(rdir)
        for sec in json.load(io.open(os.path.join(rdir, f), encoding="utf-8"))["sections"])
    check("a rewrite changes the words", "Doors open at seven" in rbody, rbody[:120])
    check("...and keeps the telephone number", "044 123 45 67" in rbody, rbody[:160])
    check("...and the markup around them", "<h2>" in rbody and "<p>" in rbody)

    #  The important half: an answer of the wrong shape keeps the
    #  original, silently and deliberately.
    REPLIES["content"] = json.dumps({"lines": ["Only one line came back"]})
    dropped = tg.generate(db, static_folder, name="Dropped", mode="rewrite",
                          kit=tg.brand_kit(brief=""), fill_scope="all",
                          use_ai_images=False)
    db.commit()
    ddir = os.path.join(static_folder, "themes", dropped, "pages")
    #  The page this is about, not the whole site: a one-line section
    #  elsewhere legitimately took the stub's one-line answer, and an
    #  assertion over every page reads that as the failure it is testing
    #  for. The two-line section is the one that had to be left alone.
    opening = [f for f in os.listdir(ddir) if "opening" in f]
    dbody = " ".join(
        sec[2] or "" for f in opening
        for sec in json.load(io.open(os.path.join(ddir, f), encoding="utf-8"))["sections"])
    check("a rewrite of the wrong shape keeps the original",
          "We open at seven" in dbody and "044 123 45 67" in dbody
          and "Only one line" not in dbody, dbody[:140])

    print()
    print("A reference gives style, and only style")
    print("-" * 70)
    from app.services import style_extract as sx                  # noqa: E402
    for bad, why in (("file:///etc/passwd", "not http"),
                     ("http://127.0.0.1/", "loopback"),
                     ("http://10.0.0.1/", "private"),
                     ("nonsense", "not a url")):
        try:
            sx.fetch(bad)
            check("refused: %s" % why, False, "it was fetched")
        except sx.RefusedError:
            check("refused: %s" % why, True)
        except Exception as e:                                    # noqa: BLE001
            check("refused: %s" % why, False, type(e).__name__)

    css = ('<style>body{font-family:"Spectral",Georgia,serif;color:#16201c}'
           '.b{background:#1d6b58;border-radius:18px;'
           'box-shadow:0 4px 28px rgba(0,0,0,.2)}'
           '.c{background:#d94f2b;border-radius:20px}</style>'
           '<h1>Their headline</h1><p>Their words, which must not travel.</p>')
    check("it reads the colours",
          sx._interesting(sx._colours(css))[:2] == ["#1d6b58", "#d94f2b"],
          str(sx._interesting(sx._colours(css))))
    check("...the typefaces", sx._fonts(css) == ["Spectral"], str(sx._fonts(css)))
    check("...the corners", sx._shape(css) == "rounded", sx._shape(css))
    check("...and the depth", sx._shadow(css) == "floating", sx._shadow(css))

    #  The boundary, asserted rather than intended: there is nothing in
    #  what this returns that could carry somebody's words.
    read = {"colours": sx._interesting(sx._colours(css)), "fonts": sx._fonts(css),
            "shape": sx._shape(css), "shadow": sx._shadow(css)}
    flat = json.dumps(read)
    check("their words are not in what it read",
          "Their headline" not in flat and "must not travel" not in flat, flat[:120])
    check("...and neither is their markup", "<" not in flat and "class=" not in flat)

    from_ref = tg.brand_kit(ref_colours=["#1d6b58", "#d94f2b"])
    check("read colours become a palette",
          bool(from_ref["palette"]) and from_ref["palette"][0]["color"] == "#1d6b58",
          str(from_ref["palette"]))
    chosen = tg.brand_kit(palette=[{"slug": "primary", "name": "P", "color": "#000080"}],
                          ref_colours=["#1d6b58"])
    check("...but a colour picked by hand wins",
          chosen["palette"][0]["color"] == "#000080", str(chosen["palette"]))

    print()
    print("One question about words, asked once")
    print("-" * 70)
    #  There were TWO controls both labelled Words: where the words come
    #  from, and a second offering "write them for me" or "leave the
    #  sections blank". The same question asked twice, with two answers
    #  that could disagree.
    check("leaving them empty is one of the answers",
          "blank" in dict(tg.MODES), str([m for m, _ in tg.MODES]))
    check("...and whether anybody writes is derived from it",
          tg.fill_scope_for("blank") == "none"
          and tg.fill_scope_for("scratch") == "all"
          and tg.fill_scope_for("reskin") == "all")
    screen = io.open("/app/app/templates/admin/theme_generator.html",
                     encoding="utf-8").read()
    check("...so there is no second control asking it",
          'name="fill_scope"' not in screen)
    check("...and only one control called Words",
          screen.count(">Words</label>") == 1, str(screen.count(">Words</label>")))

    #  A row that is not a choice is removed rather than greyed -- the
    #  rule this app follows for a schedule's irrelevant fields.
    check("each answer declares which rows it needs",
          set(tg.MODE_NEEDS) == {m for m, _ in tg.MODES}, str(sorted(tg.MODE_NEEDS)))
    check("keeping your words needs none of them",
          tg.MODE_NEEDS["reskin"] == ())
    check("...a rewrite needs the voice and nothing else",
          tg.MODE_NEEDS["rewrite"] == ("voice",))
    #  Three, not four: the page shape is no longer a row anybody fills
    #  in -- it is decided from the description and shown in the plan.
    check("...and writing new needs the description, the pages and the voice",
          set(tg.MODE_NEEDS["scratch"]) == {"brief", "pages", "voice"},
          str(tg.MODE_NEEDS["scratch"]))
    for needed in ("brief", "pages", "voice"):
        check("the form has a row for %s" % needed,
              'data-needs="%s"' % needed in screen)

    print()
    print("The look is decided from the description, not picked from a list")
    print("-" * 70)
    #  The screen used to ask an owner to pick a "front page shape" from
    #  three named skeletons, and colours from a list whose first entry
    #  was "the standard colours". Both are this app's vocabulary, and
    #  neither is a question somebody opening this for the first time can
    #  answer. What they CAN describe is their business.
    from app.services.design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS

    REPLIES["content"] = json.dumps({
        "primary": "#1d6b58", "secondary": "#16403a", "accent": "#d94f2b",
        "fonts": "cormorant-jost", "shape": "soft", "shadow": "subtle",
        "pages": [{"title": "Home", "shape": "landing"},
                  {"title": "Our story", "shape": "about"},
                  {"title": "Contact", "shape": "simple"}],
        "why": "Warm and unfussy, like a corner bakery.",
    })
    look = tg.design(db, tg.brand_kit(brief="a corner bakery"),
                     ["Home", "Our story", "Contact"])
    check("it chooses colours", look["colours"] == ["#1d6b58", "#16403a", "#d94f2b"],
          str(look["colours"]))
    check("...a typeface pairing this app actually has",
          look["fonts"] in FONT_PAIRINGS, look["fonts"])
    check("...corners and depth it actually has",
          look["shape"] in SHAPE_PRESETS and look["shadow"] in SHADOW_PRESETS,
          "%s / %s" % (look["shape"], look["shadow"]))
    check("...a shape for every page",
          look["pages"] == ["landing", "about", "simple"], str(look["pages"]))
    check("...and says why, for the owner to read", bool(look["why"]), look["why"])

    #  The important half: a model naming something this app does not
    #  have would otherwise be a look that silently falls back to
    #  nothing, or worse, a font that does not load.
    REPLIES["content"] = json.dumps({
        "primary": "not a colour", "secondary": "#GGGGGG", "accent": "#1d6b58",
        "fonts": "helvetica-neue-ultra", "shape": "bouncy", "shadow": "enormous",
        "pages": [{"title": "Home", "shape": "cinematic"}],
        "why": "",
    })
    junk = tg.design(db, tg.brand_kit(brief="a bakery"), ["Home"])
    check("a colour that is not a colour is dropped",
          junk["colours"] == ["#1d6b58"], str(junk["colours"]))
    check("...a font this app does not have is dropped", junk["fonts"] == "",
          junk["fonts"])
    check("...a shape and a depth it does not have too",
          junk["shape"] == "" and junk["shadow"] == "",
          "%s / %s" % (junk["shape"], junk["shadow"]))
    check("...and a page shape it does not have falls back to the name",
          junk["pages"] == ["landing"], str(junk["pages"]))

    #  What somebody picked themselves always wins over what was worked
    #  out for them.
    mine = tg.with_design(
        tg.brand_kit(brief="x", fonts="grotesk-inter"),
        {"colours": ["#1d6b58"], "fonts": "cormorant-jost", "shape": "pill",
         "shadow": "floating"})
    check("a font picked by hand beats one that was chosen",
          mine["fonts"] == "grotesk-inter", mine["fonts"])
    check("...and the rest is filled in", mine["shape"] == "pill"
          and bool(mine["palette"]), str(mine["shape"]))

    print()
    print("Every page asked for is a page made")
    print("-" * 70)
    REPLIES["content"] = json.dumps(ANSWER)
    five = tg.generate(db, static_folder, name="Five Pager",
                       kit=tg.brand_kit(brief="a corner bakery"),
                       fill_scope="all", use_ai_images=False,
                       pages_wanted=["Home", "Our story", "What we bake",
                                     "Find us", "Contact"],
                       looked={"pages": ["landing", "about", "simple",
                                         "simple", "simple"], "asked": True})
    db.commit()
    made = sorted(os.listdir(os.path.join(static_folder, "themes", five, "pages")))
    check("five asked for, five made", len(made) == 5, ", ".join(made))
    check("...in the order they were asked for",
          made[0].startswith("00-home") and made[4].startswith("04-contact"),
          ", ".join(made))
    #  The shape each page was given is the one the design chose, not the
    #  one its name would have suggested.
    story = json.load(io.open(os.path.join(
        static_folder, "themes", five, "pages", made[1]), encoding="utf-8"))
    check("...and each is the shape it was given",
          len(story["sections"]) == 3, str(len(story["sections"])))

    print()
    print("A banner for every page, when that is asked for")
    print("-" * 70)
    per_page = tg.plan(db, tg.brand_kit(brief="a bakery", banner_per_page=True),
                       "Banners", pages_wanted=["Home", "About", "Contact"],
                       looked={"pages": ["landing", "about", "simple"], "asked": True})
    check("three pages, three pictures", per_page["pictures"] == 3, str(per_page))
    one = tg.plan(db, tg.brand_kit(brief="a bakery"), "One",
                  pages_wanted=["Home", "About", "Contact"],
                  looked={"pages": ["landing", "about", "simple"], "asked": True})
    check("...and one otherwise, at the top of the front page",
          one["pictures"] == 1, str(one["pictures"]))
    check("...which is said in what it costs",
          per_page["calls"] > one["calls"],
          "%d vs %d" % (per_page["calls"], one["calls"]))

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
shutil.rmtree(DATA_DIR, ignore_errors=True)
sys.exit(1 if failures else 0)
