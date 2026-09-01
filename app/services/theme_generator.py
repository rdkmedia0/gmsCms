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

#  READ from PAGE_LAYOUTS, not kept here.
#
#  These were three private arrangements with their own names, so the
#  generator could build a page shape an owner had no way to choose.
#  That is this app's rule about tools, applied to arrangements: if the
#  machine can make it, a person can pick it. The words the plan shows
#  are the words the "new page" screen shows, because they are the same
#  words.
#
#  A plain import, at import time: `services.sections` imports nothing
#  from here, and it has to stay that way round.
from .sections import PAGE_LAYOUTS as _PAGE_LAYOUTS

LAYOUTS = {
    key: {"label": label, "description": blurb}
    for key, label, blurb in _PAGE_LAYOUTS
    if key in ("landing", "story", "poster", "showcase")
}
#  The smallest shape a page can be. It predates the shared list and is
#  what every fallback lands on, so it is named here rather than offered
#  on the "new page" screen, where "Standard page" already means it.
LAYOUTS["simple"] = {
    "label": "Simple",
    "description": "A banner across the top and one block of writing.",
}

_SCHEMAS = {
    #  A front page is not three paragraphs. The numbers, the quote and
    #  the closing call are asked for in the SAME request as the rest --
    #  one call, one voice, and a page with something on it besides
    #  prose.
    "landing": (
        '{"hero_headline": "...", "hero_subtext": "...", "intro_heading": "...", '
        '"intro_body": "...", "features": [{"title": "...", "body": "..."}, '
        '{"title": "...", "body": "..."}, {"title": "...", "body": "..."}], '
        '"eyebrow": "two or three words above the headline, like a category", '
        '"hero_button": "two or three words on a button, an action", '
        '"card_link": "two or three words, the same for every card, like Read more", '
        '"stats": [{"value": "a number or short figure", "label": "what it counts"}, '
        '{"value": "...", "label": "..."}, {"value": "...", "label": "..."}], '
        '"cta_headline": "...", "cta_subtext": "...", "cta_button": "two or three words"}'
    ),
    "story": (
        '{"hero_headline": "...", "hero_subtext": "...", "story_heading": "...", '
        '"story_body": "...", "cta_headline": "...", "cta_subtext": "..."}'
    ),
    "poster": ('{"hero_headline": "...", "hero_subtext": "...", "eyebrow": "...", '
               '"cta_button": "two or three words", '
               '"intro_heading": "...", "intro_body": "..."}'),
    "showcase": ('{"hero_headline": "...", "hero_subtext": "...", "eyebrow": "...", '
                 '"intro_heading": "...", "intro_body": "..."}'),
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
              banner_per_page=False, ref_feel="", composition=""):
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
        #  The ground the picture sat on, when it is pale enough to be
        #  one. Read from the same sampling that gave the palette, and
        #  used for the bands -- see `_tint_of`.
        "ground": _ground_from(ref_colours),
        "composition": composition or "",
        #  One direction for every picture in a run. Generating each from
        #  its own section's words is why AI sites look assembled out of
        #  stock: five photographs by five photographers.
        "image_direction": _image_direction(brief, tone),
    }


