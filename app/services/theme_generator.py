"""Generating a look as a Template Package.

It used to append three or four sections to whichever page you picked,
and that was the whole of it. Generating five pages meant five
irreversible edits to a live site, and the undo was "delete the sections
it added, one at a time".

It writes a **package** now -- the same unit an admin's saved template
and every shipped one already are -- and installs it through the same
installer an uploaded `.zip` goes through. Six things come with that and
none of them had to be built here:

  * it can be looked at before it is applied, because installing is not
    activating;
  * applying it is one all-or-nothing step;
  * undoing it is re-activating what was active before;
  * it can be exported and given to somebody;
  * its pictures belong to it rather than to a shared folder;
  * `package_inventory()` can say what it will do before it does it.

CLAUDE.md named this as a deferred follow-up -- "a Theme Generator layout
is structurally a package with no content". It is a package with content
now, which is the same insight from the other side.

What has NOT changed, and must not: everything it emits is built from
real tools -- Banner, Text, Card via Columns -- so an owner can edit it
afterwards exactly like something they built by hand. It writes no CSS
and invents no markup. A look is a palette, fonts, a shape and a shadow;
those are values the existing controls already carry, and the generator
picks values rather than writing rules.
"""
import json
import os
import re
import shutil
import tempfile
import uuid
from html import escape

from flask import current_app



PLACEHOLDER_IMAGE = "/static/img/placeholder.svg"


class ThemeGenError(Exception):
    """Something the owner can act on. The route says it and stops."""


# ------------------------------------------------------- the layouts

LAYOUTS = {
    "landing": {
        "label": "Landing",
        "description": "Hero banner, short intro, three feature highlights, "
                       "and a closing call-to-action.",
    },
    "about": {
        "label": "About / Story",
        "description": "Hero banner, a longer story section, and a closing "
                       "call-to-action.",
    },
    "simple": {
        "label": "Simple",
        "description": "Just a hero banner and one text section — the "
                       "smallest useful starting point.",
    },
}

_SCHEMAS = {
    "landing": (
        '{"hero_headline": "...", "hero_subtext": "...", "intro_heading": "...", '
        '"intro_body": "...", "features": [{"title": "...", "body": "..."}, '
        '{"title": "...", "body": "..."}, {"title": "...", "body": "..."}], '
        '"cta_headline": "...", "cta_subtext": "..."}'
    ),
    "about": (
        '{"hero_headline": "...", "hero_subtext": "...", "story_heading": "...", '
        '"story_body": "...", "cta_headline": "...", "cta_subtext": "..."}'
    ),
    "simple": ('{"hero_headline": "...", "hero_subtext": "...", '
               '"body_heading": "...", "body_text": "..."}'),
}


# ---------------------------------------------------- the brand kit
#
#  Everything a run needs to sound and look like ONE site, worked out
#  once and passed into every call. Each call used to be independent,
#  which is exactly why independent calls read like different companies:
#  one page formal and one chatty, one palette and another, a photograph
#  in three styles.
#
#  Every field is a value the app already has a control for -- a font
#  pairing, a shape, a shadow, a palette -- because a generated look has
#  to be one an owner can go on editing.

TONES = (
    ("warm", "Warm and friendly"),
    ("plain", "Plain and direct"),
    ("expert", "Expert and precise"),
    ("playful", "Playful"),
)

VOICES = (("we", "We — a team"), ("i", "I — one person"))

READING = (
    ("simple", "Simple — short sentences, everyday words"),
    ("normal", "Normal"),
    ("technical", "Technical — assumes the reader knows the field"),
)

#  How many pictures a run may make. Named rather than typed, because
#  the number is a cost and a wait, and "6" tells nobody that.
IMAGE_BUDGETS = (
    ("0", "None — use placeholders"),
    ("1", "One, for the top of the page"),
    ("3", "Up to three"),
)


