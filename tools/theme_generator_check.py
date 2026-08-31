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
    print("A picture gives style, and only style")
    print("-" * 70)
    import base64                                                   # noqa: E402
    from app.services import look_from_picture as lp                # noqa: E402
    js = io.open("/app/app/static/js/admin/theme-generator.js", encoding="utf-8").read()
    screen = io.open("/app/app/templates/admin/theme_generator.html",
                     encoding="utf-8").read()

    #  There WAS a "paste a link" field that fetched the page and read
    #  its CSS. It went for reasons an install's owner cares about more
    #  than we do -- a server reaching out to third-party pages
    #  repeatedly, from one address, is what a scraper looks like, and
    #  being taken for one costs THEM their reachability -- and because
    #  it was refused by exactly the sites people most want to point at:
    #  a bot check answers with a challenge page, and a challenge page
    #  HAS colours, so the reader "succeeded" and returned the wrong
    #  ones.
    check("nothing is fetched from anywhere any more",
          not os.path.exists("/app/app/services/style_extract.py"))
    route = io.open("/app/app/routes/admin/dashboard.py", encoding="utf-8").read()
    check("...and the route asks for no link",
          "reference_url" not in route and "style_extract" not in route)

    #  A picture is checked against what it IS, never what it is called:
    #  a filename is a client-supplied string, and this one is about to
    #  be sent to a model.
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 40
    check("a png is recognised by its bytes", lp._sniff(png) == "image/png")
    check("...a jpeg too", lp._sniff(b"\xff\xd8\xff\xe0" + b"\0" * 20) == "image/jpeg")
    check("...and a lie is not", lp._sniff(b"MZ\x90\0 this is an exe") is None)

    def _as_sent(blob, kind="image/png"):
        return "data:%s;base64,%s" % (kind, base64.b64encode(blob).decode())

    got = lp.accept(_as_sent(png))
    check("an honest picture is taken", got[0] == "image/png" and got[1] == png)
    for blob, why in ((b"MZ\x90\0 not a picture", "not a picture"),
                      (png + b"\0" * (lp.MAX_BYTES + 8), "too large"),
                      (b"", "empty")):
        try:
            lp.accept(_as_sent(blob))
            check("refused: %s" % why, False, "it was taken")
        except lp.PictureError:
            check("refused: %s" % why, True)
    for bad, why in (("/etc/passwd", "not a picture at all"),
                     ("data:image/png;base64,@@@@", "not really base64")):
        try:
            lp.accept(bad)
            check("refused: %s" % why, False, "it was taken")
        except lp.PictureError:
            check("refused: %s" % why, True)

    #  Measured against a real vision model: 943 KB was refused outright
    #  and 87 KB came back EMPTY -- no error, no words, which reads
    #  exactly like a model with nothing to say. The browser shrinks a
    #  picture to around 40 KB; this is what stops anything else through.
    check("a picture too big for a model to answer is refused, not sent",
          lp.MAX_BYTES <= 512 * 1024, str(lp.MAX_BYTES))
    check("...and the browser shrinks it before it gets that far",
          "SEND_SIDE" in js and "toDataURL" in js)
    #  Quality is not a size: the same 0.78 gave 47 KB on a screenshot
    #  and 70 KB on a photograph, and 70 was over the line a model
    #  answered at. What varies is the picture, so the number held fixed
    #  has to be the one that matters.
    check("...to a size, not just to a quality",
          "SEND_MAX_KB" in js and "SEND_QUALITIES" in js)
    check("...only when there are eyes at the other end",
          "data-send-picture" in js and "data-send-picture" in screen)

    #  The boundary the link reader had, kept: what comes back is words
    #  from THIS APP'S own lists, so a picture cannot carry somebody's
    #  copy into a generated site.
    from app.services.design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
    vocab = ([(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
             list(SHAPE_PRESETS), list(SHADOW_PRESETS))

    state = {"said": {}}

    def _pretend(db_, messages, tools_):
        return {"content": json.dumps(state["said"])}

    from app import assistant as asst                               # noqa: E402
    real = asst._call_provider
    asst._call_provider = _pretend
    try:
        with app.test_request_context("/"):
            state["said"] = {"fonts": list(FONT_PAIRINGS)[1], "shape": "rounded",
                             "shadow": "soft", "feel": "warm and unfussy"}
            read = lp.read_with_model(db, "image/png", png, vocab)
            check("the model names a look from the app's own lists",
                  read.get("shape") == "rounded"
                  and read.get("fonts") == list(FONT_PAIRINGS)[1], str(read))
            check("...and three or four words for how it feels",
                  read.get("feel") == "warm and unfussy")

            #  A model naming a font this app cannot load is a look that
            #  silently falls back to nothing.
            state["said"] = {"fonts": "Comic Sans MS", "shape": "brutalist",
                             "shadow": "neon", "feel": "loud"}
            read = lp.read_with_model(db, "image/png", png, vocab)
            check("an answer outside the lists is dropped, not applied",
                  read.get("fonts") == "" and read.get("shape") == ""
                  and read.get("shadow") == "", str(read))

            #  The prompt says do not read the page's words back, and a
            #  model that ignores it must not be able to smuggle markup.
            state["said"] = {"fonts": "", "shape": "", "shadow": "",
                             "feel": "<b>Their headline</b>"}
            read = lp.read_with_model(db, "image/png", png, vocab)
            check("...and what it says about the feel is short, plain words",
                  len(read.get("feel", "")) <= 80, str(read))

            asst._call_provider = lambda *a, **k: {"content": "I cannot see images."}
            check("a model that says nothing useful gives nothing, not junk",
                  lp.read_with_model(db, "image/png", png, vocab) == {})

            def _explodes(*a, **k):
                raise RuntimeError("no vision on this model")

            asst._call_provider = _explodes
            check("...and a provider that refuses does not take the screen down",
                  lp.read_with_model(db, "image/png", png, vocab) == {})
    finally:
        asst._call_provider = real

    #  Said before somebody meets it, not after: a control that quietly
    #  does nothing is worse than one that is missing.
    seeing, why = lp.can_see(db)
    check("whether a model can look at a picture is answered", isinstance(seeing, bool))
    check("...and a no comes with the reason and the way round it",
          seeing or ("colour" in why.lower() and len(why) > 30), why)

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
    print("Colours are described or picked, never borrowed from a template")
    print("-" * 70)
    #  It was a dropdown of every installed template's palette, which is
    #  a strange thing to want: if you wanted that template's colours you
    #  would use that template.
    check("no colour-scheme list on the screen",
          'name="color_preset"' not in screen)
    #  The three inputs are written by a loop over the roles, so the
    #  markup says `name="colour_{{ role }}"`. Asserted on what the
    #  template says, not on what one rendering of it happens to spell.
    check("...colours can be set exactly instead",
          'name="colour_{{ role }}"' in screen and 'name="set_colours"' in screen)
    check("...and described in words", 'name="colour_note"' in screen)

    print()
    print("Several pictures you like")
    print("-" * 70)
    check("more than one can be given",
          "data-add-reference" in screen and "data-references" in screen)
    check("...each of them a picture",
          "data-reference-image" in screen and 'name="reference_url"' not in screen)
    #  The colours are worked out in the BROWSER and sent as hex values.
    #  That is the part that always works: arithmetic on pixels needs no
    #  provider, so an install with no model at all still gets a palette
    #  out of a screenshot.
    js = io.open("/app/app/static/js/admin/theme-generator.js", encoding="utf-8").read()
    check("a picture's colours are read in the browser",
          "getImageData" in js and 'name = "ref_colour"' in js)
    #  Measured against real screenshots: a SMOOTH downscale averages
    #  neighbouring pixels and invents colours that are in no part of the
    #  picture -- it turned Hacker News orange into three tints of peach
    #  and gov.uk into three near-identical blues.
    check("...without inventing colours that are not in it",
          "imageSmoothingEnabled = false" in js)
    #  A brand colour is a decision; a photograph's average is not. And
    #  three shades of one colour is a palette with no secondary and no
    #  accent.
    check("...weighted by how decided a colour is", "sat * sat" in js)
    check("...and the three are actually different from each other",
          "function distinct(" in js and "distinct(found.strong, 3, 90)" in js)
    check("...and the colours need no provider at all",
          "FormData" not in js and "fetch(" not in js)
    check("...and the screen says where the colours are read",
          "in your browser" in screen.lower())
    check("the server takes the sampled colours", 'getlist("ref_colour")' in route)
    check("...and checks a sampled colour is a colour",
          "[0-9a-fA-F]{6}" in route)
    #  A file cannot travel through the second press, so what was read
    #  from it does -- otherwise "Make it" would read the picture again,
    #  another request, and possibly a different answer than the one on
    #  screen.
    #  The file itself is never submitted -- the input has no name. What
    #  travels is what the browser MADE of it: hex colours always, and a
    #  small jpeg copy only when something at the other end can look.
    check("the picture file itself is never uploaded",
          'name="reference_image"' not in screen and "reference_image" not in route)
    check("...and what was read from it survives the second press",
          'name="ref_feel"' in screen and 'name="ref_shape"' in screen)
    check("...which the route reads back rather than asking again",
          'request.form.get("ref_" + k)' in route)
    #  A picture is a starting value for every one of these: what
    #  somebody chose by hand always wins.
    check("a hand-picked shape beats one read from a picture",
          'kit["shape"] = kit["shape"] or signals' in route)

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
shutil.rmtree(DATA_DIR, ignore_errors=True)
sys.exit(1 if failures else 0)