def _ground_from(colours):
    """The FOURTH colour a picture gives: the ground it all sits on.

    The sampler returns three decided colours and one ground -- the
    quiet, unsaturated colour most of the picture is made of. The
    palette has three roles, so the fourth was collected, shown to the
    owner as a swatch, and then dropped.

    It is the most useful one for a band. Hacker News's cream and a dark
    site's near-black are the whole first impression of those pages, and
    neither can be derived from the primary: `tint_shade_ramp` only ever
    returns tints OF the brand colour, so a warm brand always gets a
    warm-pink band whatever the site it was read from actually looked
    like.

    Taken only when it is pale enough to carry ordinary dark text.
    Nothing here knows what colour the words on that band will be, so a
    dark ground would be a band of black with black text on it -- and
    the honest answer to "can I use this" is no rather than a guess at
    the text colour.
    """
    for colour in reversed(list(colours or [])):
        if not (isinstance(colour, str) and re.match(r"^#[0-9a-fA-F]{6}$", colour)):
            continue
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        #  Rec. 709 luma, the same weighting `readable_on` uses.
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        #  PALE enough to carry dark text, or DARK enough to carry light
        #  text. It was only the first, so a black site sampled its
        #  three brand colours, threw away the black, and came back
        #  white -- which is not what anybody pointing at a dark site
        #  is asking for.
        if luma >= 232 or luma <= 46:
            return colour
    return ""


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
            #  The page's OWN slug, so a rewrite lands back on the page
            #  it was read from rather than creating a second one beside
            #  it. The front page answers to "home", which is the name
            #  `_apply_pack_content` looks for.
            "slug_suffix": "home" if page["is_home"] else (page["slug"] or ""),
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
    '"composition": "a key from the list", '
    '"why": "one sentence", '
    #  LAST, and deliberately: a model that runs out of room stops
    #  mid-answer, and `_salvage` keeps whatever it had finished saying.
    #  So the order of these keys is an order of PRIORITY -- the look
    #  survives a truncated reply and the page shapes, which have a
    #  sensible fallback in `layout_for`, are the part that can be lost.
    #  This was the other way round, and a truncated answer cost the
    #  typeface and the composition while carefully preserving a list of
    #  page shapes the code can work out for itself.
    '"pages": [{"title": "...", "shape": "landing|story|poster|showcase|simple"}]}'
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
    from .design import (FONT_PAIRINGS, SHAPE_PRESETS, SHADOW_PRESETS,
                         COMPOSITION_PRESETS)
    wanted = list(pages) or ["Home"]
    chosen = {}
    if kit["brief"]:
        try:
            chosen = _ai_json(db, _prompt_file(
                "prompts/theme_generator_design.j2",
                kit=kit, pages=wanted, schema=DESIGN_SCHEMA,
                fonts=[(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
                shapes=list(SHAPE_PRESETS), shadows=list(SHADOW_PRESETS),
                compositions=list(COMPOSITION_PRESETS.items()),
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
        #  What the page is shaped like. The single biggest difference
        #  between two looks, and until now not a thing anybody chose.
        "composition": (chosen.get("composition")
                        if chosen.get("composition") in COMPOSITION_PRESETS else ""),
        #  Per page, by title, falling back to what the name suggests.
        "pages": [shapes.get(title.strip().lower()) or layout_for(title, i)
                  for i, title in enumerate(wanted)],
        "why": (chosen.get("why") or "").strip(),
        "asked": bool(chosen),
    }


#  Which composition suits a description, when nobody chose one. Read as
#  a set of rules somebody could argue with rather than a hash of the
#  brief: a shop with a catalogue wants to show a lot at once, a
#  portfolio wants to get out of the way of the work, and a place with
#  one thing to say and a photograph to say it with wants the poster.
_COMPOSITION_WORDS = (
    ("bold", ("bold", "loud", "striking", "dramatic", "energetic", "vibrant",
              "club", "band", "gig", "festival", "bar", "nightlife")),
    ("compact", ("shop", "store", "catalogue", "catalog", "menu", "listing",
                 "products", "stock", "range", "timetable", "schedule")),
    ("quiet", ("calm", "quiet", "gentle", "serene", "minimal", "understated",
               "wellness", "therapy", "clinic", "portfolio", "photography")),
    ("editorial", ("warm", "modern", "clean", "confident", "story", "writing",
                   "studio", "craft", "music", "jazz")),
)


def _composition_from(kit):
    """A composition worked out from the words we already have."""
    said = " ".join(str(kit.get(k) or "") for k in
                    ("ref_feel", "brief", "tone_label")).lower()
    for key, words in _COMPOSITION_WORDS:
        if any(word in said for word in words):
            return key
    #  Anything rather than "classic": classic is the even, unshaped one,
    #  and arriving there by default is how every generated site came to
    #  look the same.
    return "editorial"


def with_design(kit, look):
    """The kit, with anything the owner did not choose filled in by the
    design. What somebody picked themselves always wins."""
    made = dict(kit)
    if not made.get("palette") and look.get("colours"):
        made["palette"] = _palette_from(look["colours"])
    for key in ("fonts", "shape", "shadow", "composition"):
        made[key] = made.get(key) or look.get(key) or ""
    #  Never left empty.
    #
    #  An unanswered composition is not a neutral outcome: it is the flat
    #  one. The model skips the key often enough -- it is the newest
    #  thing in the schema and the first casualty of a short reply -- and
    #  every time it did, the run produced the same evenly-spaced page
    #  this whole feature exists to stop producing.
    #
    #  So it is worked out from what we already know about the site,
    #  which is a guess, and shown in the plan, which is what makes a
    #  guess honest.
    made["composition"] = made["composition"] or _composition_from(made)
    return made


# ---------------------------------------------------------- the plan
#
#  What a run WILL do, worked out before it does any of it. A generator
#  that spends real money and minutes on a misunderstanding, and only
#  says so afterwards, gets used once.


#  What the plan SAYS each shape will make, in the owner's words. It has
#  to name every shape the generator can pick, or a plan for one of them
#  raises rather than describing itself -- which is what a private list
#  beside a shared one does the first time the shared one grows.
SECTION_NAMES = {
    "landing": ["a banner across the top", "a short introduction",
                "some numbers", "three cards side by side",
                "a quote", "a closing call to action"],
    "story": ["a banner across the top", "the story, as running text",
              "a closing call to action"],
    "poster": ["a tall picture with a few words on it",
               "one block of writing"],
    "showcase": ["a banner across the top", "a short introduction",
                 "a row of pictures to look through"],
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
            "composition": kit.get("composition") or "",
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
    #  ONE retry, and only here.
    #
    #  A self-hosted model asked for structured content returns nothing
    #  at all often enough that a six-request run would routinely end
    #  with a template full of "Your headline" and "Feature 1" -- and
    #  the same model, asked again a second later, answers properly.
    #  This app's rule against automatic retries is about SENDS, where a
    #  retry can mail forty people twice; asking a question again costs
    #  one request and nothing else.
    #
    #  Once. A model that has nothing to say twice is telling you
    #  something, and a loop here would spend an owner's evening.
    result, last = None, None
    for attempt in (1, 2):
        try:
            result = assistant._call_provider(
                db, [{"role": "user", "content": prompt}], [], want_json=True)
        except assistant.ProviderError as e:
            last = ThemeGenError("The AI provider did not answer: %s" % e)
            result = None
        if result and (result.get("content") or "").strip():
            break
    if result is None:
        raise last or ThemeGenError("The AI provider did not answer.")
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
        salvaged = _salvage(content)
        if salvaged:
            return salvaged
        raise ThemeGenError(
            "The AI didn't return usable content (%s). Try again, or "
            "simplify the brief." % e)


def _salvage(content):
    """What can still be read out of an answer that stopped early.

    A model that runs out of room mid-answer has usually already said
    most of it: the colours, the typeface and the shape are decided in
    the first few keys, and what is missing is the tail. Every caller
    here already checks each value against the list it came from and
    falls back when one is absent -- so the difference between a
    truncated answer and a whole one is a couple of defaults, while the
    difference between a truncated answer and an ERROR is the whole run.

    Only closes what is open; never invents a value. If nothing parses,
    the caller still raises.
    """
    start = content.find("{")
    if start < 0:
        return None
    text = content[start:]
    #  Drop a half-written trailing token, then close what is still open.
    for cut in range(len(text), max(len(text) - 4000, 0), -1):
        head = text[:cut].rstrip().rstrip(",")
        opens, in_string, escaped = [], False, False
        for ch in head:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "[{":
                opens.append(ch)
            elif ch in "]}" and opens:
                opens.pop()
        if in_string or head.endswith(":"):
            continue
        try:
            found = json.loads(head + "".join("]" if o == "[" else "}"
                                              for o in reversed(opens)))
        except (ValueError, TypeError):
            continue
        if not isinstance(found, dict) or not found:
            return None
        #  A key that was half-written closes as an empty husk. It is
        #  not a value the model gave, so it does not travel.
        return {k: ([item for item in v if item] if isinstance(v, list) else v)
                for k, v in found.items()}
    return None


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
    #  Asked twice, like the words are.
    #
    #  A diffusion backend that is busy refuses or times out, and the
    #  same request a minute later succeeds -- and the difference to the
    #  owner is a front page with a photograph or a front page with a
    #  flat colour where the photograph should be. One retry, never a
    #  loop.
    image_bytes = None
    for attempt in (1, 2):
        try:
            if not ai_image.is_configured(db):
                return PLACEHOLDER_IMAGE
            image_bytes = ai_image.generate_image(db, prompt, width=1600, height=600)
            break
        except Exception:                                     # noqa: BLE001
            image_bytes = None
    if not image_bytes:
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


def _hero_chunk(headline, subtext, image_url, eyebrow="", buttons=(), ground=""):
    #  Escaped, because these are WORDS somebody (or a model) wrote, not
    #  markup. A stray "<" in a headline is a headline, not a tag.
    #
    #  An eyebrow and two buttons, because a hero that says "book me" and
    #  offers nothing to press is a poster, not a front page -- and there
    #  was not one button anywhere on a generated site. Both are ordinary
    #  content inside the Banner tool: an owner edits them in the same
    #  place they edit the headline, and can delete either.
    inside = ""
    if eyebrow:
        inside += '<span class="cms-eyebrow">%s</span>' % escape(eyebrow)
    inside += "<h2>%s</h2><p>%s</p>" % (escape(headline), escape(subtext))
    if buttons:
        inside += '<p class="cms-hero-actions">%s</p>' % "".join(
            '<a class="cms-btn%s" href="%s">%s</a>'
            % ("" if i == 0 else " cms-btn-ghost", escape(link, quote=True), escape(label))
            for i, (label, link) in enumerate(buttons))
    #  No picture? Then a band in the site's own dark, deliberately --
    #  not the grey placeholder.
    #
    #  Image generation fails for ordinary reasons (a slow backend, a
    #  provider that cannot make pictures at all) and the fallback was a
    #  grey mountain-and-sun graphic filling the top of the front page.
    #  That reads as broken; a solid brand-coloured hero reads as a
    #  choice, and the owner can drop a photograph in afterwards from the
    #  Media Library either way.
    if not image_url or image_url == PLACEHOLDER_IMAGE:
        return ('<div class="cms-banner cms-banner-plain" style="background-color:%s">'
                '<div class="cms-banner-overlay">%s</div></div>'
                % (escape(ground or "#241f1f", quote=True), inside))
    return (
        '<div class="cms-banner" style="background-image:url(' + chr(39) + '%s'
        + chr(39) + ')"><div class="cms-banner-overlay">%s</div></div>'
    ) % (escape(image_url, quote=True), inside)


def _text_chunk(heading, body):
    return "<h2>%s</h2><p>%s</p>" % (escape(heading), escape(body))


def _cards_chunk(cards):
    #  Each card ends with a link, pinned to its bottom edge by the
    #  shared stylesheet. Three cards of different lengths with ragged
    #  bottoms and nothing to click is the most recognisable
    #  generated-page tell there is.
    cells = ""
    for card in cards:
        cells += '<div class="cms-card"><h3>%s</h3><p>%s</p>' % (
            escape(card.get("title", "")), escape(card.get("body", "")))
        label, link = card.get("link_label"), card.get("link")
        if label:
            cells += '<a class="cms-card-link" href="%s">%s &rarr;</a>' % (
                escape(link or "#", quote=True), escape(label))
        cells += "</div>"
    return '<div class="cms-columns">%s</div>' % cells



#  Words an image model reliably DRAWS rather than depicts, and the
#  scaffolding of a sentence, which invites it to letter the picture.
_PROMPT_NOISE = re.compile(
    r"(a|an|the|and|or|for|with|to|of|in|on|at|is|are|my|our|your|their|"
    r"place|places|somewhere|website|site|page|business|company|based|"
    r"working|browse|listen|book|booking|get|touch|dates|about|one|person)",
    re.I)


def _picture_prompt(brief, direction):
    """What to ask for, as a SCENE rather than as a sentence.

    The prompt used to be "A wide background photograph for the top of a
    website about: <the whole brief>." -- a paragraph of prose, complete
    with a colon. Measured on a real image backend, the model drew the
    brief across the top of the picture, misspelled, over the photograph
    it had also drawn: "A demo library for a working saxophone player:
    place to browse and listent recordings..." The no-text instruction
    was present and was ignored, which is what an instruction against a
    paragraph of quotable words tends to be.

    So the brief is reduced to the things a camera could point at -- the
    nouns, in order, capped -- and the sentence around them is dropped.
    A picture cannot letter a caption it was never given.
    """
    words = _PROMPT_NOISE.sub(" ", (brief or "").replace(":", " ").replace(",", " "))
    #  Eight words, whole ones. Long enough to name the scene, short
    #  enough that there is no sentence left to letter -- and cutting on
    #  a word boundary rather than a character count, because "sessions
    #  a" is exactly the kind of fragment a model renders literally.
    subject = " ".join([w for w in words.split() if len(w) > 2][:8]).strip()
    return ("Photograph: %s. %s. Wide, no lettering of any kind."
            % (subject or "a small independent business", direction))


#  A copy answer has to carry at least this much to count as one: the
#  headline that goes at the top, or the body of the page. Anything less
#  is a reply, not an answer.
_MEANT_SOMETHING = ("hero_headline", "intro_body", "story_body", "body_text")


def _said_something(copy):
    """Whether a parsed copy answer actually contains words."""
    if not isinstance(copy, dict):
        return False
    return any(str(copy.get(key) or "").strip() for key in _MEANT_SOMETHING)


def _note_unwritten(kit, layout_key, why):
    """Remember that a page came back unwritten, to say so afterwards.

    On the KIT, because that is the one thing every call in a run shares
    -- and because a run that half-worked has to be able to tell the
    owner which half. Silence here would be the worst of both: pages
    that look finished, carrying the placeholder text nobody chose.
    """
    kit.setdefault("unwritten", []).append({"layout": layout_key, "why": why})


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
        try:
            copy = _ai_json(db, _prompt(kit, _SCHEMAS[layout_key]))
            #  An answer that PARSED is not an answer that said anything.
            #
            #  A reply of {} -- or one salvaged down to a key nobody
            #  asked about -- raises nothing, so every `val()` quietly
            #  took its fallback and the page came out reading "Your
            #  headline", "Feature 1", "Describe this feature". A
            #  template that looks finished and says nothing is worse
            #  than one that refuses: the owner has to read it to find
            #  out, and the run cost six requests either way.
            if not _said_something(copy):
                raise ThemeGenError(
                    "The AI answered, but with nothing usable in it.")
        except ThemeGenError as e:
            #  One page's words are not the run.
            #
            #  This raised, and the raise reached the route, and the
            #  route flashed and redirected -- so a model that returned
            #  nothing usable on page four threw away the look, the
            #  picture and the three pages already written, after
            #  several minutes and five requests. The owner saw a red
            #  line and an empty form.
            #
            #  The same reasoning `design()` already applies to itself:
            #  a page that could not be written falls back to its
            #  starting text, which is the same text "leave the sections
            #  empty" produces and is editable in place. What went wrong
            #  is said once, at the end, naming the page.
            copy = {}
            _note_unwritten(kit, layout_key, str(e))

    def val(key, fallback):
        return (copy.get(key) or fallback) if fill else fallback

    tint = _tint_of(kit)
    #  One direction for every picture in a run -- see
    #  brand_kit()["image_direction"].
    hero = _maybe_generate_image(
        db, _picture_prompt(brief or layout_key, kit["image_direction"]),
        use_ai_images and want_image and kit["image_budget"] > 0)

    #  Every piece carries its own STYLING, and a piece may be a real
    #  block tool rather than markup to be classified.
    #
    #  What was here made three shapes -- a banner, a paragraph, a row of
    #  cards -- laid one after another in the same width on the same
    #  white ground, and closed with a second banner over a grey
    #  placeholder. That is the whole reason a generated site came out
    #  flat: not the colours, which were right, but that nothing on the
    #  page ever used them. A page needs a change of ground, something
    #  that is not prose, and a picture that is not a placeholder.
    #
    #  Numbers, a quote and a call to action are the three things every
    #  real template on this install has and this had none of -- and
    #  each is an existing TOOL (services/blocks.py), so the owner can
    #  edit every one of them with the controls they already have.
    chunks = []
    if layout_key == "landing":
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "Your headline"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""),
            #  The second button says what it DOES, and it is not the
            #  same words as the link at the bottom of a card. "Read
            #  more" appearing on a hero button and three cards is one
            #  label meaning two things, which is the fault
            #  design_conventions_check.py exists for.
            buttons=((val("cta_button", "Get in touch"), "/contact"),
                     ("See the work", "#more")), ground=_ink_of(kit)),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        #  Full page width, with the WORDS stopping at the reading
        #  measure. A section set to 62% of the window is centred, which
        #  put its left edge 272px in -- a fourth axis on a page that
        #  already had three. The measure belongs to the text.
        chunks.append(_piece(_text_chunk(val("intro_heading", "Welcome"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
        stats = _rows(copy.get("stats") if fill else None, ("value", "label"), 3,
                      [{"value": "10", "label": "Years"},
                       {"value": "200", "label": "Happy customers"},
                       {"value": "24h", "label": "Reply time"}])
        #  The numbers stand ON the photograph, dimmed, full width.
        #
        #  A section takes a background picture and an overlay -- an
        #  existing feature of every section, and the one thing on this
        #  page that turns a stack of bands into something with a middle.
        #  The overlay is not optional: text over an unmodified
        #  photograph is legible about half the time, which is why the
        #  section tool has always insisted on one.
        #
        #  The same photograph the hero uses. One picture, two jobs, and
        #  a page that looks composed rather than assembled.
        #  On the brand's own ink, not on the hero photograph again.
        #
        #  It WAS the hero photograph, dimmed -- and one picture used
        #  twice on one page is the cheapest-looking move available.
        #  There is one picture in a run, so the honest band is a solid
        #  one in the site's own dark, which also gives the page the
        #  change of ground it needs in the middle.
        chunks.append(_block_piece(
            "stats", _numbered(stats, ("value", "label")),
            #  On the TINT, not on the site's dark.
            #
            #  A Stats block draws each figure in its own pale box, so a
            #  dark band behind it shows through the gaps as three
            #  vertical slots -- which reads as a rendering fault rather
            #  than a design. The band still changes the ground, which is
            #  what it is for; it just does it in the direction the block
            #  was built for.
            {"layout_width": "full", "bg_color": tint}))
        features = _rows(copy.get("features") if fill else None, ("title", "body"), 3,
                         [{"title": "Feature %d" % (i + 1),
                           "body": "Describe this feature."} for i in range(3)])
        #  A card links only if the run gave a label for it. Three
        #  identical "Read more" arrows under three identical cards is
        #  what a page looks like when nobody decided; no link is
        #  quieter, and truer.
        if fill and (copy.get("card_link") or "").strip():
            for card in features:
                card.setdefault("link_label", copy["card_link"].strip())
        chunks.append(_piece(_cards_chunk(features[:6]),
                             {"layout_width": "auto",
                              "shadow_style": kit.get("shadow") or "subtle"}))
        #  A quote, and NO name unless the model supplied one -- and
        #  never a role.
        #
        #  It shipped "A customer" and, worse, whatever the model
        #  invented: "Owner, Kessler & Co" went onto a template that
        #  goes onto somebody's live site as a fabricated review of a
        #  business that does not exist. This app's rule is that the
        #  generator carries no identity and must not invent one; a
        #  made-up attributed quote is the sharpest form of breaking it.
        #  An unattributed quote reads as a specimen, which is what it
        #  is, and the owner fills in a real name.
        chunks.append(_block_piece("testimonial", {
            #  A prompt, never a compliment. An invented one -- "Your
            #  saxophone playing is amazing!" -- ships to a live site as
            #  somebody's testimony about a business that has not opened
            #  yet, which is the same misattribution the invented NAME
            #  was, one layer in.
            "quote": "Add something a customer said about you.",
            "name": "", "role": "", "photo": "",
            "style": "large",
        }, {"layout_width": "full"}))
        #  And it closes on the brand colour, not on a second photograph.
        #
        #  The CTA tool's "solid" tone paints the band in the site's own
        #  primary with text chosen to be readable on it
        #  (`--primary-on`), and puts a button on it. That is a page that
        #  ENDS somewhere. Two hero photographs, one at each end, was the
        #  same idea said twice and the palette still nowhere visible.
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Ready to get started?"),
            "body": val("cta_subtext", "Get in touch today."),
            "button": val("cta_button", "Get in touch"),
            "link": "/contact",
            "tone": "solid",
        }, {"layout_width": "full"}))
        #  NO footer band here.
        #
        #  There was one, and it was wrong twice over. The site already
        #  HAS a footer -- the template's manifest turns it on
        #  (`footer_layout`), it is built from the owner's own details,
        #  and it carries the business name, which a page-level band
        #  never could, because the generator carries no identity. So
        #  the band was a second footer sitting above the real one.
        #
        #  What it contained was worse: three cells of instructions to
        #  the OWNER -- "Add your email address and telephone number
        #  here." -- rendered as live copy to visitors. Placeholder text
        #  that reads as an instruction is not thin content; it is a
        #  page telling the public what its owner has not done yet.
    elif layout_key in ("story", "about"):
        chunks.append(_piece(_hero_chunk(val("hero_headline", "Our story"),
                                         val("hero_subtext", "A short supporting line."),
                                         hero, ground=_ink_of(kit)),
                             {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("story_heading", "About us"),
                                         val("story_body", "Tell your story here.")),
                             {"layout_width": "auto"}))
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Let's talk"),
            "body": val("cta_subtext", "Reach out anytime."),
            "button": val("cta_button", "Get in touch"),
            "link": "/contact",
            "tone": "solid",
        }, {"layout_width": "full"}))
    elif layout_key == "poster":
        #  A tall picture with a few words on it, and one block of
        #  writing. Nothing else -- that is the whole point of the
        #  shape, and it is what an image-led reference asks for: a
        #  page whose subject is the photograph.
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "Your headline"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""),
            buttons=((val("cta_button", "Get in touch"), "/contact"),),
            ground=_ink_of(kit)),
            {"layout_width": "full", "corner_style": "sharp",
             #  Which part of the picture to keep when the band crops it.
             #  A hero's words sit at the bottom left, so the TOP of the
             #  photograph is the half worth keeping -- measured on a
             #  real render, a centred crop put the headline across the
             #  player's face and the standfirst over the brightest
             #  shelf. `bg_position` is the section control that already
             #  says this; the generator simply never set it.
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", "Welcome"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
    elif layout_key == "showcase":
        #  A banner, a line of introduction, and a row of pictures to
        #  look through -- the Accordion tool, which is what this app
        #  already has for "a set of pictures somebody browses".
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "Your headline"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""), ground=_ink_of(kit)),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", "Welcome"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
        from .sections import BLOCK_LIBRARY
        chunks.append({"type": BLOCK_LIBRARY["image-accordion"][0],
                       "content": BLOCK_LIBRARY["image-accordion"][1],
                       "style": {"layout_width": "auto"}})
    else:
        chunks.append(_piece(_hero_chunk(val("hero_headline", "Your headline"),
                                         val("hero_subtext", "A short supporting line."),
                                         hero, ground=_ink_of(kit)),
                             {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("body_heading", "Welcome"),
                                         val("body_text", "Write something here.")),
                             {"layout_width": "auto"}))
    return chunks