def brand_kit(brief="", tone="warm", voice="we", reading="normal",
              language="English", palette=None, fonts="", shape="", shadow="",
              image_budget="1", ref_colours=None, colour_note="",
              banner_per_page=False, ref_feel=""):
    """One kit, resolved once, read by every prompt and every picture.

    Returns plain data -- no db, no request -- so a checker, a script and
    a route all build it the same way.
    """
    from .design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
    try:
        budget = max(0, min(3, int(image_budget)))
    except (TypeError, ValueError):
        budget = 1
    return {
        "brief": (brief or "").strip(),
        "tone": tone if tone in dict(TONES) else "warm",
        "tone_label": dict(TONES).get(tone, dict(TONES)["warm"]),
        "voice": voice if voice in dict(VOICES) else "we",
        "reading": reading if reading in dict(READING) else "normal",
        "reading_label": dict(READING).get(reading, dict(READING)["normal"]),
        #  A free field on purpose: this app ships in one language and is
        #  installed in many. A closed list would be a list of the
        #  languages somebody thought of.
        "language": (language or "English").strip() or "English",
        #  Colours read off a reference page become a palette like any
        #  other -- three roles, the same three every template has -- and
        #  only when nothing was chosen by hand. What somebody picked
        #  themselves always wins over what was guessed from a URL.
        "palette": palette or _palette_from(ref_colours),
        "fonts": fonts if fonts in FONT_PAIRINGS else "",
        "shape": shape if shape in SHAPE_PRESETS else "",
        "shadow": shadow if shadow in SHADOW_PRESETS else "",
        "image_budget": budget,
        #  What they SAID about colour, in their own words -- "something
        #  warm", "our green", "nothing corporate". A free field because
        #  it is an answer to a question a person can answer; the exact
        #  hexes are worked out from it.
        "colour_note": (colour_note or "").strip(),
        #  A banner for every page rather than one for the run. It costs
        #  a request and a wait per page, which is why it is a question
        #  and not a default.
        "banner_per_page": bool(banner_per_page),
        #  Three or four words for how a picture they showed us FEELS,
        #  read by a model that could look at it. Handed to the design
        #  step, because "warm, unfussy, hand-made" is worth more to the
        #  words and the colours than any font name would be.
        "ref_feel": (ref_feel or "").strip(),
        #  One direction for every picture in a run. Generating each from
        #  its own section's words is why AI sites look assembled out of
        #  stock: five photographs by five photographers.
        "image_direction": _image_direction(brief, tone),
    }


def _palette_from(colours):
    """Three colours read off a page, as a palette this app can use."""
    if not colours:
        return None
    roles = ("primary", "secondary", "accent")
    out = []
    for role, colour in zip(roles, list(colours)[:3]):
        out.append({"slug": role, "name": role.title(), "color": colour})
    return out or None


def _image_direction(brief, tone):
    """What every picture in this run should look like."""
    feel = {
        "warm": "warm natural light, inviting, unstaged",
        "plain": "clean daylight, uncluttered, matter-of-fact",
        "expert": "controlled light, precise, considered composition",
        "playful": "bright, high colour, a sense of movement",
    }.get(tone, "warm natural light, inviting, unstaged")
    return ("photographic, %s, consistent across every image in this set; "
            "no text, no logos, no watermarks" % feel)


# ------------------------------------------------- what to write with
#
#  Three modes, because there are three intentions, and the middle one is
#  what most people with a site already want.

#  ONE question about words, with four answers. It was two controls both
#  labelled "Words" -- this one, and a second further down the form
#  offering "write them for me" or "leave the sections blank" -- which is
#  the same question asked twice, and two answers that could disagree.
#
#  "Leave them empty" belongs here because it IS a way of deciding where
#  the words come from: from nowhere.
MODES = (
    ("reskin", "Keep my words — change only the look"),
    ("rewrite", "Rewrite my words, in the voice below"),
    ("scratch", "Write new words from a description"),
    ("blank", "Leave the sections empty — no AI at all"),
)

#  Which answers need which questions. The form shows only the rows a
#  mode actually uses -- removed, not greyed, which is the rule this app
#  already follows for a schedule's irrelevant fields: a control that is
#  not a choice is not a choice being refused.
MODE_NEEDS = {
    "reskin": (),
    "rewrite": ("voice",),
    "scratch": ("brief", "pages", "voice"),
    "blank": ("pages",),
}


def fill_scope_for(mode):
    """A mode says whether anybody is asked to write. Derived rather than
    asked a second time."""
    return "none" if mode == "blank" else "all"


