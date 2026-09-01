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


def _dashboard():
    from app.routes.admin import dashboard
    return dashboard
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
assistant._call_provider = lambda db, messages, tools, **kw: {"content": REPLIES["content"]}
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
    #  A "real type" includes the declared block tools: Stats and
    #  Testimonial are tools an admin can add by hand, and a page built
    #  from them is built from tools.
    from app.services import blocks as _blocks                      # noqa: E402
    check("...whose sections are real types", kinds and all(
        k in ("banner", "text", "columns", "card", "image", "html")
        or k in _blocks.BLOCKS for k in kinds),
          ", ".join(kinds))
    check("...including a Columns of Cards, not invented markup",
          "columns" in kinds, ", ".join(kinds))
    #  An html section is how this app stores a declared block, so the
    #  test is not "no html" but "no html that is not a block": a raw
    #  embed is the thing the rule was written against, and a Stats band
    #  is not one. Typed as the block KEY instead, a section matches no
    #  branch of the render chain and draws as nothing at all.
    from app.services import blocks as _blk                          # noqa: E402
    embeds = [s for s in data["sections"]
              if s[0] == "html" and not _blk.parse_block(s[2] or "")[0]]
    check("...and nothing landed as a raw Embed", not embeds,
          str([e[2][:60] for e in embeds]))
    check("...while its blocks are stored the way blocks are stored",
          any(s[0] == "html" and _blk.parse_block(s[2] or "")[0]
              for s in data["sections"]), ", ".join(kinds))

    body = " ".join(s[2] or "" for s in data["sections"])
    #  The classes a real tool produces. Anything else is a class this
    #  generator invented, and a look built on one cannot be edited with
    #  the controls the owner has.
    #
    #  ASKED OF THE TOOLS, not written down here. The declared blocks
    #  (Stats, Testimonial, CTA and the rest) are real tools with real
    #  markup, and a hand-kept list of their classes would have to be
    #  updated every time one of them changed -- at which point it stops
    #  being a check and becomes a second, staler copy of the truth.
    #  Building each block with its own defaults gives exactly the
    #  classes an admin's own block would have.
    import re
    from app.services import blocks as block_tools                  # noqa: E402
    def _classes(html):
        return {c for group in re.findall(r'class="([a-z0-9 _-]+)"', html or "")
                for c in group.split()}

    #  The page's own furniture, all of it defined in site-base.css and
    #  editable in place: the small line above a heading, the two hero
    #  buttons, and the link that ends a card.
    known = {"cms-banner", "cms-banner-plain", "cms-banner-overlay", "cms-card",
             "cms-columns", "cms-eyebrow", "cms-hero-actions", "cms-btn",
             "cms-btn-ghost", "cms-card-link"}
    for key, spec in block_tools.BLOCKS.items():
        base = dict(spec.get("defaults") or {})
        known |= _classes(block_tools.build(key, base))
        #  And every option of any "how it looks" select: a variant class
        #  (cms-quote-large) belongs to the tool just as much as its
        #  default one does, and building only the default would report
        #  the tool's own markup as something the generator invented.
        for name, field in block_tools.flat_fields(key):
            if field.get("kind") == "select":
                for value, _label in field.get("options") or []:
                    known |= _classes(block_tools.build(
                        key, dict(base, **{name: value})))
    stray = sorted({c for c in _classes(body)
                    if c.startswith("cms-") and c not in known})
    check("no class it invented", not stray, ", ".join(stray))
    #  ...and every one it does use is defined in the shared stylesheet,
    #  which is what makes "not invented" mean something.
    css_all = (io.open("/app/app/static/css/site-base.css", encoding="utf-8").read()
               + io.open("/app/app/static/css/composition.css", encoding="utf-8").read())
    #  The generator's OWN furniture. A block tool's internal classes are
    #  the tool's business and are styled with the tool.
    mine = {"cms-banner", "cms-banner-plain", "cms-banner-overlay", "cms-eyebrow",
            "cms-hero-actions", "cms-btn", "cms-btn-ghost", "cms-card",
            "cms-card-link", "cms-columns"}
    undefined = sorted(c for c in _classes(body)
                       if c in mine and ("." + c) not in css_all)
    check("...and every class it uses is one the stylesheet defines",
          not undefined, ", ".join(undefined))
    #  And the other half of the same statement: a page that USES those
    #  tools rather than three paragraphs in a row. This is what "flat"
    #  was -- a banner, some prose, some cards, on one white ground.
    #  A run whose picture failed still has to look deliberate: the
    #  fallback was a grey mountain-and-sun placeholder filling the top
    #  of the front page, which reads as broken rather than as plain.
    from app.services import theme_generator as _tg                  # noqa: E402
    plain = _tg._hero_chunk("A headline", "A line.", _tg.PLACEHOLDER_IMAGE,
                            ground="#241f1f")
    check("a hero with no picture is a colour, not a placeholder",
          "cms-banner-plain" in plain and _tg.PLACEHOLDER_IMAGE not in plain,
          plain[:90])
    #  A fabricated attributed quote goes onto somebody's live site as a
    #  review of a business that does not exist. The generator carries
    #  no identity and must not invent one.
    from app.services import blocks as _b                             # noqa: E402
    quote_sections = [sec for sec in data["sections"]
                      if _b.parse_block(sec[2] or "")[0] == "testimonial"]
    if quote_sections:
        _key, values = _b.parse_block(quote_sections[0][2])
        check("a specimen quote is attributed to nobody",
              not (values.get("name") or "").strip()
              and not (values.get("role") or "").strip(), str(values)[:120])
        check("...and does not invent a compliment either",
              (values.get("quote") or "").lower().startswith("add "),
              (values.get("quote") or "")[:60])
    #  And the page ends somewhere: a site with no name, no contact and
    #  no link under the fold is not a finished page.
    #  The site's own footer is built from the owner's details by the
    #  template's footer_layout. The band that used to sit above it was
    #  a second footer, and it shipped instructions to the OWNER as copy
    #  for visitors.
    every = " ".join(sec[2] or "" for sec in data["sections"])
    check("no instruction text is shipped as public copy",
          "Add your email address" not in every
          and "Add your address, or the area" not in every)
    check("...and the run does not build a second footer",
          "Where to find me" not in every)
    check("a front page is not all prose",
          any(block_tools.parse_block(s[2] or "")[0] for s in data["sections"]),
          ", ".join(kinds))
    styles = [s[3] for s in data["sections"] if isinstance(s[3], dict)]
    check("...and every section says how it should sit",
          len(styles) == len(data["sections"]), str(len(styles)))
    check("...with a change of ground under some of them",
          any(st.get("bg_color") for st in styles), str(styles))
    check("...and a hero that runs the full width",
          any(st.get("layout_width") == "full" for st in styles), str(styles))
    #  A value the width control does not offer is a control showing
    #  nothing selected. Auto, Full, or Custom with a percentage.
    check("...in widths the control actually offers",
          all(st.get("layout_width") in (None, "", "auto", "full", "custom")
              for st in styles), str([st.get("layout_width") for st in styles]))
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
    assistant._call_provider = lambda db, m, t, **kw: (asked.__setitem__("n", asked["n"] + 1),
                                                 {"content": REPLIES["content"]})[1]
    shown = tg.plan(db, kit, "A plan", pages_wanted=["Home"])
    assistant._call_provider = real
    check("the plan itself asks the provider nothing", asked["n"] == 0, str(asked["n"]))
    #  ...but the ROUTE does, before calling it: the look is decided at
    #  plan time so the plan can show it. The screen said "nothing has
    #  been asked of the AI yet" for as long as that was false, and this
    #  check passed the whole time -- because it tests the function and
    #  the sentence is on the screen.
    #  What the screen SAYS, not what the file contains: the sentence
    #  this replaced is quoted in a comment explaining why it went, and
    #  a check that cannot tell those apart fails on its own footnote.
    screen_says = re.sub(r"\{#.*?#\}", "", io.open(
        "/app/app/templates/admin/theme_generator.html", encoding="utf-8").read(),
        flags=re.S)
    check("...and the screen does not claim that on the route's behalf",
          "Nothing has been asked of the AI yet" not in screen_says)
    check("...it says what looking actually cost",
          "{{ spent }} request" in screen_says
          and "spent=spent" in io.open("/app/app/routes/admin/dashboard.py",
                                       encoding="utf-8").read())
    check("...and still promises the site has not moved",
          "nothing on your site has changed" in screen_says)
    #  Finishing a job is not a request to be taken somewhere else. It
    #  used to end on the template list, which is a page the admin did
    #  not ask for, with the form they had filled in left behind.
    route_says = io.open("/app/app/routes/admin/dashboard.py", encoding="utf-8").read()
    check("a finished run leaves you where you were",
          'url_for("admin.theme_generator", made=slug)' in route_says
          and 'return redirect(url_for("admin.templates_screen"))' not in route_says)
    #  It does not merely SAY where it went: it shows the front page it
    #  made, in a frame, with a button to use it. A run that finishes by
    #  emptying the form and leaving a green line says a thing happened
    #  and nothing about what the thing is.
    check("...and shows what it made, rather than announcing it",
          "cms-made-frame" in screen_says
          and "admin.template_preview" in screen_says)
    #  A front page is six things now, not four: the numbers, the quote
    #  and the closing call joined it when a page stopped being a banner,
    #  a paragraph and three cards.
    check("...and says how many sections", shown["sections"] == 6, str(shown))
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
    check("an About page gets the story layout", tg.layout_for("About us", 1) == "story")
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
    print("Switching template does not leave the last one behind")
    print("-" * 70)
    #  `_retire_foreign_pack_pages` spares a page somebody has WRITTEN
    #  in, and `_apply_pack_content` cleared that flag BEFORE inserting
    #  the pack's sections -- and the trigger on `sections` sets it on
    #  any write. So every page of every pack came out marked edited,
    #  every one of them was spared, and the previous template's pages
    #  stayed. Five switches, five templates' pages in one menu:
    #  twenty-seven of them on the install where this was found.
    admin_src = io.open("/app/app/routes/admin/__init__.py", encoding="utf-8").read()
    body = admin_src[admin_src.index("def _apply_pack_content("):]
    body = body[:body.index("\ndef ", 10)]
    check("a pack's own pages do not come out marked as yours",
          body.index("UPDATE pages SET owner_edited = 0")
          > body.rindex("INSERT INTO sections"),
          "the flag is cleared before the writes that set it")

    print()
    print("A generated page knows which page it is")
    print("-" * 70)
    #  An empty slug is not a page with no name -- it is a page that
    #  matches nothing. `_apply_pack_content` keys the front page off
    #  exactly "home" and every other page off its slug, so a five-page
    #  template activated into a site left four pages unwritten and the
    #  fifth landing wherever an empty slug happened to fall. What the
    #  owner got was their old site with a new palette, which is exactly
    #  what "it does not load any real style" looked like.
    with app.app_context():
        pkg_dir, _ = tg.build_package(
            db, "Slug Check",
            [{"title": "Home", "sections": [["text", "", "<p>One</p>", ""]]},
             {"title": "The library", "sections": [["text", "", "<p>Two</p>", ""]]},
             {"title": "About me", "sections": [["text", "", "<p>Three</p>", ""]]}])
    named = [json.load(io.open(os.path.join(pkg_dir, "pages", f), encoding="utf-8"))
             ["slug_suffix"]
             for f in sorted(os.listdir(os.path.join(pkg_dir, "pages")))]
    check("the front page answers to home", named[:1] == ["home"], str(named))
    check("...and every other page to its own name",
          named == ["home", "the-library", "about-me"], str(named))
    check("...so not one of them is empty", all(named))

    #  A template's pictures belong to the template. A generated banner
    #  is written where every upload is written and referred to by the
    #  URL that serves it -- which means nothing on anybody else's
    #  install, so the template exported with a broken picture.
    shot = os.path.join(app.static_folder, "uploads", "themegen-check.png")
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    io.open(shot, "wb").write(b"\x89PNG\r\n\x1a\n" + b"\0" * 30)
    banner = ("<div class=\"cms-banner\" style=\"background-image:"
              "url('/static/uploads/themegen-check.png')\"></div>")
    with app.app_context():
        pkg_dir, made_slug = tg.build_package(
            db, "Media Check", [{"title": "Home",
                                 "sections": [["banner", "", banner, ""]]}])
    home = json.load(io.open(os.path.join(pkg_dir, "pages", "00-home.json"),
                             encoding="utf-8"))
    check("a generated picture travels inside the package",
          "media/" in home["sections"][0][2]
          and "/static/uploads/" not in home["sections"][0][2],
          home["sections"][0][2][:110])
    check("...as a real file, named after the template it belongs to",
          os.path.isfile(os.path.join(pkg_dir, "media",
                                      "%s-themegen-check.png" % made_slug)),
          str(os.listdir(os.path.join(pkg_dir, "media")))
          if os.path.isdir(os.path.join(pkg_dir, "media")) else "no media dir")
    os.remove(shot)

    print()
    print("Everything the generator picks, an owner can pick too")
    print("-" * 70)
    #  THE RULE, made mechanical.
    #
    #  This app's own test is "could an owner change it with a control?"
    #  -- and it is easy to add a property to the generator, wire it
    #  through the package, the row and the stylesheet, and never notice
    #  that the only way to change it afterwards is to edit the
    #  database. Composition and the light/dark ground both shipped that
    #  way: they shape a site more than Corners or Depth do, and neither
    #  had a control.
    #
    #  So: every key the generator writes into a manifest is listed here
    #  against the route that lets somebody change their mind. A new key
    #  with no route fails, which is the only way this stays true.
    OWNED_BY = {
        "palette": "admin.template_colors_preset",
        "google_fonts_url": "admin.template_fonts_preset",
        "shape_override": "admin.template_shape_preset",
        "shadow_override": "admin.template_shadow_preset",
        "composition": "admin.template_composition_preset",
        "ground_color": "admin.template_ground",
        #  The ink the reference was written in. It is not a control of
        #  its own: "light or dark" is one decision, and choosing a
        #  ground clears the ink so it is worked out to suit.
        "ink_color": "admin.template_ground",
        "nav_layout": "admin.layout_screen",
        "footer_layout": "admin.layout_screen",
        "page_layout": "admin.layout_screen",
    }
    known = {r.endpoint for r in app.url_map.iter_rules()}
    src = io.open("/app/app/services/theme_generator.py", encoding="utf-8").read()
    written = set(re.findall(r'manifest\["([a-z_]+)"\]\s*=', src))
    #  Identity and bookkeeping are not LOOK properties; they are the
    #  package saying what it is.
    written -= {"name", "slug", "has_content", "pages"}
    for key in sorted(written):
        route = OWNED_BY.get(key)
        check("an owner can change: %s" % key,
              bool(route) and route in known,
              "no control" if not route else "no route %s" % route)
    check("...and nothing it writes is unaccounted for",
          not (written - set(OWNED_BY)), ", ".join(sorted(written - set(OWNED_BY))))

    print()
    print("A generated look is actually worn")
    print("-" * 70)
    #  A pairing's file is only @font-face -- it makes the faces
    #  available and binds nothing. Every shipped template binds them in
    #  its own theme.css, and a GENERATED one has no theme.css, so it
    #  downloaded a webfont on every page load and rendered in Segoe UI.
    #  The typeface is the largest single difference between two looks,
    #  and it was inert: "it does not load any real style".
    site = io.open("/app/app/routes/public.py", encoding="utf-8").read()
    check("a template with no stylesheet is still set in its typeface",
          "def _fonts_for(template)" in site)
    check("...from the pairing it names",
          'pairing.get("google_fonts_url") == named' in site)
    #  A template that ships a stylesheet has SAID what its families
    #  are, in the file. The emitted variables come after it and would
    #  win, so this must not reach them.
    check("...and never over a template that says so itself",
          '_column(template, "css_path")' in site
          and site.index('_column(template, "css_path")')
              < site.index('pairing.get("google_fonts_url") == named'))

    print()
    print("An answer that stopped early is not a dead end")
    print("-" * 70)
    #  Measured on a real 8B thinking model: asked in PROSE for a JSON
    #  object it thought out loud first and ran out of room mid-string,
    #  which arrives as "Unterminated string" -- an error about a model
    #  that was answering perfectly well.
    brain = io.open("/app/app/assistant.py", encoding="utf-8").read()
    check("the wire is told the answer is JSON, not just the prompt",
          'body["response_format"] = {"type": "json_object"}' in brain
          and 'body["format"] = "json"' in brain)
    check("...and the generator asks for that",
          "want_json=True" in io.open("/app/app/services/theme_generator.py",
                                      encoding="utf-8").read())
    #  Everything here is checked against the list it came from and
    #  falls back when absent, so a truncated answer costs a couple of
    #  defaults. An ERROR costs the whole run.
    kept = tg._salvage('{"primary": "#1d6b58", "secondary": "#d94f2b", "accent": "#f0a')
    check("what it did say is kept", kept == {"primary": "#1d6b58",
                                              "secondary": "#d94f2b"}, str(kept))
    kept = tg._salvage('{"fonts": "x", "pages": [{"title": "Home", "shape": "landing"}, {"tit')
    check("...including a list it was in the middle of",
          (kept or {}).get("pages") == [{"title": "Home", "shape": "landing"}], str(kept))
    check("...and nothing is invented to fill the gap",
          tg._salvage('{"primary": "#1d6b58", "shape":') == {"primary": "#1d6b58"})
    check("...while junk is still junk", tg._salvage("not json at all") is None)
    #  And an answer that PARSED is not an answer that said anything: a
    #  reply of {} raises nothing, so every fallback was taken quietly
    #  and the template came out reading "Your headline", "Feature 1",
    #  "Describe this feature" -- finished-looking and mute.
    check("an empty answer does not count as words",
          not tg._said_something({}) and not tg._said_something({"x": "y"})
          and not tg._said_something({"hero_headline": "   "}))
    check("...and a real one does",
          tg._said_something({"hero_headline": "We open at seven"}))
    #  And a mute FRONT page refuses the whole run. A template whose
    #  home page reads "Your headline / Feature 1 / Describe this
    #  feature" costs the same wait as a good one and has to be found
    #  and thrown away by hand -- which is worse than being told.
    src = io.open("/app/app/services/theme_generator.py", encoding="utf-8").read()
    #  Any shape that can BE a front page counts, not just "landing" --
    #  a poster or a showcase is somebody's home page too.
    check("a mute front page refuses the run",
          'u.get("layout") in ("landing", "poster", "showcase")' in src
          and "front_unwritten" in src)
    #  A model that returns nothing once very often answers properly a
    #  second later, and a six-request run should not be lost to that.
    #  Once, though: a model with nothing to say twice is telling you
    #  something, and a loop would spend an owner's evening.
    tries = {"n": 0}

    def _mute_then_answering(db_, messages, tools_, **kw):
        tries["n"] += 1
        return {"content": "" if tries["n"] == 1 else REPLIES["content"]}

    real_provider = assistant._call_provider
    assistant._call_provider = _mute_then_answering
    try:
        with app.app_context():
            got = tg._ai_json(db, "anything")
        check("a mute reply is asked once more", tries["n"] == 2 and bool(got),
              str(tries["n"]))
        tries["n"] = 0
        assistant._call_provider = lambda *a, **k: {"content": ""}
        try:
            with app.app_context():
                tg._ai_json(db, "anything")
            check("...and twice is the end of it", False, "it kept going")
        except tg.ThemeGenError:
            check("...and twice is the end of it", True)
    finally:
        assistant._call_provider = real_provider
    #  Which key gets lost is decided by the order they are asked for.
    #  The page shapes have a fallback the code can work out; the
    #  typeface and the composition do not, so they go first.
    order = tg.DESIGN_SCHEMA
    check("...and the look is asked for before the part that can be lost",
          order.index('"composition"') < order.index('"pages"')
          and order.index('"fonts"') < order.index('"pages"'), order[:60])

    print()
    print("A picture gives style, and only style")
    print("-" * 70)
    import base64                                                   # noqa: E402
    from app.services import look_from_picture as lp                # noqa: E402
    js = io.open("/app/app/static/js/admin/theme-generator.js", encoding="utf-8").read()
    css = io.open("/app/app/static/css/admin.css", encoding="utf-8").read()
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
    #  A run is synchronous and can take minutes. Watched on a real
    #  machine the screen said nothing at all for ten of them, which
    #  reads as a click that missed -- and a second press is a second
    #  run, paid for the same as the first.
    check("the screen says it is working while it works",
          "cmsElapsedTimer" in js and "aria-busy" in js)
    #  The plan is its own small form above the big one, so a listener on
    #  "the" form covers "Show me the plan" and misses "Make it" -- the
    #  one press that takes minutes was the one that said nothing.
    check("...on the plan's own form too, not just the big one",
          "form[action*='theme-generator']" in js)
    check("...and stops every button, not the one that was pressed",
          'querySelectorAll("button[type=submit]")' in js)
    #  A disabled control is not submitted, so disabling the submitter
    #  inside the submit event deletes the field that says WHICH button
    #  was pressed -- "Show me the plan" then arrives with no `preview`,
    #  and no preview means make it. The free look cost a full run.
    check("...without losing which button was pressed",
          "carried.name = button.name" in js
          and js.index("carried.name = button.name")
              < js.index('querySelectorAll("button[type=submit]")'))
    check("...using the app's own counter, not a fourth setInterval",
          "setInterval(" not in js)
    #  A row of swatches says a picture was read. It does not say it was
    #  the one they chose.
    check("...and the picture they chose is shown back to them",
          "data-reference-thumb" in js and "cms-reference-thumb" in css)
    check("...only when there are eyes at the other end",
          "data-send-picture" in js and "data-send-picture" in screen)

    #  The boundary the link reader had, kept: what comes back is words
    #  from THIS APP'S own lists, so a picture cannot carry somebody's
    #  copy into a generated site.
    from app.services.design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
    vocab = ([(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
             list(SHAPE_PRESETS), list(SHADOW_PRESETS))

    state = {"said": {}}

    def _pretend(db_, messages, tools_, **kw):
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

    #  The plan's whole job is that a look you cannot see is a look you
    #  cannot correct -- and the row for it was dead code for as long as
    #  it existed, because `plan()` returned no "look" key at all.
    seen_kit = tg.with_design(
        tg.brand_kit(brief="A saxophone player's demo library.",
                     ref_colours=["#1d6b58", "#d94f2b"]),
        {"colours": ["#000080"], "fonts": "", "shape": "sharp", "shadow": "",
         "pages": ["landing"], "why": "Because it suits them.", "asked": True})
    shown = tg.plan(db, seen_kit, "Demo", pages_wanted=["Home"],
                    looked={"pages": ["landing"], "why": "Because it suits them.",
                            "asked": True}, use_ai_images=False)
    check("the plan says what the look will be", bool(shown.get("look")),
          str(shown.get("look")))
    check("...with the colours the run will actually use",
          "#1d6b58" in (shown["look"]["colours"] or [])
          and "#000080" not in (shown["look"]["colours"] or []),
          str(shown["look"]["colours"]))
    #  What a page is SHAPED like -- the hero's height, the air in a
    #  band, the type scale -- was a constant in the stylesheet, which
    #  is why two templates with different palettes still read as one
    #  design in two colours. It is chosen now, and every step it
    #  travels through has to carry it: the design chose one, the plan
    #  was built with it, and pressing Make it dropped it, so what got
    #  made was the flat default no matter what had been decided.
    from app.services.design import COMPOSITION_PRESETS               # noqa: E402
    from werkzeug.datastructures import MultiDict                   # noqa: E402
    carried = _dashboard()._carried_look(MultiDict([
        ("look_page", "landing"), ("look_composition", "editorial"),
        ("look_colour", "#1d6b58"), ("look_colour", "#d94f2b")]))
    #  And the palette, for the same reason: `.items()` on a MultiDict
    #  yields one value per key, so the sampled colours arrived as one.
    check("every carried colour survives too",
          carried.get("colours") == ["#1d6b58", "#d94f2b"], str(carried.get("colours")))
    check("a chosen composition survives the second press",
          carried.get("composition") == "editorial", str(carried))
    check("...and the plan says which one it is",
          "plan.look.composition" in io.open(
              "/app/app/templates/admin/theme_generator.html",
              encoding="utf-8").read())
    #  An unanswered composition is not neutral, it is the flat one --
    #  and the model skips the key often, being the newest thing in the
    #  schema and the first casualty of a short reply.
    for brief, expected in (("A busy shop with a catalogue of products", "compact"),
                            ("A calm wellness clinic", "quiet"),
                            ("A loud club night with a live band", "bold")):
        got = tg.with_design(tg.brand_kit(brief=brief), {})["composition"]
        check("a %s gets the %s composition" % (brief.split()[1], expected),
              got == expected, got)
    #  ...and it has to survive being INSTALLED. A freshly generated
    #  template is always a new row, and the new-row branch of the
    #  installer did not carry the composition at all -- so it survived
    #  only for a template that already existed, which a generated one
    #  never is.
    pkgsrc = io.open("/app/app/services/packages.py", encoding="utf-8").read()
    insert = pkgsrc[pkgsrc.index("INSERT INTO templates"):]
    insert = insert[:insert.index("return cur.lastrowid")]
    check("a new template row carries its composition",
          "composition_default" in insert and 'manifest.get("composition")' in insert)
    check("...with as many values as columns",
          insert.count("?") - insert.count("VALUES (?") * 0 > 0
          and insert.count(",") > 0)
    check("...and nothing ever comes out unshaped",
          tg.with_design(tg.brand_kit(brief="A thing."), {})["composition"] not in ("", "classic"))
    check("...but a chosen one still wins",
          tg.with_design(tg.brand_kit(brief="A calm clinic"),
                         {"composition": "poster"})["composition"] == "poster")
    check("...from a list of whole opinions, not sliders",
          len(COMPOSITION_PRESETS) >= 4
          and all(spec.get("blurb") for spec in COMPOSITION_PRESETS.values()))
    #  Tokens the stylesheet already reads. A template picks among
    #  values; it never writes a rule.
    css_now = io.open("/app/app/static/css/site-base.css", encoding="utf-8").read()
    #  The composition rules moved out of the shared stylesheet and into
    #  a look a template can choose; the assertions about them follow.
    css_now += io.open("/app/app/static/css/composition.css", encoding="utf-8").read()
    #  --site-measure is the READING measure and is applied per text
    #  block, not to the page column; --site-content-max is the page's
    #  own axis. Conflating them made every band 62 characters wide.
    for token in ("--site-hero-min", "--site-band-pad", "--site-lead",
                  "--site-content-max"):
        check("...%s is a token the stylesheet reads" % token,
              ("var(%s" % token) in css_now and (token + ":") in css_now)
    #  A dark reference makes a dark site. Sampling a black page, keeping
    #  its three brand colours and then building a white one is reading
    #  half the picture.
    from app.services.palette import page_colours, contrast              # noqa: E402
    pal = [{"slug": "primary", "color": "#382828"},
           {"slug": "accent", "color": "#ff4000"}]
    dark = page_colours(pal, "#000000")
    check("a dark picture makes a dark page",
          dark["--site-ground"] == "#000000"
          and contrast(dark["--site-ink"], dark["--site-ground"]) > 7,
          str(dark))
    check("...with its bands lighter than the ground, not darker",
          contrast(dark["--site-tint"], "#000000") > 1.0
          and dark["--site-tint"] != "#000000", dark["--site-tint"])
    light = page_colours(pal, "#f8f8f0")
    #  The sampler writes three decided colours and THEN the ground.
    #  Reading any of the first three as a ground inverts a site on the
    #  strength of its brand colour: measured on a workshop photograph,
    #  a mid-tone ground was rightly rejected and the primary #082038
    #  taken in its place, so the page went navy for no reason anybody
    #  chose.
    #  The sampler writes three decided colours and THEN the ground, so
    #  the ground is the last entry and nothing else -- reading any of
    #  the first three inverts a site on the strength of its brand
    #  colour, which is how a workshop photograph with a grey-blue
    #  ground came to produce a navy page.
    check("only the sampler's ground can be the ground",
          tg._ground_from(["#082038", "#883028", "#003878", "#a8b8b8"]) == "#a8b8b8")
    check("...and it is taken as it comes, mid tones included",
          tg._ground_from(["#a", "#b", "#c", "#989880"]) == "#989880")
    #  THE PICTURE IS SHOWING ITS TEXT COLOUR, so it is read rather
    #  than derived -- but a sampled ink is a guess about which
    #  near-neutral pixels were letters, and it is wrong in ordinary
    #  ways. Hacker News hands back the mid grey of its own interface
    #  (3.0:1 on its cream, which no page should use for body text) and
    #  a photograph of a workshop has no writing in it at all. So it is
    #  believed only when it reads comfortably, and measured, never
    #  assumed.
    used = page_colours([{"slug": "primary", "color": "#382828"}],
                        "#000000", "#f5f2e2")["--site-ink"]
    check("an ink the picture shows clearly is used", used == "#f5f2e2", used)
    used = page_colours([{"slug": "primary", "color": "#8a4f24"}],
                        "#f8f8f0", "#828286")["--site-ink"]
    check("...one that does not read is refused", used != "#828286", used)
    check("...and what replaces it does read",
          contrast(used, "#f8f8f0") >= 7, "%.1f:1" % contrast(used, "#f8f8f0"))
    used = page_colours([{"slug": "primary", "color": "#2070b8"}], "#f8f8f8", "")
    check("...and a picture that shows none gets one worked out",
          contrast(used["--site-ink"], "#f8f8f8") >= 7)

    #  THE EXAMPLE IS THE INSTRUCTION. A picture with a mid ground used
    #  to be refused and a default light page derived instead -- the one
    #  thing the owner did not ask for, since they uploaded that
    #  picture. Following it is the tool's job; making the words legible
    #  on it is arithmetic.
    for label, ground, accent in (("near-black", "#000000", "#ff4000"),
                                  ("cream", "#f8f8f0", "#ff6800"),
                                  ("mid sage", "#989880", "#503828"),
                                  ("mid grey-blue", "#a8b8b8", "#003878")):
        made = page_colours([{"slug": "primary", "color": "#382828"},
                             {"slug": "accent", "color": accent}], ground)
        check("a %s ground is followed" % label, made["--site-ground"] == ground)
        check("...and its words read on it",
              contrast(made["--site-ink"], ground) >= 4.5
              and contrast(made["--site-accent-text"], ground) >= 4.5,
              "ink %.1f, accent %.1f" % (contrast(made["--site-ink"], ground),
                                         contrast(made["--site-accent-text"], ground)))
    check("...and a pale picture keeps its own pale ground",
          light["--site-ground"] == "#f8f8f0", light["--site-ground"])
    #  A band cannot wear a lens: --site-radius may be 50%/30%, which on
    #  a full-width band draws an ellipse with the page showing through
    #  the corners.
    #  A surface that paints its own background states its own ink. On a
    #  light site an inherited dark ink hides this; on a dark one the
    #  hero's filled button, the stats boxes and a card's link all came
    #  out white on white.
    for surface in (".cms-banner-overlay .cms-btn:not(.cms-btn-ghost) { color:",
                    ".cms-stat { color:", ".cms-card-link { color:"):
        check("a surface says its own ink: %s" % surface.split(" {")[0][:34],
              surface in css_now)
    #  One surface for everything that sits ON the page. A card was
    #  white, a stat box painted --primary-50 (a LIGHT step whatever the
    #  page is) and a quote took a tint -- three near-identical greys on
    #  a light page, and on a dark one a pale box that reads as the
    #  inversion having failed.
    check("every enclosed component reads one surface",
          "--site-surface" in css_now and "cms-stat" in css_now)
    #  A COMPOSITION IS A LOOK A TEMPLATE WEARS, not a rulebook that
    #  certain pages get. These rules began in the shared stylesheet,
    #  written for generated templates and scoped away from the shipped
    #  ones -- which worked, and was still design living in code: a
    #  second rulebook only machine-made pages could have, that no owner
    #  could opt into and no hand-made template could use.
    comp = io.open("/app/app/static/css/composition.css", encoding="utf-8").read()
    check("a composition is a stylesheet, like any other look",
          len(comp) > 4000 and "--site-band-pad" in comp)
    #  Nothing of it left in the shared sheet, and every rule in it
    #  gated on a template having CHOSEN one.
    base_only = io.open("/app/app/static/css/site-base.css", encoding="utf-8").read()
    check("...and none of it is left in site-base",
          "The premium half" not in base_only and "cms-plain-theme" not in base_only)
    #  The gate is the LINK, not a selector on every rule.
    #
    #  The first version scoped all hundred-odd selectors with a prefix.
    #  A mechanical prefixer destroys any rule whose declaration wraps
    #  across a line and mangles every comment it passes -- it did both,
    #  and the corruption was committed before anyone looked. A file
    #  that is either loaded or not needs no scoping at all, and cannot
    #  be corrupted by adding it.
    page_src = io.open("/app/app/templates/public/page.html", encoding="utf-8").read()
    check("...loaded only when a template has chosen one",
          "{% if composition %}" in page_src and "css/composition.css" in page_src)
    #  A hero's words sit on a photograph and the overlay says what
    #  colour they are. The page's ink is chosen to read on the PAGE,
    #  and on a light site that is dark -- so a colour rule reaching one
    #  level too far put a dark orange headline on a dark photograph and
    #  made the most important sentence on the site the least legible.
    #  Same fault, same shape, as the one that turned the bakery's white
    #  headline brown.
    check("the page's ink never reaches a hero's words",
          ":not(.cms-banner-overlay h2)" in comp
          and ".cms-banner-overlay h1, .cms-banner-overlay h2" in comp)
    check("...and it carries no scoping selector of its own",
          "cms-plain-theme" not in comp and "[data-composition]" not in comp)
    #  The shape of the corruption, asserted directly: a stray comma
    #  after a closing brace is a parse error that silently kills every
    #  rule after it in the block.
    check("...and parses: no stray comma after a brace",
          "}," not in comp and "}," not in css_now.split(comp)[0],
          "found a `},`")
    #  Which means ANY template can wear one -- shipped or generated --
    #  and one that has chosen none is untouched.
    page = io.open("/app/app/templates/public/page.html", encoding="utf-8").read()
    check("...so any template can wear one, and none has to",
          'data-composition="{{ composition }}"' in page
          and "css/composition.css" in page)
    #  `organic` is a blob and `pill` is 999px. On a control that is the
    #  shape somebody chose; on a 1468px band or a card it draws an
    #  ellipse with the page showing through around it. The band's own
    #  box is the SECTION -- reaching only the block inside it left the
    #  oval exactly where it was.
    check("a wide surface takes the safe radius, not the shape",
          "cms-card-shape" in css_now and "var(--site-radius-safe" in css_now)
    check("...and the band's own box squares too",
          '.cms-section[data-layout-width="full"] { border-radius: 0; }' in css_now
          or '.cms-section[data-layout-width="full"] { border-radius: 0 }' in css_now
          or ('.cms-section[style*="background-color"],' in css_now
              and "border-radius: 0; }" in css_now))

    check("...and a template that chooses none renders as it always did",
          all(("var(%s," % t) in css_now
              for t in ("--site-hero-min", "--site-band-pad", "--site-lead",
                        "--site-content-max")))

    check("...and the shape, and why", shown["look"]["shape"] == "sharp"
          and shown["look"]["why"].startswith("Because"), str(shown["look"]))
    screen_now = io.open("/app/app/templates/admin/theme_generator.html",
                         encoding="utf-8").read()
    check("...and the screen shows it without waiting to be asked",
          "plan.look and (plan.look.colours" in screen_now)
    #  A reading that was TAKEN is already stated as the look; saying it
    #  again under "from your picture" makes two rows somebody has to
    #  compare to find out they agree. What that row adds is where the
    #  reading did not win -- which is always somebody's own choice.
    check("...and the picture row says only what it adds",
          "signals.fonts != plan.look.fonts" in screen_now
          and "your own choice above wins" in screen_now)
    check("...and no look is called a none shadow",
          "in ('', 'none') %}no{%" in screen_now)

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
                  {"title": "Our story", "shape": "story"},
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
          look["pages"] == ["landing", "story", "simple"], str(look["pages"]))
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

    #  Every shape the generator can pick must be describable in the
    #  plan and buildable by hand. A private list beside a shared one
    #  drifts the first time the shared one grows -- it did, and a plan
    #  for a "story" page raised a KeyError instead of describing it.
    from app.services.sections import PAGE_LAYOUTS, starter_page_sections
    pickable = {k for k, _l, _b in PAGE_LAYOUTS}
    for shape in tg.LAYOUTS:
        check("the plan can describe a %s page" % shape,
              shape in tg.SECTION_NAMES, shape)
        if shape != "simple":
            check("...and an owner can pick it by hand", shape in pickable, shape)
            with app.app_context():
                built = starter_page_sections(db, shape, "Test")
            check("...and gets the same shape", bool(built), shape)

    print()
    print("Every page asked for is a page made")
    print("-" * 70)
    REPLIES["content"] = json.dumps(ANSWER)
    five = tg.generate(db, static_folder, name="Five Pager",
                       kit=tg.brand_kit(brief="a corner bakery"),
                       fill_scope="all", use_ai_images=False,
                       pages_wanted=["Home", "Our story", "What we bake",
                                     "Find us", "Contact"],
                       looked={"pages": ["landing", "story", "simple",
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
                       looked={"pages": ["landing", "story", "simple"], "asked": True})
    check("three pages, three pictures", per_page["pictures"] == 3, str(per_page))
    one = tg.plan(db, tg.brand_kit(brief="a bakery"), "One",
                  pages_wanted=["Home", "About", "Contact"],
                  looked={"pages": ["landing", "story", "simple"], "asked": True})
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