def _piece(html, style=None):
    """A chunk of markup to be classified, plus how it should sit."""
    return {"html": html, "style": style or {}}


def _block_piece(key, values, style=None):
    """One of the declared block tools, built by the tool itself.

    Not markup this file invented: `blocks.build` is what the Stats,
    Testimonial and CTA tools use when an admin adds one by hand, so what
    lands on the page is a real block, editable through its own panel,
    with its `data-field` attributes intact. A look nobody can edit
    afterwards is not a look, it is a picture of one.
    """
    from . import blocks
    made = dict(blocks.BLOCKS[key].get("defaults") or {})
    #  A blank is a DECISION; only "not supplied" defers to the default.
    #
    #  Filtering empty strings out here meant the testimonial's own
    #  default attribution -- a full invented name and company -- came
    #  through every deliberate attempt to leave it blank, and shipped a
    #  fabricated review to whoever installed the template.
    made.update({k: v for k, v in values.items() if v is not None})
    #  Type "html", which is how this app stores every declared block.
    #
    #  Not a raw embed, and not a guess: a block section IS an html
    #  section whose markup carries `cms-block-<key>`, and the renderer
    #  recognises it from that class (`is_block` in public.py) to draw it
    #  and to give it its own editing panel. Typed as the block key
    #  instead -- which is what this did -- the section matched no branch
    #  of the render chain at all, so the Stats band, the quote and the
    #  closing call were stored perfectly and drawn as nothing. An empty
    #  dark band where the numbers should be is exactly what that looks
    #  like from the outside.
    return {"type": "html", "content": blocks.build(key, made),
            "style": style or {}}