def _visible_text(html):
    """The words in a chunk of section markup, in order.

    Tags out, entities back, whitespace squeezed. Used to show a model
    what a page currently says without showing it markup it might try to
    imitate.
    """
    from html import unescape
    text = re.sub(r"<[^>]+>", chr(10), html or "")
    return [line.strip() for line in unescape(text).split(chr(10)) if line.strip()]


def site_pages(db, page_ids=None):
    """This site's own pages, as package page data.

    The same shape `build_package` writes and the same shape a shipped
    template's pages/*.json already has -- so "keep my words, change the
    look" is not a special path through the generator, it is the ordinary
    one with the words already written.
    """
    rows = db.execute(
        "SELECT * FROM pages WHERE is_public = 1 ORDER BY nav_order, title").fetchall()
    out = []
    for page in rows:
        if page_ids and page["id"] not in page_ids:
            continue
        sections = db.execute(
            "SELECT * FROM sections WHERE page_id = ? ORDER BY position",
            (page["id"],)).fetchall()
        if not sections:
            continue
        out.append({
            "title": page["title"],
            "slug_suffix": "",
            "meta_description": page["meta_description"] or "",
            "sections": [[s["type"], s["title"] or "", s["content"] or "", ""]
                         for s in sections],
        })
    return out


def rewrite_pages(db, kit, pages):
    """The same pages, said in the voice the kit asks for.

    Conservative on purpose, and the reason is the one thing a rewrite
    must not do: lose a fact. A telephone number or an opening time
    dropped in a rewrite is a mistake the owner has to find, and may
    never. So the model is shown the LINES of a section and asked for the
    same number of lines back; anything else -- a different count, an
    empty answer, a refusal -- keeps the original, silently and
    deliberately.

    Only the sections made of writing are offered. A Blog tool, a form,
    a booking widget are markers resolved against live data, and their
    markup is not prose to be improved.
    """
    written = []
    for page in pages:
        sections = []
        for kind, title, content, width in page["sections"]:
            if kind not in ("text", "banner", "card"):
                sections.append([kind, title, content, width])
                continue
            lines = _visible_text(content)
            if not lines:
                sections.append([kind, title, content, width])
                continue
            new = _rewrite_lines(db, kit, lines, page["title"])
            sections.append([kind, title,
                             _replace_lines(content, lines, new) if new else content,
                             width])
        written.append(dict(page, sections=sections))
    return written


def _rewrite_lines(db, kit, lines, page_title):
    """The same lines, rewritten. None if anything is off."""
    schema = '{"lines": [%s]}' % ", ".join('"..."' for _ in lines)
    prompt = _prompt_file("prompts/theme_generator_rewrite.j2",
                          kit=kit, page=page_title,
                          lines=lines, schema=schema, count=len(lines))
    try:
        answer = _ai_json(db, prompt)
    except ThemeGenError:
        return None
    new = answer.get("lines")
    if not isinstance(new, list) or len(new) != len(lines):
        #  A different number of lines is a rewrite that dropped or
        #  invented something. Kept as it was.
        return None
    if any(not isinstance(line, str) or not line.strip() for line in new):
        return None
    return new


def _replace_lines(html, old_lines, new_lines):
    """Put the rewritten words back where the old ones were.

    Text nodes only: the markup is untouched, so a Banner stays a Banner
    and a Card keeps its shape. Replaced one occurrence at a time and in
    order, because the same word can appear twice on a page.
    """
    from html import escape as _esc
    out = html
    for old, new in zip(old_lines, new_lines):
        out = out.replace(">" + old + "<", ">" + _esc(new) + "<", 1)
    return out


# ------------------------------------------------- deciding the look
#
#  The screen used to ask an owner to pick a "front page shape" from
#  three named skeletons, and colours from a list whose first entry was
#  "the standard colours". Both are internal vocabulary, and neither is a
#  question somebody opening this for the first time can answer. What
#  they CAN describe is their business.
#
#  So the look is derived from the description, from this app's own
#  vocabularies -- and every answer is validated against those same lists
#  here, because a model naming a font this app does not have would be a
#  look that silently falls back to nothing.