def _rows(given, keys, least, fallback):
    """`given` if it is a usable list of dicts, otherwise the fallback."""
    if not isinstance(given, list):
        return fallback
    kept = [row for row in given
            if isinstance(row, dict) and any(str(row.get(k) or "").strip() for k in keys)]
    return kept if len(kept) >= least else fallback


def _numbered(rows, keys, prefix="item"):
    """A block tool's flat, numbered field names, from a list of rows."""
    out = {}
    for i, row in enumerate(rows, start=1):
        for key in keys:
            out["%s%d_%s" % (prefix, i, key)] = str(row.get(key) or "").strip()
    return out


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
        #  A piece is either markup to be classified into native
        #  sections, or a block tool that already knows what it is.
        if isinstance(chunk, dict) and chunk.get("type"):
            out.append([chunk["type"], "", chunk["content"], dict(chunk.get("style") or {})])
            continue
        html = chunk["html"] if isinstance(chunk, dict) else chunk
        style = dict(chunk.get("style") or {}) if isinstance(chunk, dict) else {}
        for section in _classify_layout_chunk(html):
            #  Four entries: type, title, content, and the section's own
            #  styling. That fourth slot was written as an empty string
            #  for as long as this existed, which is why every generated
            #  site came out flat: a page of unstyled bands in the
            #  default width, on one white ground, whatever palette it
            #  had been given.
            out.append([section["type"], section.get("title", ""),
                        section["content"], dict(style)])
    return out


def _ink_of(kit):
    """The site's own dark, as a real colour a section can be painted in."""
    from .palette import page_colours
    return (page_colours(kit.get("palette") or [], kit.get("ground") or "")
            .get("--site-ink") or "#241f1f")


def _tint_of(kit):
    """The palest step of the palette's primary, as a real colour.

    Not `var(--primary-50)`: a section's background is stored as a value
    the colour control shows and an owner can change, and a variable name
    there is neither. This is what gives a page a change of ground --
    most of what reads as "designed" on a page of bands, and one
    attribute per section.
    """
    #  The ground the picture actually had, if it gave us one that can
    #  carry dark text. It beats a tint of the brand colour, which is
    #  only ever a paler version of the same hue -- so a site read from a
    #  cream page got a pink band, and the one colour that would have
    #  made it look like the thing it was read from was thrown away.
    from .palette import page_colours
    derived = page_colours(kit.get("palette") or [],
                           kit.get("ground") or "").get("--site-tint")
    if derived:
        return derived
    from .palette import tint_shade_ramp
    primary = ""
    for role in (kit.get("palette") or []):
        if role.get("slug") == "primary" and role.get("color"):
            primary = role["color"]
    if not primary:
        return "#f6f6f6"
    ramp = tint_shade_ramp(primary)
    return ramp.get("lightest") or ramp.get("light") or "#f6f6f6"