DESIGN_SCHEMA = (
    '{"primary": "#RRGGBB", "secondary": "#RRGGBB", "accent": "#RRGGBB", '
    '"fonts": "a key from the list", "shape": "a key from the list", '
    '"shadow": "a key from the list", '
    '"pages": [{"title": "...", "shape": "landing|about|simple"}], '
    '"why": "one sentence"}'
)

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def design(db, kit, pages):
    """What this site should look like, decided from the description.

    Returns a dict of values this app already has controls for, every one
    of them checked against the list it came from. Anything the model
    invents is dropped and the sensible default stands -- a look that
    quietly falls back is better than one that refuses, and the owner
    sees all of it in the plan before anything is made.
    """
    from .design import FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS
    wanted = list(pages) or ["Home"]
    chosen = {}
    if kit["brief"]:
        try:
            chosen = _ai_json(db, _prompt_file(
                "prompts/theme_generator_design.j2",
                kit=kit, pages=wanted, schema=DESIGN_SCHEMA,
                fonts=[(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
                shapes=list(SHAPE_PRESETS), shadows=list(SHADOW_PRESETS),
                layouts=list(LAYOUTS)))
        except ThemeGenError:
            #  A look nobody could decide is not a reason to refuse the
            #  whole run: the shapes fall back to what the page names
            #  suggest, and the palette to the app's own.
            chosen = {}

    colours = [chosen.get(role) for role in ("primary", "secondary", "accent")]
    colours = [c for c in colours if isinstance(c, str) and _HEX.match(c.strip())]

    shapes = {}
    for entry in (chosen.get("pages") or []):
        if isinstance(entry, dict) and entry.get("shape") in LAYOUTS:
            shapes[str(entry.get("title", "")).strip().lower()] = entry["shape"]

    return {
        "colours": [c.lower() for c in colours][:3],
        "fonts": chosen.get("fonts") if chosen.get("fonts") in FONT_PAIRINGS else "",
        "shape": chosen.get("shape") if chosen.get("shape") in SHAPE_PRESETS else "",
        "shadow": chosen.get("shadow") if chosen.get("shadow") in SHADOW_PRESETS else "",
        #  Per page, by title, falling back to what the name suggests.
        "pages": [shapes.get(title.strip().lower()) or layout_for(title, i)
                  for i, title in enumerate(wanted)],
        "why": (chosen.get("why") or "").strip(),
        "asked": bool(chosen),
    }


def with_design(kit, look):
    """The kit, with anything the owner did not choose filled in by the
    design. What somebody picked themselves always wins."""
    made = dict(kit)
    if not made.get("palette") and look.get("colours"):
        made["palette"] = _palette_from(look["colours"])
    for key in ("fonts", "shape", "shadow"):
        made[key] = made.get(key) or look.get(key) or ""
    return made


# ---------------------------------------------------------- the plan
#
#  What a run WILL do, worked out before it does any of it. A generator
#  that spends real money and minutes on a misunderstanding, and only
#  says so afterwards, gets used once.


SECTION_NAMES = {
    "landing": ["a banner across the top", "a short introduction",
                "three cards side by side", "a closing banner"],
    "about": ["a banner across the top", "the story, as running text",
              "a closing banner"],
    "simple": ["a banner across the top", "one block of writing"],
}


def plan(db, kit, name, mode="scratch", pages_wanted=None, looked=None,
         use_ai_images=True, fill_scope="all"):
    """(what it will make, what it will cost) without asking anybody.

    Takes the same answers the run takes, including whether pictures are
    wanted at all -- a plan that promises a photograph the run will not
    make is worse than no plan, and that is exactly what it did before
    the checker caught it.
    """
    if mode in ("reskin", "rewrite"):
        existing = site_pages(db)
        pages = [{"title": p["title"],
                  "sections": ["%d sections, as they are now" % len(p["sections"])]}
                 for p in existing]
        #  A rewrite asks once per text-bearing section, not once per
        #  page. Counted, because it is what the run costs and the
        #  difference between the two modes is the whole bill.
        asks = sum(1 for p in existing for sec in p["sections"]
                   if sec[0] in ("text", "banner", "card") and _visible_text(sec[2]))
        return {
            "name": name or "Generated look",
            "layout": ("Your pages, exactly as they read now"
                       if mode == "reskin" else "Your pages, said differently"),
            "pages": pages,
            "sections": sum(len(p["sections"]) for p in existing),
            "pictures": 0,
            "placeholders": 0,
            "calls": 0 if mode == "reskin" else asks,
            "writes": mode == "rewrite",
            "keeps_words": mode == "reskin",
            "language": kit["language"],
            "tone": kit["tone_label"],
        }

    wanted = pages_wanted or ["Home"]
    #  The look is decided HERE, not when the run starts, so what the
    #  plan shows is what gets made -- and so the owner can look at the
    #  colours and the shapes before anything is written. `looked` is
    #  handed back to `generate` for exactly that reason.
    keys = [k for k in (looked or {}).get("pages") or []]
    if len(keys) != len(wanted):
        keys = [layout_for(title, i) for i, title in enumerate(wanted)]

    writes = bool(kit["brief"]) and fill_scope != "none"
    per_page = kit.get("banner_per_page", False)
    pictures = 0
    if use_ai_images and kit["image_budget"] > 0:
        pictures = len(wanted) if per_page else 1
    pages = [{"title": title, "sections": SECTION_NAMES[key],
              "shape": LAYOUTS[key]["label"]}
             for title, key in zip(wanted, keys)]
    banners = sum(len([x for x in p["sections"] if "banner" in x]) for p in pages)
    return {
        "name": name or "Generated look",
        "layout": ", ".join(LAYOUTS[k]["label"] for k in keys),
        "pages": pages,
        "sections": sum(len(p["sections"]) for p in pages),
        "pictures": pictures,
        "placeholders": max(0, banners - pictures),
        #  One call per page for the words, one per picture.
        "calls": (len(pages) if writes else 0) + pictures,
        "writes": writes,
        "keeps_words": False,
        "language": kit["language"],
        "tone": kit["tone_label"],
        #  The look, taken from the KIT rather than from the design --
        #  which is the whole point of showing it. By here the kit has
        #  already had the design folded in, under anything the owner
        #  picked by hand and anything sampled from their picture, so
        #  this is what the run will actually use. The design's own
        #  colours are a suggestion that may have lost.
        #
        #  There was a row for this and it never appeared: `plan()`
        #  returned no "look" key at all, so the template's `if
        #  plan.look` was dead and the docstring above -- "the owner can
        #  look at the colours and the shapes before anything is
        #  written" -- described something that did not happen.
        "look": {
            "colours": [c.get("color") for c in (kit.get("palette") or [])
                        if c.get("color")][:4],
            "fonts": kit.get("fonts") or "",
            "shape": kit.get("shape") or "",
            "shadow": kit.get("shadow") or "",
            "why": (looked or {}).get("why", ""),
            "asked": bool((looked or {}).get("asked")),
        },
    }



# ------------------------------------------------- asking the provider


def _prompt_file(name, **values):
    """One prompt file, rendered.

    Through the Jinja environment rather than `render_template`, which
    runs the app's context processors -- and one reads the session. A
    service must be callable without a request: from a script, from a
    checker, from the scheduler.
    """
    return current_app.jinja_env.get_template(name).render(**values)


def _prompt(kit, schema):
    """The brand kit, as the prompt file writes it.

    Rendered through the Jinja environment rather than `render_template`,
    which runs the app's context processors -- and one of those reads the
    session. A service must be callable without a request: from a script,
    from a checker, from the scheduler. Dragging Flask's request context
    into one is the thing CLAUDE.md's service rule exists to prevent, and
    it showed up here as "Working outside of request context" the first
    time this was tested outside a browser.
    """
    return _prompt_file("prompts/theme_generator_brief.j2", kit=kit, schema=schema)


def _ai_json(db, prompt):
    """One JSON answer from whatever provider is configured.

    A model that wraps its JSON in a fence is the ordinary case, not an
    error, so the fence is stripped rather than refused.
    """
    from .. import assistant
    try:
        result = assistant._call_provider(
            db, [{"role": "user", "content": prompt}], [])
    except assistant.ProviderError as e:
        raise ThemeGenError("The AI provider did not answer: %s" % e)
    content = (result.get("content") or "").strip()
    content = re.sub(r"^```(?:json)?", "", content).strip()
    content = re.sub(r"```$", "", content).strip()
    if not content:
        #  A small self-hosted model asked for JSON very often returns
        #  nothing at all. Answered in words, and with the way round it,
        #  rather than relayed as an empty reply -- the rule
        #  ai_limits_check.py exists for.
        raise ThemeGenError(
            "The AI returned nothing at all, which a smaller self-hosted "
            "model often does when asked for structured content. Try a "
            "larger model, or generate the layout with the sections left "
            "blank.")
    try:
        return json.loads(content)
    except (ValueError, TypeError) as e:
        raise ThemeGenError(
            "The AI didn't return usable content (%s). Try again, or "
            "simplify the brief." % e)


def _maybe_generate_image(db, prompt, use_ai_images):
    """A picture for the hero, or the placeholder.

    Never a refusal: a look that arrives without its photograph is still
    a look, and the owner can put one in. A provider that cannot make
    pictures AT ALL is a different matter and is said on the screen
    before this runs -- see ai_image.unavailable_reason().
    """
    if not use_ai_images:
        return PLACEHOLDER_IMAGE
    from flask import current_app
    from .. import ai_image
    try:
        if not ai_image.is_configured(db):
            return PLACEHOLDER_IMAGE
        image_bytes = ai_image.generate_image(db, prompt, width=1600, height=600)
    except Exception:                                         # noqa: BLE001
        return PLACEHOLDER_IMAGE
    unique_name = "%s.png" % uuid.uuid4().hex
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(image_bytes)
    url = "/static/uploads/%s" % unique_name
    db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
    db.commit()
    return url


# --------------------------------------------------- building the page
#
#  Every chunk below is markup a real admin could have produced by
#  picking tools from the panel. That is the rule this feature has always
#  followed and the one most easily lost: the moment a generator invents
#  a class of its own, what it makes stops being editable.


def _hero_chunk(headline, subtext, image_url):
    #  Escaped, because these are WORDS somebody (or a model) wrote, not
    #  markup. A stray "<" in a headline is a headline, not a tag.
    return (
        '<div class="cms-banner" style="background-image:url(' + chr(39) + '%s'
        + chr(39) + ')">'
        '<div class="cms-banner-overlay"><h2>%s</h2><p>%s</p></div></div>'
    ) % (escape(image_url, quote=True), escape(headline), escape(subtext))


def _text_chunk(heading, body):
    return "<h2>%s</h2><p>%s</p>" % (escape(heading), escape(body))


def _cards_chunk(cards):
    cells = "".join(
        '<div class="cms-card"><h3>%s</h3><p>%s</p></div>'
        % (escape(card.get("title", "")), escape(card.get("body", "")))
        for card in cards)
    return '<div class="cms-columns">%s</div>' % cells



def layout_chunks(db, layout_key, kit, fill_scope, use_ai_images,
                  want_image=True):
    """The HTML chunks for one layout. `fill_scope` "none" asks nobody.

    Takes the brand KIT rather than a bare brief: the tone, the language
    and the reading level are what stop two pages from the same run
    sounding like two companies, and they can only do that if every call
    gets them.
    """
    if layout_key not in LAYOUTS:
        raise ThemeGenError("Unknown layout.")

    brief = kit["brief"]
    fill = fill_scope != "none"
    copy = {}
    if fill:
        if not brief:
            raise ThemeGenError(
                "Describe your site or business, so the AI has something to "
                "write about.")
        copy = _ai_json(db, _prompt(kit, _SCHEMAS[layout_key]))

    def val(key, fallback):
        return (copy.get(key) or fallback) if fill else fallback

    #  One direction for every picture in a run -- see
    #  brand_kit()["image_direction"].
    hero = _maybe_generate_image(
        db, "A wide background photograph for the top of a website about: %s. %s"
        % (brief or layout_key, kit["image_direction"]),
        use_ai_images and want_image and kit["image_budget"] > 0)

    chunks = []
    if layout_key == "landing":
        chunks.append(_hero_chunk(val("hero_headline", "Your headline"),
                                  val("hero_subtext", "A short supporting line."), hero))
        chunks.append(_text_chunk(val("intro_heading", "Welcome"),
                                  val("intro_body", "Write an introduction here.")))
        features = copy.get("features") if fill else None
        if not features or len(features) < 3:
            features = [{"title": "Feature %d" % (i + 1),
                         "body": "Describe this feature."} for i in range(3)]
        chunks.append(_cards_chunk(features[:6]))
        chunks.append(_hero_chunk(val("cta_headline", "Ready to get started?"),
                                  val("cta_subtext", "Get in touch today."),
                                  PLACEHOLDER_IMAGE))
    elif layout_key == "about":
        chunks.append(_hero_chunk(val("hero_headline", "Our story"),
                                  val("hero_subtext", "A short supporting line."), hero))
        chunks.append(_text_chunk(val("story_heading", "About us"),
                                  val("story_body", "Tell your story here.")))
        chunks.append(_hero_chunk(val("cta_headline", "Let's talk"),
                                  val("cta_subtext", "Reach out anytime."),
                                  PLACEHOLDER_IMAGE))
    else:
        chunks.append(_hero_chunk(val("hero_headline", "Your headline"),
                                  val("hero_subtext", "A short supporting line."), hero))
        chunks.append(_text_chunk(val("body_heading", "Welcome"),
                                  val("body_text", "Write something here.")))
    return chunks


# ------------------------------------------------ writing the package


def _slug(text, fallback="generated"):
    made = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return made or fallback


def free_slug(db, wanted):
    """A slug no template already answers to.

    Two templates sharing one slug means one of them is unreachable, and
    the folder they install into is the same folder.
    """
    base = _slug(wanted)
    slug, i = base, 2
    while db.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
        slug = "%s-%d" % (base, i)
        i += 1
    return slug


def sections_for(chunks):
    """The chunks as section rows a package file can carry.

    Through `_classify_layout_chunk`, which is the same classifier a
    hand-built page's imported layout goes through -- so what lands is a
    real Banner, a real Text and a real Columns of Cards, not markup
    with a type guessed at write time.
    """
    from .sections import _classify_layout_chunk
    out = []
    for chunk in chunks:
        for section in _classify_layout_chunk(chunk):
            #  Four entries, because that is the shape every shipped
            #  package's page file uses: type, title, content, width.
            out.append([section["type"], section.get("title", ""),
                        section["content"], ""])
    return out


def build_package(db, name, pages, palette=None, google_fonts_url=None,
                  shape=None, shadow=None, work_dir=None):
    """Writes a package directory and returns (its path, its slug).

    `pages` is a list of {title, slug_suffix, sections}. A package with
    pages carries `has_content`, which is what makes Load Content mean
    something for it later.
    """
    slug = free_slug(db, name)
    root = work_dir or tempfile.mkdtemp(prefix="themegen-")
    pkg_dir = os.path.join(root, slug)
    os.makedirs(os.path.join(pkg_dir, "pages"), exist_ok=True)

    manifest = {
        "name": name,
        "slug": slug,
        "has_content": bool(pages),
        #  Deliberately absent: business_name, tagline, footer_blurb.
        #  A package MAY carry an identity and this one must not invent
        #  one -- the site's name is the site's, and a generator is the
        #  most likely thing in this app to overwrite it by accident.
    }
    if palette:
        manifest["palette"] = palette
    if google_fonts_url:
        manifest["google_fonts_url"] = google_fonts_url
    #  A shape and a shadow are values the Corners/Depth controls already
    #  carry, and install_theme_package writes them straight onto the
    #  installed row. The generator picks values; it does not write CSS.
    if shape:
        manifest["shape_override"] = shape
    if shadow:
        manifest["shadow_override"] = shadow
    with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    for i, page in enumerate(pages):
        data = {
            "title": page["title"],
            "slug_suffix": page.get("slug_suffix", ""),
            "page_type": "standard",
            "meta_description": page.get("meta_description", ""),
            "sections": page["sections"],
        }
        #  NN- prefix, so the order a package's pages arrive in is the
        #  order they were written rather than whatever the filesystem
        #  hands back.
        path = os.path.join(pkg_dir, "pages",
                            "%02d-%s.json" % (i, _slug(page["title"], "page")))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return pkg_dir, slug


def layout_for(title, index):
    """Which starting arrangement a page called this should get.

    By the name, because the names people give pages mean something: an
    About page wants the story layout and a Contact page wants the small
    one. Guessed rather than asked, and shown in the plan before it runs
    -- a guess somebody can see and change is worth ten they cannot.
    """
    words = (title or "").strip().lower()
    if index == 0:
        return "landing"
    if any(w in words for w in ("about", "story", "who we are", "team", "us")):
        return "about"
    return "simple"


def page_list(raw):
    """The pages somebody asked for, from one field.

    One per line, or separated by commas -- because both are what people
    type, and refusing one of them teaches a format rather than reading
    an answer.
    """
    parts = []
    for line in (raw or "").replace(",", chr(10)).split(chr(10)):
        name = " ".join(line.split())
        if name and name.lower() not in {p.lower() for p in parts}:
            parts.append(name)
    return parts[:12]


def generate(db, static_folder, name, kit, fill_scope, use_ai_images,
             mode="scratch", pages_wanted=None, looked=None):
    """Generate a look, install it as a template, and say which one.

    Installed, NOT activated. That is the whole difference from what this
    did before: it hands back something to look at, keep, throw away or
    export, rather than editing a live page in a way that has to be
    undone by hand.

    Three modes, because there are three intentions:

      * `reskin` keeps every word the site already has and changes only
        the look. No AI at all, and by far the most useful mode for a
        site that already works.
      * `rewrite` says the same things in the voice the kit asks for,
        keeping every fact -- see rewrite_pages() for how carefully.
      * `scratch` writes new pages from the description.
    """
    from . import packages
    name = (name or "").strip() or "Generated look"

    if mode in ("reskin", "rewrite"):
        pages = site_pages(db)
        if not pages:
            raise ThemeGenError(
                "This site has no pages with anything on them yet, so there is "
                "nothing to keep. Write something first, or choose “Write "
                "something new”.")
        if mode == "rewrite":
            pages = rewrite_pages(db, kit, pages)
    else:
        wanted = pages_wanted or ["Home"]
        #  What each page should BE, decided from the description rather
        #  than picked by the owner from three named skeletons. `looked`
        #  is passed in when the plan has already worked it out, so the
        #  run does not ask twice and cannot get a different answer than
        #  the one that was shown.
        chosen = (looked or {}).get("pages") or design(db, kit, wanted)["pages"]
        pages = []
        for i, title in enumerate(wanted):
            key = chosen[i] if i < len(chosen) else layout_for(title, i)
            #  One picture for the run, at the top of the first page --
            #  five hero photographs is five waits and five charges for a
            #  look nobody has approved yet. Unless they asked for one
            #  per page, which is a question on the form and not a
            #  default.
            chunks = layout_chunks(
                db, key, kit, fill_scope, use_ai_images,
                want_image=(i == 0 or kit.get("banner_per_page", False)))
            pages.append({"title": title, "slug_suffix": "",
                          "sections": sections_for(chunks)})

    pkg_dir, slug = build_package(
        db, name, pages,
        palette=kit.get("palette"),
        google_fonts_url=_fonts_url(kit.get("fonts")),
        shape=kit.get("shape"), shadow=kit.get("shadow"))
    try:
        packages.install_theme_package(
            db, slug, static_folder, pkg_dir_override=pkg_dir, is_builtin=False)
    finally:
        shutil.rmtree(os.path.dirname(pkg_dir), ignore_errors=True)
    return slug


def _fonts_url(pairing):
    """The local stylesheet for a font pairing, or nothing.

    Local, always: every selectable font in this app is bundled as real
    .woff2 files and nothing here fetches Google at runtime, by design.
    Never write a fonts.googleapis.com URL into a package -- see
    CLAUDE.md's "Fonts are fully self-hosted".
    """
    if not pairing:
        return None
    from .design import FONT_PAIRINGS
    spec = FONT_PAIRINGS.get(pairing) or {}
    return spec.get("google_fonts_url") or None