def build_package(db, name, pages, palette=None, google_fonts_url=None,
                  shape=None, shadow=None, work_dir=None,
                  nav_layout=None, footer_layout=None, composition=None,
                  ground=None):
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
        #  A LOOK INCLUDES THE WAY ROUND IT.
        #
        #  These three keys are the only thing that makes a template's
        #  header and footer get built when it is activated
        #  (`_apply_default_layout` is the one place that happens, and it
        #  reads exactly these). Without them a generated template
        #  arrived with an empty header zone: five pages, no menu, no way
        #  to reach four of them except by typing the address. Every
        #  shipped template declares them; this one did not, and nothing
        #  said so.
        #
        #  Values from the app's own preset lists, like everything else
        #  the generator picks -- and changeable afterwards from Layout,
        #  which is what makes a default legitimate rather than a
        #  decision taken away.
        "nav_layout": nav_layout or "centered",
        "footer_layout": footer_layout or "simple",
        "page_layout": "none",
        #  Deliberately absent: business_name, tagline, footer_blurb.
        #  A package MAY carry an identity and this one must not invent
        #  one -- the site's name is the site's, and a generator is the
        #  most likely thing in this app to overwrite it by accident.
    }
    if palette:
        manifest["palette"] = palette
    if ground:
        #  The ground the picture sat on. Carried beside the palette
        #  because it is the same kind of thing -- a colour somebody
        #  chose by choosing a picture -- and because a dark site is
        #  a dark site on whoever installs it.
        manifest["ground_color"] = ground
    if google_fonts_url:
        manifest["google_fonts_url"] = google_fonts_url
    #  A shape and a shadow are values the Corners/Depth controls already
    #  carry, and install_theme_package writes them straight onto the
    #  installed row. The generator picks values; it does not write CSS.
    if shape:
        manifest["shape_override"] = shape
    if shadow:
        manifest["shadow_override"] = shadow
    if composition:
        manifest["composition"] = composition
    with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    for i, page in enumerate(pages):
        data = {
            "title": page["title"],
            #  Every page says which page it IS, and the first one says
            #  "home".
            #
            #  This was written empty, and an empty slug is not a page
            #  with no name -- it is a page that matches nothing.
            #  `_apply_pack_content` keys the front page off exactly the
            #  string "home" and every other page off its slug, so a
            #  five-page template activated into a site left four of its
            #  pages unwritten and the fifth landing wherever an empty
            #  slug happened to fall. What arrived was the old site with
            #  a new palette, which is precisely "it does not look like
            #  anything".
            "slug_suffix": page.get("slug_suffix") or ("home" if i == 0
                                                       else _slug(page["title"], "page")),
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
    _carry_media(pkg_dir, slug)
    return pkg_dir, slug


def _carry_media(pkg_dir, slug):
    """Copy the pictures this package refers to INTO it.

    A generated banner is written where every uploaded picture is
    written, and referred to by the URL that serves it -- which is
    correct for the site and wrong for a package, because that URL means
    nothing anywhere else. Exported, the template arrived with a broken
    picture; installed on another site, the same. This is the rule
    CLAUDE.md already states for authored templates -- a template's
    pictures belong to the template -- applied to the one path that was
    not following it.

    The same two steps `packages._build_package_dir` takes when saving a
    live site, and deliberately the same helpers, so a generated package
    and a saved one are the same kind of thing on disk.
    """
    from flask import current_app
    from . import packages
    pages_dir = os.path.join(pkg_dir, "pages")
    if not os.path.isdir(pages_dir):
        return
    paths = [os.path.join(pages_dir, f) for f in sorted(os.listdir(pages_dir))]
    found = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
        for section in spec["sections"]:
            for m in packages.EXPORTABLE_MEDIA.finditer(section[2] or ""):
                #  Named after the template it belongs to, so a file that
                #  is later copied anywhere still says whose it is.
                found.setdefault(m.group(0),
                                 "media/%s-%s" % (slug, os.path.basename(m.group(1))))
    if not found:
        return
    media_dir = os.path.join(pkg_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    carried = {}
    for url, rel in found.items():
        src = packages._static_source_path(current_app.static_folder, url)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(media_dir, os.path.basename(rel)))
            carried[url] = rel
    if not carried:
        return
    for path in paths:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
        for section in spec["sections"]:
            for url, rel in carried.items():
                section[2] = (section[2] or "").replace(url, rel)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)


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
        return "story"
    #  A page whose name is about LOOKING at things gets the shape for
    #  that -- a gallery, a portfolio, a menu of work.
    if any(w in words for w in ("gallery", "portfolio", "work", "photos",
                                "pictures", "space", "rooms", "library")):
        return "showcase"
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

    #  A page that could not be written keeps its starting text and the
    #  owner is told. A run where NOTHING could be written is a different
    #  claim: the AI contributed nothing at all, and handing back a
    #  template full of placeholder prose as though it had worked is the
    #  "absence is not an explanation" failure this app has a rule
    #  about. So the per-page fallback stands, and the whole-run silence
    #  still refuses, in the provider's own words.
    #  THE FRONT PAGE, not just "all of them".
    #
    #  The rule was: refuse only if nothing at all could be written. So a
    #  run where the landing page came back mute and the three small
    #  pages came back fine produced a template whose front page read
    #  "Your headline / A short supporting line. / Feature 1 / Describe
    #  this feature." -- and the owner is looking at that front page
    #  first, in a template list, deciding whether this tool is any good.
    #
    #  A front page of placeholders is worse than no template: it costs
    #  the same wait, and it has to be found and thrown away by hand.
    front_unwritten = any(u.get("layout") in ("landing", "poster", "showcase")
                          for u in (kit.get("unwritten") or []))
    if fill_scope != "none" and pages and (
            front_unwritten
            or len(kit.get("unwritten") or []) >= len(pages)):
        raise ThemeGenError((kit["unwritten"][0]["why"] if kit.get("unwritten") else "")
                            or "The AI returned nothing at all.")

    pkg_dir, slug = build_package(
        db, name, pages,
        palette=kit.get("palette"),
        google_fonts_url=_fonts_url(kit.get("fonts")),
        shape=kit.get("shape"), shadow=kit.get("shadow"),
        composition=kit.get("composition"), ground=kit.get("ground"))
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
