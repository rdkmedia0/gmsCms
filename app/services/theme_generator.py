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
import html as _html
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

#  FOUR WAYS A FRONT PAGE CAN BE ARRANGED, not one.
#
#  Every site this generator made opened the same way -- picture,
#  paragraph, three numbers, three cards, a quote, a closing band --
#  because `layout_for` returned "landing" for page one whatever the
#  business was. Six templates built from the same four sections
#  demonstrate one layout six times, which is the fault the shipped set
#  was rebuilt to avoid, reappearing in the tool that writes new ones.
#
#  Each of these is the SAME vocabulary in a different order, which is
#  the point: an owner can rearrange them afterwards with the controls
#  they already have, because every piece is a tool from the panel.
LAYOUTS["editorial"] = {
    "label": "Editorial",
    "description": ("Words first: a title page with no photograph, a "
                    "story, then a picture. For writing, coaching, "
                    "consulting, a studio -- anywhere the voice is the "
                    "product."),
}
LAYOUTS["catalogue"] = {
    "label": "Catalogue",
    "description": ("What you offer and what it costs, early. Prices, "
                    "then what is included. For a venue, a shop, a "
                    "practice with packages."),
}
LAYOUTS["process"] = {
    "label": "Process",
    "description": ("How working together goes, step by step, then the "
                    "evidence. For trades, clinics, weddings, anything "
                    "booked in advance."),
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
    #  Words first. No stats, no card row: a title, a story in two
    #  parts, a line somebody said, and a quiet close.
    "editorial": (
        '{"hero_headline": "...", "hero_subtext": "...", '
        '"eyebrow": "two or three words above the headline, like a category", '
        '"cta_button": "two or three words, an action", '
        '"intro_heading": "...", "intro_body": "two or three sentences", '
        '"second_heading": "...", "second_body": "two or three sentences", '
        '"picture_caption": "one line to sit over the photograph", '
        '"cta_headline": "...", "cta_subtext": "..."}'
    ),
    #  What it costs, early, because for these businesses that is the
    #  question. Three tiers and what each includes.
    "catalogue": (
        '{"hero_headline": "...", "hero_subtext": "...", '
        '"eyebrow": "two or three words above the headline", '
        '"intro_heading": "...", "intro_body": "two or three sentences", '
        '"tiers": [{"name": "what this option is called", '
        '"price": "a figure, digits only, no currency", '
        '"period": "what the price covers, like per day", '
        '"features": "three or four things included, one per line"}, '
        '{"name": "...", "price": "...", "period": "...", "features": "..."}, '
        '{"name": "...", "price": "...", "period": "...", "features": "..."}], '
        '"tier_cta": "two or three words on each tier button", '
        '"features": [{"title": "...", "body": "..."}, {"title": "...", "body": "..."}, '
        '{"title": "...", "body": "..."}], '
        '"cta_headline": "...", "cta_subtext": "...", "cta_button": "two or three words"}'
    ),
    #  How it goes, in order. The evidence after the explanation.
    "process": (
        '{"hero_headline": "...", "hero_subtext": "...", '
        '"eyebrow": "two or three words above the headline", '
        '"intro_heading": "...", "intro_body": "two or three sentences", '
        '"steps": [{"when": "one or two words, like First or Week one", '
        '"title": "what happens", "text": "one sentence"}, '
        '{"when": "...", "title": "...", "text": "..."}, '
        '{"when": "...", "title": "...", "text": "..."}, '
        '{"when": "...", "title": "...", "text": "..."}], '
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


#  The most content anybody can paste in one go.
#
#  A CV is a page or two; an "everything we do" document can be fifty.
#  The whole of it goes into EVERY page's request, so that one voice
#  reads across the site -- which means a long paste multiplies. Cut with
#  a message rather than discovered as a provider error halfway through a
#  six-minute run.
MAX_SOURCE_CHARS = 20000

def brand_kit(brief="", tone="warm", voice="we", reading="normal",
              language="English", palette=None, fonts="", shape="", shadow="",
              image_budget="1", ref_colours=None, colour_note="",
              banner_per_page=False, ref_feel="", composition="", ref_ink="",
              source_text="", source_layout=None):
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
        #  The owner's own content, when they have some. Capped: the
        #  whole of it goes into EVERY page's request, so one voice
        #  reads across the site -- which means a long paste
        #  multiplies. See MAX_SOURCE_CHARS.
        "source_text": (source_text or "").strip()[:MAX_SOURCE_CHARS],
        #  The document's own columns, when it has them (see documents.
        #  columns_from) -- so the page can be laid out the way the
        #  document is. None for a one-column document; then the ordinary
        #  single-column path renders it.
        "source_layout": source_layout if isinstance(source_layout, dict) else None,
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
        #  The colour the reference was WRITTEN in, when the picture
        #  showed one clearly enough to use. Checked against the
        #  ground before it is believed -- see palette.page_colours.
        "ink": _ink_that_reads(ref_ink, _ground_from(ref_colours), palette),
        "composition": composition or "",
        #  One direction for every picture in a run. Generating each from
        #  its own section's words is why AI sites look assembled out of
        #  stock: five photographs by five photographers.
        "image_direction": _image_direction(brief, tone),
    }


def _ink_that_reads(ink, ground, palette):
    """The sampled ink, or nothing -- decided the way the PAGE decides.

    A template stores the ink it was read with, and the renderer takes
    it only when it reaches 7:1 on the ground. So an ink that can never
    pass was being written down anyway: true of Hacker News' interface
    grey, and of a photograph with no writing in it at all.

    That is worse than storing nothing. The page looked right, because
    the renderer had already thrown the value away -- but the template
    claimed a text colour it does not use, and a later change of ground
    could make the claim come true and repaint the site in it.

    Same threshold, same arithmetic, one place earlier.
    """
    from .palette import contrast, page_colours
    ink = (ink or "").strip()
    if not ink:
        return ""
    on = ground or (page_colours(palette or []) or {}).get("--site-ground") or "#ffffff"
    return ink if contrast(ink, on) >= 7.0 else ""


def _ground_from(colours):
    """The ground the picture sat on. Whatever it is.

    The sampler writes three decided colours and THEN the ground, so
    the ground is the last entry and nothing else -- reading any of the
    first three inverts a site on the strength of its brand colour,
    which is how a workshop photograph with a grey-blue ground came to
    produce a navy page.

    And it is taken as it comes. This used to accept a ground only if it
    was pale enough to carry dark text or dark enough to carry light
    text, and derive one otherwise -- so a picture with a MID ground got
    a default light page, which is the one thing the owner did not ask
    for. They uploaded that picture. If they had wanted a white site
    they would have uploaded a white one.

    Making text readable on it is this app's job, not the owner's, and
    it is arithmetic: see palette.page_colours, which picks the ink by
    measuring against the ground rather than assuming which way round
    the page is.
    """
    for colour in list(colours or [])[-1:]:
        if isinstance(colour, str) and re.match(r"^#[0-9a-fA-F]{6}$", colour):
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


#  LAST RESORT ONLY. These two lists are one author's taste written down,
#  and they help exactly the briefs that happen to contain one of these
#  words. The real path is the design call writing a scene FROM the brief
#  -- it has no list in it and it is where a vague idea gets its
#  specificity added rather than matched. Everything below runs only when
#  that call gave nothing back.
#
#  Words that say what a picture should LOOK like rather than what it is
#  of. When a brief carries any of these the concept is the direction,
#  and the house style has to get out of its way -- "warm natural light,
#  inviting, unstaged" is the opposite of brass machinery under
#  gaslight, and it was appended to every prompt regardless.
#  Words the noun cut let through that are not things a camera can point
#  at. Found in a prompt a real run sent.
FRAGMENT_WORDS = ("that", "which", "but", "and", "with", "from", "into",
                  "encompasses", "encompassing", "including", "specialist",
                  "specialising", "specializing", "focused", "focusing",
                  "based", "style", "styled", "themed", "theme", "site",
                  "website", "page", "pages", "cv", "resume")
_FRAGMENTS = set(FRAGMENT_WORDS)

#  A kind of person. Led with, the image model draws one -- and a
#  generated person on a personal site is a stranger presented as the
#  owner. Set aside from the subject; the scene is made of what they
#  work with, not of them.
PERSON_NOUNS = ("engineer", "engineers", "architect", "architects",
                "designer", "designers", "developer", "developers",
                "consultant", "consultants", "coach", "coaches", "nurse",
                "doctor", "lawyer", "accountant", "photographer", "writer",
                "artist", "teacher", "trainer", "therapist", "plumber",
                "electrician", "builder", "chef", "baker", "barber",
                "stylist", "man", "woman", "person", "people", "team",
                "staff", "founder", "owner", "director", "manager")

STYLE_WORDS = ("steampunk", "vintage", "retro", "noir", "gangster", "art deco",
               "deco", "brutalist", "minimal", "minimalist", "industrial",
               "rustic", "futuristic", "cyberpunk", "gothic", "victorian",
               "mid-century", "scandinavian", "japanese", "tropical", "nautical",
               "neon", "pastel", "monochrome", "brass", "copper", "marble",
               "concrete", "timber", "1920s", "1930s", "1939", "1950s", "1960s",
               "1970s", "1980s", "1990s")


def _image_direction(brief, tone):
    """What every picture in this run should look like.

    The concept first, when the brief has one. This was a house style
    keyed off the TONE alone -- warm meant "natural light, inviting,
    unstaged" -- appended to every picture whatever the brief said, so
    a 1939 steampunk concept was asked for as an inviting, unstaged
    photograph. Style words in a brief are the owner saying what the
    pictures should look like; the tone is the fallback for a brief
    that says nothing about it.
    """
    low = (brief or "").lower()
    styled = [w for w in STYLE_WORDS if w in low]
    if styled:
        return ("in a %s style, staged and art-directed, consistent across "
                "every image in this set; no text, no logos, no watermarks"
                % ", ".join(styled[:4]))
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

#  Languages worth offering, and a way out of the list.
#
#  This was a free-text box, defended on the grounds that "a list would
#  be the languages somebody thought of". True, and it made everyone
#  type -- including the overwhelming majority who want one of these, and
#  who now have to spell it and hope. A list AND a box is the answer to
#  both: pick the common case, type the one nobody thought of.
#
#  Shown in the language's own name first, because somebody looking for
#  German is looking for Deutsch. The value is the English name, which
#  is what goes to the model.
LANGUAGES = (
    ("English", "English"),
    ("Spanish", "Espanol (Spanish)"),
    ("Portuguese", "Portugues (Portuguese)"),
    ("French", "Francais (French)"),
    ("German", "Deutsch (German)"),
    ("Italian", "Italiano (Italian)"),
    ("Dutch", "Nederlands (Dutch)"),
    ("Polish", "Polski (Polish)"),
    ("Czech", "Cestina (Czech)"),
    ("Swedish", "Svenska (Swedish)"),
    ("Danish", "Dansk (Danish)"),
    ("Norwegian", "Norsk (Norwegian)"),
    ("Finnish", "Suomi (Finnish)"),
    ("Greek", "Ellinika (Greek)"),
    ("Turkish", "Turkce (Turkish)"),
    ("Russian", "Russkiy (Russian)"),
    ("Ukrainian", "Ukrayinska (Ukrainian)"),
    ("Arabic", "Arabiyya (Arabic)"),
    ("Hebrew", "Ivrit (Hebrew)"),
    ("Hindi", "Hindi"),
    ("Chinese", "Zhongwen (Chinese)"),
    ("Japanese", "Nihongo (Japanese)"),
    ("Korean", "Hangugeo (Korean)"),
    ("Vietnamese", "Tieng Viet (Vietnamese)"),
    ("Indonesian", "Bahasa Indonesia"),
)

#  The value that means "not on the list", and the reason the box exists.
LANGUAGE_OTHER = "other"


def language_from(chosen, typed):
    """The language to write in, from a list and a box.

    The box wins only when the list was told to stand aside. Anything
    else -- a typed value left over from a previous run, a blank box --
    keeps what was picked, so the two controls cannot disagree about
    what the answer is.
    """
    chosen = (chosen or "").strip()
    typed = (typed or "").strip()
    if chosen == LANGUAGE_OTHER:
        return typed[:40] or "English"
    known = dict(LANGUAGES)
    return chosen if chosen in known else (chosen[:40] or "English")



#  ONE question about words, with four answers. It was two controls both
#  labelled "Words" -- this one, and a second further down the form
#  offering "write them for me" or "leave the sections blank" -- which is
#  the same question asked twice, and two answers that could disagree.
#
#  "Leave them empty" belongs here because it IS a way of deciding where
#  the words come from: from nowhere.
#  WHOSE words, and which words. "My words" meant the pages on THIS
#  SITE right now -- not the template's, which is what it read as, and
#  the difference matters: one is the owner's own writing and the other
#  is demo content that came with a look. Each label names its source.
MODES = (
    ("reskin", "Keep my site's words exactly - change only the look"),
    ("rewrite", "Say my site's words differently - same facts, new voice"),
    ("scratch", "Write new words from the design concept below"),
    ("blank", "Leave every section empty - no AI at all"),
)

#  Which answers need which questions. The form shows only the rows a
#  mode actually uses -- removed, not greyed, which is the rule this app
#  already follows for a schedule's irrelevant fields: a control that is
#  not a choice is not a choice being refused.
MODE_NEEDS = {
    "reskin": (),
    "rewrite": ("voice",),
    #  TWO DIFFERENT THINGS, and they were briefly made into one.
    #
    #  The DESCRIPTION is the guide: what to build, what this site is
    #  for, the concept. It is always the thing directing the run.
    #  CONTENT is optional and is a different axis entirely -- the real
    #  words the owner already has and needs to appear, a CV, a price
    #  list, an about page.
    #
    #  Making content a MODE said they were alternatives -- describe it
    #  OR paste it -- which is wrong in both directions: somebody with
    #  a CV still has to say what kind of site they want, and somebody
    #  describing a business may still have the paragraph they want on
    #  the about page.
    "scratch": ("brief", "source", "pages", "voice"),
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
    #  The pictures, from the same call that decides the look -- one
    #  kit, resolved once, read by every picture in the run. A brief
    #  written as a concept ("1939 gangster steampunk") is answered
    #  here as a SCENE: brass, gaslight, cathode screens.
    '"picture": "the scene every photograph on this site should show, in ten to twenty words: places, objects, light, materials. Never a person.", '
    #  LAST, and deliberately: a model that runs out of room stops
    #  mid-answer, and `_salvage` keeps whatever it had finished saying.
    #  So the order of these keys is an order of PRIORITY -- the look
    #  survives a truncated reply and the page shapes, which have a
    #  sensible fallback in `layout_for`, are the part that can be lost.
    #  This was the other way round, and a truncated answer cost the
    #  typeface and the composition while carefully preserving a list of
    #  page shapes the code can work out for itself.
    #  BUILT from LAYOUTS, not written out here. This said
    #  "landing|story|poster|showcase|simple" -- the set as it stood
    #  before three arrangements were added, so the model was shown a
    #  menu that did not include them while the prose above it described
    #  all four. A private list beside a shared one drifts the first
    #  time the shared one grows, which is the third time this file has
    #  been caught doing it.
    '"pages": [{"title": "...", "shape": "' + "|".join(LAYOUTS) + '"}]}'
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
    #  The list AS GIVEN, which may be empty -- that is the signal that
    #  nobody named the pages and the content should decide. Defaulting
    #  it here hid that signal from the code twenty lines down, so a
    #  four-section CV was treated as a request for one page called
    #  Home. The default belongs after the deciding, not before it.
    asked_for = list(pages or [])
    wanted = asked_for or ["Home"]
    chosen = {}
    if kit["brief"]:
        try:
            chosen = _ai_json(db, _prompt_file(
                "prompts/theme_generator_design.j2",
                kit=kit, pages=wanted, schema=DESIGN_SCHEMA,
                fonts=[(k, v["name"]) for k, v in FONT_PAIRINGS.items()],
                shapes=list(SHAPE_PRESETS), shadows=list(SHADOW_PRESETS),
                compositions=list(COMPOSITION_PRESETS.items()),
                layouts=[(k, v["description"]) for k, v in LAYOUTS.items()]))
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

    #  WHOSE PAGES. Normally the owner's list; in the mode where they
    #  paste their content and name no pages, the model's -- deciding
    #  what pages the content needs is most of what "arrange it for me"
    #  asks for. Titles are taken only when there were none, so a list
    #  somebody typed is never quietly replaced.
    titles = list(asked_for)
    if not titles:
        titles = [str(e.get("title", "")).strip()
                  for e in (chosen.get("pages") or [])
                  if isinstance(e, dict) and str(e.get("title", "")).strip()]
        titles = page_list(chr(10).join(titles))
        #  ...and if it proposed none, the CONTENT'S OWN HEADINGS.
        #
        #  A real CV uploaded through this mode came back as a single
        #  page, because the design call had timed out and there was
        #  nothing left to fall back to -- after the screen had said
        #  the pages would be worked out from the content.
        #
        #  They can be, without asking anybody: a document that has
        #  been written for people already has its sections marked.
        #  Experience, Qualifications, How I work, Contact -- those
        #  are the pages, and the person who wrote them decided that,
        #  which is a better answer than a model's guess and free.
        #  A LONE FRONT PAGE IS THE GENERIC ANSWER, and it loses to
        #  evidence, the same way a "landing" shape does. Asked what
        #  pages a five-section CV needs, the model answered with one:
        #  Home. The document says otherwise -- Experience,
        #  Qualifications, How I work, Contact are written in it, by
        #  the person whose CV it is.
        #
        #  So the headings win when the model proposed nothing, and
        #  when it proposed only a front page. Two or more titles is a
        #  real answer and is kept.
        #  THE DOCUMENT'S OWN HEADINGS ARE ITS PAGES, whenever content
        #  was given and no pages were typed. The model may propose
        #  titles, but a document already has a structure and the
        #  person who wrote it decided it; a proposal that renames the
        #  sections is a proposal that loses them, because the content
        #  is placed by heading.
        if kit.get("source_text"):
            found = headings_in(kit["source_text"])
            if len(found) > 1:
                titles = found
        if len(titles) <= 1:
            titles = headings_in(kit.get("source_text", "")) or titles
        titles = titles or ["Home"]

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
        "pages": [_front_shape(shapes.get(title.strip().lower()), title, i,
                               _signal_text(kit))
                  for i, title in enumerate(titles)],
        "page_titles": titles,
        "why": (chosen.get("why") or "").strip(),
        "picture": (chosen.get("picture") or "").strip()[:240],
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
    #  The scene the design call wrote goes in FRONT of the direction,
    #  so every picture in the run is asked for as that scene in that
    #  style. The house style is what happens when nobody said.
    if look.get("picture") and not str(made.get("image_direction", "")).startswith("SCENE:"):
        made["image_direction"] = "SCENE:%s|%s" % (look["picture"], made.get("image_direction", ""))
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
    #  Said in the same plain words as the rest: what the owner will see
    #  on the page, in the order they will see it. "Looking is free" --
    #  this is the whole of what a plan can promise before a single
    #  provider call is made.
    "editorial": ["a title across the top, no photograph",
                  "the opening, as running text",
                  "a picture band with one line on it",
                  "the rest of the story",
                  "a quote", "a quiet closing call to action"],
    "catalogue": ["a banner across the top", "a short introduction",
                  "your prices, in three options",
                  "three cards side by side",
                  "a closing call to action"],
    "process": ["a banner across the top", "a short introduction",
                "the steps of working together, in order",
                "some numbers", "a quote", "a closing call to action"],
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

    #  THE PAGES THE RUN WILL ACTUALLY MAKE. This defaulted to Home when
    #  nobody typed a list, so the plan promised one page and one picture
    #  to somebody who had attached a five-section CV -- and then the run
    #  made five. What the plan shows must be what gets made, or the
    #  plan is a guess with a Make button under it.
    wanted = list(pages_wanted or [])
    if not wanted:
        wanted = list((looked or {}).get("page_titles") or [])
    if len(wanted) <= 1:
        wanted = headings_in(kit.get("source_text", "")) if kit.get("source_text") else wanted
    wanted = wanted or ["Home"]
    #  A DOCUMENT IS ONE PAGE, rendered whole and in order -- so the plan
    #  shows one page, which is what generate() will make. (The headings
    #  still structure that page; they are just not separate pages.)
    if kit.get("source_text") and not pages_wanted:
        wanted = [wanted[0]]
    #  The look is decided HERE, not when the run starts, so what the
    #  plan shows is what gets made -- and so the owner can look at the
    #  colours and the shapes before anything is written. `looked` is
    #  handed back to `generate` for exactly that reason.
    keys = [k for k in (looked or {}).get("pages") or []]
    if len(keys) != len(wanted):
        keys = [layout_for(title, i, _signal_text(kit))
                for i, title in enumerate(wanted)]

    writes = bool(kit["brief"]) and fill_scope != "none"
    per_page = kit.get("banner_per_page", False)
    #  A COUNT, which it never was. `image_budget` was read as a gate
    #  -- greater than zero, make one picture -- so "Up to three" and
    #  "One, for the top of the page" did exactly the same thing, and
    #  the plan said one picture to somebody who had just asked for
    #  three. A control whose value is only ever tested against zero is
    #  a control that lies about what it offers.
    pictures = 0
    if use_ai_images and kit["image_budget"] > 0:
        pictures = min(len(wanted) if per_page else kit["image_budget"],
                       len(wanted))
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




def _prompt(kit, schema, page_title=""):
    """The brand kit, as the prompt file writes it.

    Rendered through the Jinja environment rather than `render_template`,
    which runs the app's context processors -- and one of those reads the
    session. A service must be callable without a request: from a script,
    from a checker, from the scheduler. Dragging Flask's request context
    into one is the thing CLAUDE.md's service rule exists to prevent, and
    it showed up here as "Working outside of request context" the first
    time this was tested outside a browser.
    """
    #  Two prompts, and the rule in them is the exact inverse. Writing
    #  from a description must invent NO facts; placing content the owner
    #  gave must invent no facts either, but for the opposite reason --
    #  it has them, and every one it adds is one they never wrote.
    if (kit.get("source_text") or "").strip():
        return _prompt_file("prompts/theme_generator_place.j2", kit=kit,
                            schema=schema, page_title=page_title or "this page")
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
                #  A generation call, not a chat one: nobody is watching a
                #  cursor, the screen already says "Generating ... 240s",
                #  and a self-hosted model writing structured JSON needs
                #  longer than a minute. See assistant.GENERATE_TIMEOUT.
                db, [{"role": "user", "content": prompt}], [], want_json=True,
                timeout=assistant.GENERATE_TIMEOUT)
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
    #  MAKING the picture is allowed to fail, and did not take the run
    #  with it. SAVING it was not, and did: an uploads directory the
    #  process could not write to raised PermissionError out of here,
    #  through generate(), to the route -- a 500 after six minutes and
    #  five provider calls, with the words, the palette and the picture
    #  all already paid for and nothing kept.
    #
    #  The docstring above already says what should happen: "a look that
    #  arrives without its photograph is still a look". A disk that
    #  refuses is the same outcome as a backend that refuses, and gets
    #  the same answer.
    try:
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        with open(os.path.join(current_app.config["UPLOAD_FOLDER"],
                               unique_name), "wb") as f:
            f.write(image_bytes)
    except OSError:
        return PLACEHOLDER_IMAGE
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


#  A PORTRAIT, when the site is a person rather than a business.
#
#  The shape a CV asks for -- a round photograph overlapping the band
#  -- and the generator can tell when it is wanted: a career history
#  speaks as one person and reads as a chronology. It is the Banner's
#  own option (services/sections.BANNER_PORTRAITS), so what it produces
#  is a banner the owner goes on editing with the controls already on
#  it.
#
#  IT LEAVES THE PICTURE EMPTY, deliberately. This generator carries no
#  identity and must not invent one, and a synthetic face on somebody's
#  CV is the sharpest form of breaking that -- a stranger's face
#  presented as theirs. The slot is made and the page is styled around
#  it; the photograph is one click on a control that is already there.
PORTRAIT_WORDS = ("cv", "resume", "curriculum", "vitae", "profile",
                  "portfolio", "freelance", "freelancer")

#  A CAREER history, which is not the same as a trade. The Process
#  shape is chosen by both -- a bicycle workshop and a CV are each a
#  series of things in order -- but only one of them is a person's own
#  history, and a headshot over "I repair and install boilers" is not
#  the same page as one over "Clinical lead, 2019 to 2024".
CAREER_WORDS = ("cv", "resume", "curriculum", "vitae", "career",
                "employment", "employed", "experience", "qualification",
                "qualifications", "qualified", "education", "graduated",
                "references", "referees")


def wants_portrait(kit):
    """Whether a front page should carry a portrait slot.

    Two ways to be sure, and both need the site to be ONE PERSON: the
    words say so outright (a CV, a profile), or the site speaks as
    "I" and the content is a career history -- the same evidence that
    puts the front page on the Process shape.

    A business speaking as "we" gets none of this, however many people
    work there: a round headshot over a company's banner is a
    different page altogether.
    """
    words = set(re.findall(r"[a-z]+", _signal_text(kit).lower()))
    if words & set(PORTRAIT_WORDS):
        return True
    if (kit or {}).get("voice") != "i":
        return False
    return bool(words & set(CAREER_WORDS))


def _hero_chunk(headline, subtext, image_url, eyebrow="", buttons=(), ground="",
                portrait=""):
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
    #
    #  AND IT SAYS WHAT COLOUR THE WORDS ON IT ARE. `.cms-banner-overlay`
    #  is `color: #fff`, which is right over a photograph -- every one
    #  gets a dark scrim -- and wrong the moment the band is a flat
    #  colour that might be pale. The band here is painted in the page's
    #  INK, which on a dark site is CREAM: measured on three subpages of
    #  one generated template, white words on a cream slab.
    #
    #  A surface that paints its own background states its own ink, and
    #  this is the only place that knows the band's colour.
    #  The portrait, when one belongs: the Banner tool's own classes
    #  and its own empty figure, so what arrives is a banner the owner
    #  edits with the controls already on it. EMPTY, because a face is
    #  an identity and this generator invents none.
    face, slot = "", ""
    if portrait:
        from .sections import BANNER_PORTRAITS, BANNER_PORTRAIT_SIZES
        where = portrait if portrait in BANNER_PORTRAITS[1:] else "left"
        #  A short headline leaves room for a big portrait; a long one
        #  does not, and the two would collide on a narrow band.
        big = "large" if len(headline or "") < 40 else "medium"
        big = big if big in BANNER_PORTRAIT_SIZES else "medium"
        #  A generated CV portrait is round -- the profile default --
        #  and the owner can change it on the Banner panel afterwards.
        face = (" cms-has-portrait cms-has-portrait-%s"
                " cms-portrait-size-%s cms-portrait-shape-round") % (where, big)
        slot = ('<figure class="cms-banner-portrait cms-banner-portrait-empty">'
                '<span class="cms-banner-portrait-hint">Choose a picture</span>'
                '</figure>')
    if not image_url or image_url == PLACEHOLDER_IMAGE:
        from .palette import readable_on
        band = ground or "#241f1f"
        return ('<div class="cms-banner cms-banner-plain%s" '
                'style="background-color:%s;color:%s">%s'
                '<div class="cms-banner-overlay" style="color:inherit">%s</div></div>'
                % (face, escape(band, quote=True), escape(readable_on(band), quote=True), slot, inside))
    return (
        '<div class="cms-banner%s" style="background-image:url(' + chr(39) + '%s'
        + chr(39) + ')">%s<div class="cms-banner-overlay">%s</div></div>'
    ) % (face, escape(image_url, quote=True), slot, inside)


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
    #  Lookarounds rather than a word-boundary escape. The pattern is a
    #  list of whole words and needs its edges, and this file has already
    #  carried a LOST escape once -- the boundary arrived as a literal
    #  control character, so the rule asked for something no brief
    #  contains and stripped nothing at all, silently, for as long as
    #  nobody read the prompt it produced. `email_layout_check.py` is
    #  what found it; a pattern with no escape in it cannot be broken
    #  that way in the first place.
    r"(?<![A-Za-z])(a|an|the|and|or|for|with|to|of|in|on|at|is|are|my|our|"
    r"your|their|place|places|somewhere|website|site|page|business|company|"
    r"based|working|browse|listen|book|booking|get|touch|dates|about|one|"
    r"person)(?![A-Za-z])",
    re.I)


def _picture_prompt(brief, direction, people=True):
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
    #  A SCENE THE DESIGN CALL WROTE, when there is one: the concept
    #  turned into things a camera can point at, by the one call that
    #  read the whole brief. It is why a steampunk CV can get a brass
    #  control room rather than a man at a desk. `direction` carries it
    #  in front of the house style when the kit has it.
    if direction and direction.startswith("SCENE:"):
        scene, _, rest = direction[6:].partition("|")
        return ("Photograph: %s. %s Wide, no lettering of any kind.%s"
                % (scene.strip(), rest.strip(),
                   "" if people else " No people, no faces, no figures."))
    #  THE FALLBACK, when the design call gave no scene. Rebuilt from the
    #  prompt a real run sent:
    #
    #    "Photograph: that encompasses Reliability Engineering Automation
    #     Observability specialist but."
    #
    #  Three faults in one line. The noun cut kept sentence fragments
    #  ("that", "but") the noise list did not know; the STYLE words were
    #  past the eight-word cap and fell off, so a steampunk brief carried
    #  no steampunk; and what survived led with the occupation, which is
    #  a person, so a person was drawn. And with no brief at all the
    #  subject was the layout key -- "Photograph: process." -- five
    #  times over.
    #
    #  So: style words first, always, however long the brief; then the
    #  things a camera can point at, with anything that is a kind of
    #  person set aside; and never the layout key.
    crowd = "" if people else " No people, no faces, no figures."
    low = (brief or "").lower()
    styled = [w for w in STYLE_WORDS if w in low]
    cleaned = _PROMPT_NOISE.sub(" ", (brief or "").replace(":", " ").replace(",", " "))
    kept = []
    for w in cleaned.split():
        bare = w.strip(".;!?()" + chr(39) + chr(34)).lower()
        if len(bare) <= 2 or bare in _FRAGMENTS or bare in PERSON_NOUNS:
            continue
        if bare in styled:
            continue
        kept.append(bare)
    subject = " ".join(styled[:4] + kept[:6]).strip()
    if not subject:
        subject = "a small independent business"
    return ("Photograph: %s. %s. Wide, no lettering of any kind.%s"
            % (subject, direction, crowd))


#  A copy answer has to carry at least this much to count as one: the
#  headline that goes at the top, or the body of the page. Anything less
#  is a reply, not an answer.
_MEANT_SOMETHING = ("hero_headline", "intro_body", "story_body", "body_text")


def _said_something(copy):
    """Whether a parsed copy answer actually contains words."""
    if not isinstance(copy, dict):
        return False
    return any(str(copy.get(key) or "").strip() for key in _MEANT_SOMETHING)


def _note_unwritten(kit, layout_key, why, page_title=""):
    """Remember that a page came back unwritten, to say so afterwards.

    On the KIT, because that is the one thing every call in a run shares
    -- and because a run that half-worked has to be able to tell the
    owner which half. Silence here would be the worst of both: pages
    that look finished, carrying the placeholder text nobody chose.
    """
    #  WHICH page, not just which shape. The mute-front-page guard
    #  compares against the first page's title, and two pages can
    #  share a shape.
    kit.setdefault("unwritten", []).append(
        {"layout": layout_key, "why": why, "page": page_title})


def _distinctive(text):
    """The tokens a page built from this text would carry: numbers, and
    capitalised words that are not the first word of a sentence."""
    out = set()
    for sentence in re.split(r"[.!?\n]+", text or ""):
        words = sentence.split()
        for n, w in enumerate(words):
            bare = w.strip(",;:()'" + chr(34))
            if not bare:
                continue
            if any(ch.isdigit() for ch in bare):
                out.add(bare.lower())
            elif n > 0 and bare[0].isupper() and len(bare) > 2:
                out.add(bare.lower())
    return out


def _used_the_content(answer, source):
    """Whether a model's answer carries any of the source's own facts.

    A source with fewer than two distinctive tokens cannot be checked
    and is not: a section that says only "Contact me" leaves nothing
    to measure, and refusing an answer for failing a test it could not
    take would be the wrong kind of strict.
    """
    marks = _distinctive(source)
    if len(marks) < 2:
        return True
    said = " ".join(str(v) for v in (answer or {}).values()
                    if isinstance(v, str))
    said += " " + " ".join(
        str(x) for v in (answer or {}).values() if isinstance(v, list)
        for row in v if isinstance(row, dict) for x in row.values())
    return bool(marks & _distinctive(said))


#  A DOCUMENT, PLACED IN FULL.
#
#  The page shapes were written for marketing copy -- a headline, "two
#  or three sentences", three cards -- so a CV's Experience section with
#  three dated roles was squeezed into a paragraph, and the check that
#  the content had been used asked only that SOME fact survive. Neither
#  is what loading content is for. The owner uploaded it so that it is
#  used, all of it, and given a structure.
#
#  So when content is given, the pages are built from the document:
#  its headings are the pages, and every block under a heading becomes
#  the tool that can hold it -- dated lines a timeline, short lines a
#  list, paragraphs paragraphs. All in the owner's own words. The model
#  writes only the connective tissue: a headline, an eyebrow, a closing
#  line. Measured afterwards by content_coverage(), which the run reports
#  and the checker enforces.
_DATED = re.compile(r"^\s*((?:19|20)\d{2}(?:\s*(?:-|to|\u2013|\u2014)\s*(?:(?:19|20)\d{2}|now|present|today))?)\b[\s:\-\u2013\u2014.]*(.*)$", re.I)


#  A date on a CV role line is usually a SPAN -- "2017-2021", "2020 -
#  Present", "Jan 2019 to Mar 2021" -- not a bare year. Pulling only the
#  year out ("2020") and leaving the rest ("(-Present)") in the title
#  read badly AND made the line miss its own coverage check, because the
#  token "2020-Present" was then nowhere on the page. This lifts the
#  whole span, exactly as written, into the when field.
_DATE_SPAN = re.compile(
    r"\(?\b((?:19|20)\d{2})\s*(?:[-–—]|to)\s*"
    r"(present|now|current|(?:19|20)\d{2})\b\)?", re.I)
_ONE_YEAR = re.compile(r"\(?\b((?:19|20)\d{2})\b\)?")


def _when_and_title(line):
    """A dated line split into (when, what) -- the span verbatim, and the
    line with that span lifted out and tidied."""
    m = _DATE_SPAN.search(line)
    if not m:
        m = _ONE_YEAR.search(line)
    if not m:
        return "", line.strip(" ()-–—,.").strip()
    when = m.group(0).strip("()").strip()
    title = (line[:m.start()] + " " + line[m.end():])
    title = re.sub(r"\s{2,}", " ", title).strip(" ()-–—,.·|").strip()
    return when, title


def document_blocks(text):
    """The blocks of one document section, each with the tool it wants.

    Split on blank lines first, because that is how people write
    documents. Then each block is read for what it IS, in this order:

      * lines that are entries in time -- a year somewhere in them, a CV
        role or a study -- become a TIMELINE, with any bullets under an
        entry carried as its text;
      * a run of bullets or short lines with no full stops becomes a
        LIST;
      * anything else stays PARAGRAPHS.

    Nothing is dropped: a block this cannot classify is paragraphs,
    which hold anything, so every line of the document reaches the page.
    """
    year = re.compile(r"(?:19|20)\d{2}")
    out = []
    for raw_block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l.strip() for l in raw_block.split(chr(10)) if l.strip()]
        if not lines:
            continue
        bulletish = [l.lstrip().startswith(("-", "\u2022", "*", "\u2013")) for l in lines]
        has_year = [bool(year.search(l)) for l in lines]

        #  ENTRIES IN TIME. Two or more lines carrying a year -- whether
        #  the year is at the start ("2019 to now") or the end of the
        #  line ("Verde Atelier (2017-2021)"), which is how a CV writes
        #  it -- make this an experience/education section. Each
        #  year-bearing, non-bullet line starts an entry; the bullets
        #  under it are its text. Checked BEFORE the plain list below,
        #  or a dated block of short lines would be flattened to bullets.
        if sum(has_year) >= 2:
            rows, cur = [], None
            for l, yr, bul in zip(lines, has_year, bulletish):
                clean = l.lstrip("-\u2022*\u2013 ").strip()
                if yr and not bul:
                    when, title = _when_and_title(l)
                    cur = [when, title, []]
                    rows.append(cur)
                elif cur is not None:
                    cur[2].append(clean)
                else:
                    rows.append(["", clean, []])
            out.append(("timeline",
                        [(w, (t + (". " + " ".join(x) if x else "")).strip(". "))
                         for w, t, x in rows]))
            continue

        #  A LIST: bullets, or three or more short lines with no full
        #  stop -- a skills or achievements section.
        if len(lines) >= 2 and sum(bulletish) * 2 >= len(lines):
            out.append(("list", [l.lstrip("-\u2022*\u2013 ").strip() for l in lines]))
            continue
        if len(lines) >= 3 and all(len(l) <= 90 and not l.endswith(".") for l in lines):
            out.append(("list", lines))
            continue

        out.append(("paragraphs", [" ".join(lines)] if len(lines) == 1
                    else [l for l in lines]))
    return out


def _doc_hero_bits(text):
    """The name and any intro the document opens with, before its first
    heading. A CV's opening is a name -- often split across boxes ("Keith"
    / "Stevenson") -- and sometimes a line of role under it; those short
    lines are joined into one headline, and anything longer is the intro.
    """
    title, rest = opening_of(text)
    lines = [l.strip() for l in ([title] + rest.split(chr(10))) if l.strip()]
    name_parts, i = [], 0
    while i < len(lines) and i < 3 and len(lines[i].split()) <= 3:
        name_parts.append(lines[i])
        i += 1
    name = " ".join(name_parts) if name_parts else (lines[0] if lines else "")
    intro = chr(10).join(lines[i:]).strip()
    return name, intro


def _first_sentence(text, least=8):
    """The first real sentence in a document -- the hero's subtitle when
    the opening is only a name. Read LINE by line, not by blank-line
    blocks: a boxed CV runs its name straight into its profile with no
    blank between, so a block starts "Keith Stevenson Professional
    Profile ..." and is not a sentence about anything. A line of real
    prose -- eight words or more, not a heading and not a bullet -- is."""
    for line in (text or "").split(chr(10)):
        line = line.strip()
        if (len(line.split()) >= least and not line[:1] in "-•▪‣*·"
                and _looks_like_heading(line, ["x"]) == 0):
            return re.split(r"(?<=[.!?])\s", line)[0][:180]
    return ""


def _render_doc_blocks(blocks):
    """Document blocks (paragraphs / list / timeline) as page chunks.
    One place, so the intro and every section render the same way."""
    out = []
    for kind, rows in blocks:
        if kind == "timeline":
            steps = [{"when": w or "", "title": t.split(". ")[0][:80] if t else w,
                      "text": t} for w, t in rows]
            #  The timeline block holds six entries; a longer run of
            #  roles becomes several timelines rather than crashing on a
            #  seventh or dropping it.
            for start in range(0, len(steps), 6):
                laid = _numbered(steps[start:start + 6],
                                 ("when", "title", "text"), "step")
                laid["style"] = "vertical"
                out.append(_block_piece("timeline", laid,
                                        {"layout_width": "auto"}))
        elif kind == "list":
            items = "".join("<li>%s</li>" % escape(l) for l in rows)
            out.append(_piece("<ul>%s</ul>" % items, {"layout_width": "auto"}))
        else:
            paras = "".join("<p>%s</p>" % escape(x) for x in rows if x)
            if paras:
                out.append(_piece(paras, {"layout_width": "auto"}))
    return out


_SOCIAL_NETS = ("linkedin", "facebook", "instagram", "youtube",
                "tiktok", "pinterest", "github")


def _guess_contact_icon(value):
    """The icon a contact line implies, read from what it says -- so a
    LinkedIn address gets the LinkedIn mark, an email an envelope. The
    same reading the Contacts tool does; "" for a line that is not one."""
    v = (value or "").strip()
    low = v.lower()
    for net in _SOCIAL_NETS:
        if net in low:
            return "brand:" + net
    if "twitter.com" in low or low.startswith("x.com/"):
        return "brand:x"
    if "@" in v and "/" not in v:
        return "✉️"
    if re.match(r"^[\d\s+()./-]{5,}$", v):
        return "\U0001F4DE"
    if low.startswith("http") or ("." in v and " " not in v):
        return "\U0001F310"
    return ""


#  Sections whose content is a set of short labels rather than prose --
#  the ones a person would build with the Tags tool. Read from the
#  heading, so an Awards or Achievements section (real sentences with
#  dates) stays a list and is not forced into pills.
TAG_SECTIONS = frozenset((
    "skills", "competencies", "expertise", "proficiencies", "strengths",
    "technologies", "tools", "specialties", "specialisms", "interests",
    "hobbies", "languages",
))


def _maybe_tags_html(heading, text):
    """A skills/competencies/interests section as a Tags BLOCK -- the same
    tool a person would reach for -- when its heading says it is labels
    and its lines are short. None otherwise, so prose stays prose."""
    words = set(w.strip(":").lower() for w in (heading or "").split())
    if not (words & TAG_SECTIONS):
        return None
    lines = [l.strip().lstrip("-•*– ").strip()
             for l in (text or "").split(chr(10)) if l.strip()]
    lines = [l for l in lines if l]
    if len(lines) < 3:
        return None
    #  Short labels: a few words, no sentence punctuation. A line that
    #  runs on like a sentence means this is not really a tag list.
    if not all(0 < len(l) <= 44 and l[-1] not in ".!?" and len(l.split()) <= 6
               for l in lines):
        return None
    from . import blocks
    values = {}
    for i, label in enumerate(lines[:24], start=1):
        values["tag%d_label" % i] = label
    return blocks.build("tags", values)


def _maybe_contact_html(text):
    """A section that is a list of contact and social lines rendered as a
    Contacts BLOCK -- icons and all -- instead of plain text. It is the
    right tool for the job (phone, email, a LinkedIn address), and the
    only way those items carry their marks. None when the lines are not
    mostly contact details, so a prose section is untouched.
    """
    lines = [l.strip() for l in (text or "").split(chr(10)) if l.strip()]
    if not lines or len(lines) > 12:
        return None
    rows = [{"value": l, "icon": _guess_contact_icon(l), "show": True}
            for l in lines]
    hits = sum(1 for r in rows if r["icon"])
    #  Mostly contact lines, and no more than one stray -- a heading's
    #  worth of prose with an email in it is not a contact block.
    if hits < max(1, int(0.6 * len(lines) + 0.999)) or (len(lines) - hits) > 1:
        return None
    from .sections import build_contact_tool
    return build_contact_tool(rows, layout="column")


def _column_html(coltext):
    """One document column rendered as a single block of HTML -- headings
    and their content, in order -- to drop into a Columns cell. A cell
    holds rich text exactly as a hand-built Columns section does, so this
    is the Text tool's own markup and stays editable.
    """
    out = []

    def blocks_html(text):
        for kind, rows in document_blocks(text):
            if kind == "list":
                out.append("<ul>%s</ul>" % "".join(
                    "<li>%s</li>" % escape(x) for x in rows))
            elif kind == "timeline":
                for when, what in rows:
                    out.append("<p><strong>%s</strong> %s</p>"
                               % (escape(when), escape(what)) if when
                               else "<p>%s</p>" % escape(what))
            else:
                out.append("".join("<p>%s</p>" % escape(x) for x in rows if x))

    #  headings_in treats the FIRST line as the document's own title and
    #  never a heading -- right for the page as a whole (the name), wrong
    #  for a column, whose first line is usually a heading ("Profile",
    #  "Skills"). A blank line in front means the column's real first line
    #  is line two, so its opening heading is found and its section kept.
    coltext = chr(10) + (coltext or "")
    heads = headings_in(coltext)
    for heading in heads[1:]:
        own = section_under(coltext, heading)
        if not own.strip():
            continue
        out.append("<h2>%s</h2>" % escape(heading))
        #  The right tool for the section: a contacts/social list as the
        #  Contacts tool (icons and all); a skills/competencies list as
        #  the Tags tool (pills); everything else as document blocks. All
        #  three are tools a person could have reached for by hand.
        contact = _maybe_contact_html(own)
        tags = None if contact else _maybe_tags_html(heading, own)
        if contact:
            out.append(contact)
        elif tags:
            out.append(tags)
        else:
            blocks_html(own)
    #  A column with no heading of its own still renders -- nothing a
    #  document says is dropped for want of a heading over it.
    if not out:
        blocks_html(coltext)
    return "".join(out)


def _columns_document_chunks(kit, hero_image, val):
    """A document with a column LAYOUT as the page it already is: a
    full-width hero, then one Columns section per band of the document.

    The bands come from the document's own geometry (documents.
    columns_from / _docx_bands), so a two-column body followed by a
    three-column references row comes back as a two-column section then a
    three-column one -- the page reflects the format it was given, built
    from the Banner, Columns and Text tools, nothing new. A band that is
    a single column is a plain section; a band of two or more is a
    Columns section, one cell per column.
    """
    import json as _json
    layout = kit.get("source_layout") or {}
    bands = layout.get("bands")
    if not bands and layout.get("columns"):
        bands = [{"columns": layout["columns"]}]
    bands = [b for b in (bands or []) if (b.get("columns") or [])]
    if not any(len([c for c in (b.get("columns") or []) if (c or "").strip()]) >= 2
               for b in bands):
        return None
    text = kit.get("source_text") or ""
    name, _intro = _doc_hero_bits(text)
    subtitle = _first_sentence(text) or val("hero_subtext", "")
    chunks = [_piece(_hero_chunk(
        name or "Home", subtitle, hero_image,
        eyebrow=val("eyebrow", ""),
        buttons=((val("cta_button", "Get in touch"), "/contact"),),
        ground=_ink_of(kit),
        portrait=("left" if wants_portrait(kit) else "")),
        {"layout_width": "full", "corner_style": "sharp", "bg_position": "center"})]
    for band in bands:
        cells = [_column_html(c) for c in (band.get("columns") or [])
                 if (c or "").strip()]
        cells = [c for c in cells if c.strip()]
        if len(cells) >= 2:
            #  A TWO-column band is a main column beside a narrower one --
            #  a CV's body and sidebar -- so it takes the Columns tool's
            #  "wide-left" width. Three or more (a references row) stay
            #  equal. Both are the real width control, nothing bespoke.
            content = {"columns": cells}
            if len(cells) == 2:
                content["width"] = "wide-left"
            chunks.append({"type": "columns",
                           "content": _json.dumps(content),
                           "style": {"layout_width": "wide"}})
        elif cells:
            #  A one-column band is a plain full-width section, not a
            #  Columns of one.
            chunks.append(_piece(cells[0], {"layout_width": "wide"}))
    return chunks if len(chunks) > 1 else None


def _document_chunks(kit, page_title, is_front, hero_image, val):
    """The WHOLE document as one page, in the order it was written.

    A CV is read top to bottom -- name, profile, experience, education,
    skills, references -- and the person who wrote it chose that order.
    So the front page is the whole document: a hero with the name and
    what they do, the opening intro, then every section under its own
    heading, each rendered as the tool that fits it (dated roles become a
    timeline, a bulleted list becomes a list, prose becomes paragraphs).

    This replaced a page-per-heading split that re-sliced the document by
    reading order and mis-paired it -- "Education" showing a phone number,
    the front page a row of "Panel 1" placeholders. One ordered page
    cannot mis-attribute a section to the wrong page, and never falls
    through to generic filler. Non-front pages return None: a document is
    one page, so there are no others.
    """
    text = kit.get("source_text") or ""
    if not is_front:
        return None
    if not text.strip():
        return None

    #  A document that carries its own columns is laid out as those
    #  columns; one that does not falls through to the single ordered
    #  page below.
    if kit.get("source_layout"):
        columned = _columns_document_chunks(kit, hero_image, val)
        if columned:
            return columned

    name, intro = _doc_hero_bits(text)
    #  The DOCUMENT'S own first sentence is the subtitle -- on a CV that
    #  is the profile line, which says what the person does. The model's
    #  guess is only a fallback: asked for a subtitle it tends to echo
    #  the name ("Stevenson"), and the whole point of loading a document
    #  is that its words win over a guess about them.
    subtitle = _first_sentence(text) or val("hero_subtext", "")
    chunks = [_piece(_hero_chunk(
        name or page_title, subtitle, hero_image,
        eyebrow=val("eyebrow", ""),
        buttons=((val("cta_button", "Get in touch"), "/contact"),),
        ground=_ink_of(kit),
        portrait=("left" if wants_portrait(kit) else "")),
        {"layout_width": "full", "corner_style": "sharp", "bg_position": "center"})]

    #  The opening intro (anything before the first heading that was not
    #  part of the name) as its own words.
    if intro.strip():
        chunks += _render_doc_blocks(document_blocks(intro))

    #  Then each section, in the document's own order, under its heading.
    for heading in headings_in(text)[1:]:
        own = section_under(text, heading)
        if not own.strip():
            continue
        chunks.append(_piece("<h2>%s</h2>" % escape(heading),
                             {"layout_width": "auto"}))
        chunks += _render_doc_blocks(document_blocks(own))
    return chunks


def content_coverage(source, pages):
    """How much of the document reached the site: 0..1 over its lines.

    A line counts when its words appear, in order, somewhere on some
    page -- markup stripped, whitespace squeezed. Lines under four words
    are not counted, because "Contact" and "2013" prove nothing either
    way. This is the number the run reports and the checker enforces:
    the purpose of loading content is that it is used.
    """
    said = " ".join(
        " ".join(re.sub(r"<[^>]+>", " ", sec[2]).split()).lower()
        for pg in (pages or []) for sec in pg.get("sections", []))
    said = _html.unescape(said)
    lines = [" ".join(l.split()).lower() for l in (source or "").split(chr(10))]
    lines = [l for l in lines if len(l.split()) >= 4]
    if not lines:
        return 1.0

    #  A line has REACHED the site when its words have, not when its
    #  exact run of characters has. A dated line becomes a timeline
    #  entry -- "2021 to now" in one field, "Independent practice" in
    #  another -- so the line is on the page and not contiguous, and an
    #  exact-substring test called three roles missing that the same
    #  check had just found by name. Words of four letters or more, and
    #  four in five of them present, is what "on the page" means here.
    def reached(line):
        if line in said:
            return True
        words = [w.strip(".,;:()") for w in line.split()]
        words = [w for w in words if len(w) >= 4]
        if not words:
            return False
        found = sum(1 for w in words if w in said)
        return found >= max(1, int(0.8 * len(words) + 0.999))

    hit = sum(1 for l in lines if reached(l))
    return hit / float(len(lines))



def layout_chunks(db, layout_key, kit, fill_scope, use_ai_images,
                  want_image=True, page_title="", portrait="", is_front=False):
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
        #  Something to work FROM -- a description, or the owner's own
        #  content. This asked for a brief only, which refused the mode
        #  built around pasting content instead of describing a
        #  business: the paste IS the description there, and a run
        #  carrying a full CV was turned away for having nothing to
        #  write about.
        if not (brief or kit.get("source_text")):
            raise ThemeGenError(
                "Describe your site or business, or paste the content you "
                "already have, so the AI has something to work from.")
        try:
            copy = _ai_json(db, _prompt(kit, _SCHEMAS[layout_key], page_title))
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
            _note_unwritten(kit, layout_key, str(e), page_title)

    #  IF THE MODEL SAID NOTHING, THE DOCUMENT STILL HAS.
    #
    #  Asked to fill a page called "Qualifications" from a CV, this
    #  model very often answers with nothing at all -- and five thin
    #  pages answering that way refuses the whole run, after three
    #  minutes, with the owner's content sitting unread in the request.
    #
    #  The document already says what belongs under that word, in the
    #  owner's own wording. It needs no provider, cannot invent a fact,
    #  and beats the alternative outright: the alternative is "Write
    #  your introduction here" on a page called Qualifications, next to
    #  a CV that lists them.
    #  ...AND WHEN IT SAID SOMETHING THAT IGNORED THE CONTENT. A brief
    #  with a strong flavour -- "1939 gangster steampunk" -- came back
    #  as three paragraphs of flavour and not one fact from the CV
    #  attached beside it. The model answered, so nothing was
    #  unwritten, and the owner's content sat in the request unused.
    #
    #  Measured rather than trusted: the distinctive tokens of the
    #  content -- numbers, and capitalised words that are not sentence
    #  starts -- are what a page built FROM it would carry. If the
    #  page carries none of them while its section of the document
    #  has several, the answer did not use the document, and the
    #  document is used instead.
    if fill and copy and kit.get("source_text") and page_title:
        own_now = section_under(kit["source_text"], page_title)
        if not own_now:
            own_now = opening_of(kit["source_text"])[1]
        if own_now and not _used_the_content(copy, own_now):
            copy = {}
            _note_unwritten(kit, layout_key,
                            "The AI wrote around your content rather than from it.",
                            page_title)

    if fill and not copy and kit.get("source_text") and page_title:
        own = section_under(kit["source_text"], page_title)
        #  The FRONT page has no heading of its own -- no document says
        #  "Home" -- so it takes the opening instead: the name, what the
        #  person does, and the sentence or two under it. Without this
        #  the front page was the one page still unwritten, which is
        #  exactly what refuses the whole run.
        head = page_title
        if not own:
            head, own = opening_of(kit["source_text"])
            #  A document that goes straight from its title into its
            #  first heading has an opening with a name and nothing
            #  under it -- and a front page with a headline and no
            #  words is still unwritten, which refuses the run. What
            #  such a document puts FIRST is its most important
            #  section, so that is what the front page says.
            if not own:
                marks = headings_in(kit["source_text"])
                if len(marks) > 1:
                    own = section_under(kit["source_text"], marks[1])
        if own:
            #  Every name the shapes read. A page's arrangement decides
            #  which pair it asks for -- body_heading/body_text on the
            #  simple one, intro_* on a landing, story_* on a story --
            #  and filling only three of them left "Welcome / Write
            #  something here" on the pages that use the fourth, which
            #  is the placeholder text this whole fallback exists to
            #  prevent.
            copy = {"body_heading": head or page_title,
                    "body_text": own,
                    "intro_heading": head or page_title,
                    "intro_body": own,
                    "story_heading": head or page_title,
                    "story_body": own,
                    "hero_headline": head or page_title,
                    "hero_subtext": own.split(chr(10))[0]}
            #  Written after all, just not by the model.
            for note in (kit.get("unwritten") or []):
                if note.get("page") == page_title:
                    kit["unwritten"].remove(note)
                    break

    def val(key, fallback):
        return (copy.get(key) or fallback) if fill else fallback

    tint = _tint_of(kit)
    #  One direction for every picture in a run -- see
    #  brand_kit()["image_direction"].
    hero = _maybe_generate_image(
        db, _picture_prompt(brief or _signal_text(kit), kit["image_direction"],
                            people=not wants_portrait(kit)),
        use_ai_images and want_image and kit["image_budget"] > 0)

    #  THE DOCUMENT FIRST. When the owner gave content, the page is
    #  built from it in full -- see _document_chunks -- and the model
    #  supplies only what a document does not write for itself.
    if kit.get("source_text"):
        built = _document_chunks(kit, page_title, is_front, hero, val)
        if built:
            for note in list(kit.get("unwritten") or []):
                if note.get("page") == page_title:
                    kit["unwritten"].remove(note)
            return built

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
                     ("See the work", "#more")), ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        #  Full page width, with the WORDS stopping at the reading
        #  measure. A section set to 62% of the window is centred, which
        #  put its left edge 272px in -- a fourth axis on a page that
        #  already had three. The measure belongs to the text.
        #  THE PAGE'S OWN NAME, not the word "Welcome".
        #
        #  A model that writes a page's words but no heading for it is
        #  common, and the generic default made a page called "How I
        #  work" open with "Welcome" over the owner's own three steps.
        #  The page already has a name -- the owner or the document
        #  gave it one -- and it is a better heading than any word this
        #  file can supply.
        chunks.append(_piece(_text_chunk(val("intro_heading", page_title or "Welcome"),
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
            "stats", _numbered(stats, ("value", "label"), "stat"),
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
            "name": "", "role": "",
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
            "text": val("cta_subtext", "Get in touch today."),
            "cta": val("cta_button", "Get in touch"),
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
                                         hero, ground=_ink_of(kit), portrait=portrait),
                             {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("story_heading", "About us"),
                                         val("story_body", "Tell your story here.")),
                             {"layout_width": "auto"}))
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Let's talk"),
            "text": val("cta_subtext", "Reach out anytime."),
            "cta": val("cta_button", "Get in touch"),
            "link": "/contact",
            "tone": "solid",
        }, {"layout_width": "full"}))
    elif layout_key == "editorial":
        #  A TITLE PAGE, not a photograph. The band is the site's own
        #  ink, the type is the whole of it, and the picture is held
        #  back until the reader has been given a reason to look.
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "A title"),
            val("hero_subtext", "One line underneath."), "",
            eyebrow=val("eyebrow", ""),
            buttons=((val("cta_button", "Read on"), "#more"),),
            ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", "The short version"),
                                         val("intro_body", "Write the opening here.")),
                             {"layout_width": "auto"}))
        #  Then the picture, full width, with one line over it -- the
        #  section's own background-image and overlay, which is how
        #  every template does a photographic band.
        caption = val("picture_caption", "")
        if hero:
            chunks.append(_piece(
                "<h2>%s</h2>" % escape(caption) if caption else "",
                {"layout_width": "full", "bg_image": hero,
                 "bg_overlay": "dark", "bg_position": "center"}))
        chunks.append(_piece(_text_chunk(val("second_heading", "And then"),
                                         val("second_body", "Carry the story on.")),
                             {"layout_width": "auto"}))
        chunks.append(_block_piece("testimonial", {
            "quote": "Add something a reader or client said.",
            "name": "", "role": "", "style": "large",
        }, {"layout_width": "full", "bg_color": tint}))
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Get in touch"),
            "text": val("cta_subtext", "A line about what happens next."),
            "cta": val("cta_button", "Say hello"),
            "link": "/contact",
            #  Quiet, because this page has been quiet the whole way
            #  down and a solid brand band at the end is a different
            #  document.
            "tone": "outline",
        }, {"layout_width": "auto"}))

    elif layout_key == "catalogue":
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "What we offer"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""),
            buttons=((val("cta_button", "See prices"), "#more"),),
            ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "center"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", "How it works"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
        tiers = _rows(copy.get("tiers") if fill else None,
                      ("name", "price", "period", "features"), 3,
                      [{"name": "Option %d" % (i + 1), "price": "",
                        "period": "", "features": "What is included"}
                       for i in range(3)])[:3]
        priced = _numbered(tiers, ("name", "price", "period", "features"), "tier")
        label = (copy.get("tier_cta") or "").strip() if fill else ""
        for i in range(1, 4):
            priced["tier%d_cta" % i] = label or "Enquire"
            priced["tier%d_link" % i] = "/contact"
        chunks.append(_block_piece("pricing", priced,
                                   {"layout_width": "full", "bg_color": tint}))
        features = _rows(copy.get("features") if fill else None, ("title", "body"), 3,
                         [{"title": "Feature %d" % (i + 1),
                           "body": "Describe this feature."} for i in range(3)])
        chunks.append(_piece(_cards_chunk(features[:6]),
                             {"layout_width": "auto",
                              "shadow_style": kit.get("shadow") or "subtle"}))
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Ready to book?"),
            "text": val("cta_subtext", "Tell us what you need."),
            "cta": val("cta_button", "Get in touch"),
            "link": "/contact", "tone": "solid",
        }, {"layout_width": "full"}))

    elif layout_key == "process":
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "How it goes"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""),
            buttons=((val("cta_button", "Get in touch"), "/contact"),
                     ("How it works", "#more")),
            ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "center"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", "What to expect"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
        steps = _rows(copy.get("steps") if fill else None,
                      ("when", "title", "text"), 3,
                      [{"when": "Step %d" % (i + 1), "title": "What happens",
                        "text": "One sentence."} for i in range(4)])[:3]
        laid = _numbered(steps, ("when", "title", "text"), "step")
        laid["style"] = "vertical"
        chunks.append(_block_piece("timeline", laid, {"layout_width": "auto"}))
        stats = _rows(copy.get("stats") if fill else None, ("value", "label"), 3,
                      [{"value": "10", "label": "Years"},
                       {"value": "200", "label": "Jobs done"},
                       {"value": "24h", "label": "Reply time"}])
        chunks.append(_block_piece(
            "stats", _numbered(stats, ("value", "label"), "stat"),
            {"layout_width": "full", "bg_color": tint}))
        chunks.append(_block_piece("testimonial", {
            "quote": "Add something a customer said about you.",
            "name": "", "role": "", "style": "large",
        }, {"layout_width": "full"}))
        chunks.append(_block_piece("cta", {
            "heading": val("cta_headline", "Ready to start?"),
            "text": val("cta_subtext", "Get in touch and we will talk it through."),
            "cta": val("cta_button", "Get in touch"),
            "link": "/contact", "tone": "solid",
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
            ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp",
             #  Which part of the picture to keep when the band crops it.
             #  A hero's words sit at the bottom left, so the TOP of the
             #  photograph is the half worth keeping -- measured on a
             #  real render, a centred crop put the headline across the
             #  player's face and the standfirst over the brightest
             #  shelf. `bg_position` is the section control that already
             #  says this; the generator simply never set it.
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", page_title or "Welcome"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
    elif layout_key == "showcase":
        #  A banner, a line of introduction, and a row of pictures to
        #  look through -- the Accordion tool, which is what this app
        #  already has for "a set of pictures somebody browses".
        chunks.append(_piece(_hero_chunk(
            val("hero_headline", "Your headline"),
            val("hero_subtext", "A short supporting line."), hero,
            eyebrow=val("eyebrow", ""), ground=_ink_of(kit), portrait=portrait),
            {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("intro_heading", page_title or "Welcome"),
                                         val("intro_body", "Write an introduction here.")),
                             {"layout_width": "auto"}))
        from .sections import BLOCK_LIBRARY
        chunks.append({"type": BLOCK_LIBRARY["image-accordion"][0],
                       "content": BLOCK_LIBRARY["image-accordion"][1],
                       "style": {"layout_width": "auto"}})
    else:
        chunks.append(_piece(_hero_chunk(val("hero_headline", "Your headline"),
                                         val("hero_subtext", "A short supporting line."),
                                         hero, ground=_ink_of(kit), portrait=portrait),
                             {"layout_width": "full", "corner_style": "sharp",
             "bg_position": "top"}))
        chunks.append(_piece(_text_chunk(val("body_heading", page_title or "Welcome"),
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
    #  A FIELD THE BLOCK DOES NOT HAVE IS A MISTAKE, NOT AN EXTRA.
    #
    #  `_numbered` writes `item1_value` unless it is told the tool's own
    #  prefix, and the Stats block reads `stat1_value`. The keys did not
    #  match, `made` kept its defaults, and every site this generator has
    #  ever produced shipped the same three figures -- 12, 400+, 98% --
    #  while the model's real numbers were written, passed in, and
    #  dropped on the floor. Nothing raised and nothing looked wrong.
    #
    #  Loud, because it can only be a coding error: the callers are all
    #  in this file and the checker runs every one of them.
    unknown = [k for k in values if k not in made]
    if unknown:
        raise ThemeGenError(
            "The %s tool has no field called %s." % (key, ", ".join(sorted(unknown))))
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
    """A block tool's flat, numbered field names, from a list of rows.

    A LIST BECOMES LINES, not its own repr. A field like a pricing
    tier's features takes several things one per line, and asking a
    model for "three or four things included, one per line" gets a JSON
    array about as often as it gets a string -- both are reasonable
    readings of the request. `str()` on the array put
    ['Lighting setup', 'Changing room'] on a live pricing card, brackets
    and quotes included.

    Joining is the right answer rather than re-asking: the model gave
    the right facts in a shape the field can hold once it is written
    down properly.
    """
    out = {}
    for i, row in enumerate(rows, start=1):
        for key in keys:
            value = row.get(key)
            if isinstance(value, (list, tuple)):
                value = chr(10).join(
                    str(part).strip() for part in value if str(part).strip())
            out["%s%d_%s" % (prefix, i, key)] = str(value or "").strip()
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
    """The band colour for a hero with no picture: the page, inverted.

    This was called "the site's own dark", which it was while every page
    was a light one. `--site-ink` is now whatever reads on the ground --
    so on a black site it is cream. Painting a band in it is still the
    right idea, because it is the one colour guaranteed to stand apart
    from the page; what was missing is that the words on it have to be
    the other half of that pair. See _hero_chunk.
    """
    from .palette import page_colours
    return (page_colours(kit.get("palette") or [], kit.get("ground") or "",
                         kit.get("ink") or "")
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
    derived = page_colours(kit.get("palette") or [], kit.get("ground") or "",
                           kit.get("ink") or "").get("--site-tint")
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
                  ground=None, ink=None):
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
    if ink:
        manifest["ink_color"] = ink
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


def _signal_text(kit):
    """Everything the owner said about what this site is.

    The brief AND anything they pasted. Scoring the brief alone reads
    one line and ignores the two pages underneath it -- and in the mode
    where they paste their content the brief is optional and usually
    empty, so the shape would have been chosen from nothing at all.
    """
    return " ".join(x for x in ((kit or {}).get("brief"),
                                (kit or {}).get("source_text")) if x)


def _front_shape(said, title, index, brief):
    """The model's answer, unless the model gave the generic one.

    A DEFAULT IS NOT A DECISION. Asked which shape a front page should
    be, this model answers "landing" whatever the business is -- it did
    so for a wedding barn with three package prices, a bicycle workshop
    and a potter, in the same run, after being given all four shapes
    with their descriptions and told explicitly that landing is one of
    four rather than the normal one. Describing the choice better was
    worth doing and did not change the answer.

    So: any shape it names that is NOT the generic one is a real
    choice and wins. "landing" on a front page is indistinguishable
    from not having chosen, and loses to a specific signal in the
    brief -- three package prices means the prices belong on the front
    page, whoever noticed it.

    Every other page is left entirely to the model: there is no
    generic answer to override there.
    """
    if index != 0:
        return said or layout_for(title, index, brief)
    if said and said != "landing":
        return said
    return layout_for(title, index, brief)


#  What a brief SOUNDS like, per front-page shape. Whole words, matched
#  by stem, so "servicing" counts for "servic" and "workshop" does not
#  count for "shop" -- which it did, as a plain substring, and put a
#  bicycle repair workshop in the catalogue instead of the process.
FRONT_SIGNALS = {
    "catalogue": ("price", "prices", "pricing", "package", "packages",
                  "hire", "rent", "rental", "room", "rooms", "menu",
                  "shop", "sell", "sells", "selling", "product",
                  "products", "membership", "rate", "rates"),
    "editorial": ("write", "writer", "writing", "writes", "journal",
                  "essay", "essays", "coach", "coaching", "consult",
                  "consultant", "therapy", "studio", "portfolio",
                  "photograph", "photographer", "design", "designer",
                  "teach", "teaches", "teaching"),
    "process": ("repair", "repairs", "fit", "fitting", "install",
                "service", "services", "servicing", "clinic", "treatment",
                "treatments", "appointment", "appointments", "book",
                "booked", "booking", "wedding", "weddings", "event",
                "events", "build", "building", "renovation", "restoration",
                #  A career history belongs here, not under
                #  "editorial". The words are a person's rather than a
                #  business's, but the SHAPE is the one the trades
                #  need: things in order, with dates on them, which is
                #  what the timeline block is. A CV as prose is a wall;
                #  as a chronology it is the document people already
                #  know how to read.
                "cv", "resume", "curriculum", "vitae", "career",
                "employment", "employed", "experience", "qualification",
                "qualifications", "qualified", "education", "graduated",
                "references", "referees", "registered", "certified"),
}


def layout_for(title, index, brief=""):
    """Which starting arrangement a page called this should get.

    By the name, because the names people give pages mean something: an
    About page wants the story layout and a Contact page wants the small
    one. Guessed rather than asked, and shown in the plan before it runs
    -- a guess somebody can see and change is worth ten they cannot.
    """
    words = (title or "").strip().lower()
    if index == 0:
        #  A FRONT PAGE IS NOT ONE SHAPE.
        #
        #  This returned "landing" for page one of every site ever
        #  generated, so a bakery, a saxophonist and a wedding venue all
        #  opened with a photograph, a paragraph, three numbers, three
        #  cards, a quote and a band -- in that order.
        #
        #  Scored rather than ordered: the first list to match used to
        #  win, which made the answer depend on which shape happened to
        #  be checked first. Counting lets a brief that is mostly about
        #  one thing say so, and a tie means nothing stood out, which is
        #  what "landing" is for.
        found = re.findall(r"[a-z]+", (brief or "").lower())
        scores = {}
        for shape, stems in FRONT_SIGNALS.items():
            scores[shape] = sum(1 for w in found if w in stems)
        best = max(scores, key=lambda k: scores[k])
        top = scores[best]
        if top and list(scores.values()).count(top) == 1:
            return best
        return "landing"
    if any(w in words for w in ("about", "story", "who we are", "team", "us")):
        return "story"
    #  A page whose name is about LOOKING at things gets the shape for
    #  that -- a gallery, a portfolio, a menu of work.
    if any(w in words for w in ("gallery", "portfolio", "work", "photos",
                                "pictures", "space", "rooms", "library")):
        return "showcase"
    return "simple"


def opening_of(text):
    """Everything a document says before its first heading.

    A CV opens with a name, what the person does, and a sentence or two
    about it -- and that is the front page's material, exactly. There is
    no heading called "Home", so section_under finds nothing for the
    front page, which left it the one page still unwritten and refused
    the whole run by the mute-front-page guard.

    The first line is the document's title, so it is offered separately
    from the rest: a headline and the words under it.
    """
    rows = [l.strip() for l in (text or "").split(chr(10))]
    marks = set(h.strip().lower() for h in headings_in(text))
    out = []
    for row in rows:
        if row.lower() in marks and row.lower() != "home":
            break
        out.append(row)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    title = out[0] if out else ""
    rest = chr(10).join(out[1:]).strip()
    return title, rest



def section_under(text, heading):
    """The lines a document keeps under one of its own headings.

    The other half of headings_in. If the model cannot place a page --
    and asked to fill "Qualifications" from a CV it very often answers
    with nothing at all -- the document already says what belongs there,
    in the owner's own words, under that exact word.

    This needs no provider and cannot invent anything, which makes it a
    better failure than the placeholder text the page would otherwise
    keep: "Write your introduction here" on a page called
    Qualifications, next to a CV that lists them.
    """
    want = (heading or "").strip().lower()
    if not want:
        return ""
    rows = [l.strip() for l in (text or "").split(chr(10))]
    marks = set(h.strip().lower() for h in headings_in(text))
    out, taking = [], False
    for row in rows:
        low = row.lower()
        if taking and low in marks and low != want:
            break
        if low == want:
            taking = True
            continue
        if taking:
            out.append(row)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return chr(10).join(out).strip()



#  The section titles a real CV actually uses -- so a heading is found
#  by what it SAYS as well as by how it looks. A person does not write
#  "PROFESSIONAL EXPERIENCE" in the shape of a sentence, and a document
#  exported from Word rarely leaves a blank line above it.
CV_SECTION_WORDS = frozenset((
    "profile", "summary", "about", "objective", "overview", "bio",
    "experience", "employment", "work", "history", "career", "roles",
    "education", "qualifications", "academic", "training", "courses",
    "skills", "expertise", "competencies", "proficiencies", "strengths",
    "projects", "portfolio", "selected", "clients", "work",
    "certifications", "certificates", "licences", "licenses", "accreditations",
    "awards", "achievements", "honours", "honors", "recognition",
    "publications", "talks", "press",
    "references", "referees",
    "contact", "details", "info", "information",
    "interests", "hobbies", "activities", "volunteering", "voluntary",
    "languages", "memberships", "affiliations", "associations",
))


def _clean_heading(line):
    """A heading's own words, without the marks a document decorates it
    with: Markdown hashes, a leading "1." or "2)" number, a trailing
    colon. The page is named for what the section IS, not how it was
    typeset."""
    line = re.sub(r"^#{1,6}\s+", "", line or "")
    line = re.sub(r"^\(?\d{1,2}[.)]\s+", "", line)
    return line.rstrip(":").strip()


def _looks_like_heading(line, following, blank_above=False):
    """Whether one line reads as a section heading of a document.

    A Markdown heading is one outright. Otherwise a heading is a line
    that is NONE of the things a heading never is -- and then one of the
    things a heading is.

    Never a heading: a bullet or dash-led line; a line that ends like a
    sentence or a parenthetical ("Work Permit (C)"); a contact fragment
    (an email, a phone number, a year in brackets); a slash-separated
    pair, which is how a template writes "Qualification / Institution".
    These exclusions are the whole reason a box-built CV stopped turning
    its own phone number and its dates into pages.

    Then a heading IS one of: a known CV section word (Education,
    References, Skills), whole or in a short title ("Work Experience");
    mostly CAPITALS with enough letters to be a word and not initials;
    or -- only when a blank line sits above it -- a short line, which is
    how an unconventional heading ("Where I have worked") is caught.
    Always provided there is something under it to be the heading OF.
    """
    if not line:
        return 0
    #  A Markdown heading is unambiguous and bypasses the shape tests.
    if re.match(r"#{1,6}\s+\S", line):
        return 2
    if len(line) > 48:
        return 0
    if line[0] in "-•▪‣⁃*·∙":
        return 0
    if line[-1] in ".,;:!?)]–—-":
        return 0
    words = line.split()
    if len(words) > 5:
        return 0
    #  Contact fragments and dated content: an email, a phone number, a
    #  year in brackets -- short and title-less, but not sections.
    if "@" in line or sum(c.isdigit() for c in line) >= 4:
        return 0
    #  "A / B" is a content pair a template lays out, not a heading.
    if " / " in line or "://" in line:
        return 0
    if not any(following):
        return 0
    bare = _clean_heading(line)
    low = bare.lower()
    #  STRONG (2): a known CV section word -- whole, or in a short title
    #  ("Work Experience") -- or mostly CAPITALS with enough letters to
    #  be a word and not a monogram ("KS"). A document with several of
    #  these is telling us its own structure, and headings_in trusts it.
    if low in CV_SECTION_WORDS:
        return 2
    if len(words) <= 3 and any(
            w.strip(":").lower() in CV_SECTION_WORDS for w in words):
        return 2
    letters = [c for c in bare if c.isalpha()]
    if len(letters) >= 4 and sum(1 for c in letters if c.isupper()) / len(letters) >= 0.7:
        return 2
    #  WEAK (1): a short line with a blank line above it. This catches an
    #  unconventional heading ("Where I have worked") -- but it also
    #  catches a referee's name, so headings_in leans on these only when
    #  the strong headings are too few to structure the document alone.
    if blank_above and 0 < len(words) <= 4 and len(letters) >= 3:
        return 1
    return 0


def headings_in(text, most=10):
    """The section headings of a document somebody wrote, as page names.

    A document written for people already carries its own structure --
    PROFILE, EXPERIENCE, EDUCATION, REFERENCES -- and the person who
    wrote it decided that. It is a better answer than a model's guess
    about the same document, and it costs nothing.

    What counts as a heading is _looks_like_heading: mostly-capitals, or
    a known CV section word, or a short line with a blank line above it.
    The earlier version demanded that blank line for ALL of them, so a
    CV exported from Word -- which runs a section's last line straight
    into the next title, in capitals -- came back with one heading and
    the whole document crammed onto a single page.

    The first line is never a heading: it is the document's own name.
    "Home" is always first, because the document has no name for its
    front page and every site needs one.
    """
    lines = [l.strip() for l in (text or "").split(chr(10))]
    found = []
    for i, line in enumerate(lines):
        if i == 0:
            continue
        blank_above = (i > 0 and not lines[i - 1])
        strength = _looks_like_heading(line, lines[i + 1:i + 4], blank_above)
        if strength:
            found.append((strength, _clean_heading(line)))
    #  STRONG HEADINGS WIN. A document that marks its sections clearly --
    #  a box-built CV with Education, Experience, References in plain
    #  words -- is not helped by also promoting every short line with a
    #  gap above it, because those are its referees' names and its job
    #  titles. So the weak, blank-line-above headings are kept only when
    #  the strong ones are too few (under three) to structure it alone --
    #  which is exactly the unconventional document that has no section
    #  words at all and needs them.
    strong = [name for s, name in found if s >= 2]
    picked = [name for s, name in found] if len(strong) < 3 else strong
    seen, out = set(), ["Home"]
    for name in picked:
        key = name.lower()
        if key in seen or key == "home" or not key:
            continue
        seen.add(key)
        out.append(name)
    return out[:most]



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
        #  NOT defaulted to Home yet. `design` proposes page titles
        #  when the owner named none -- and defaulting here told it the
        #  owner had asked for exactly one page called Home, so the
        #  proposal and the document's own headings could never be
        #  reached. A CV with four sections came out as one page.
        wanted = list(pages_wanted or [])
        #  What each page should BE, decided from the description rather
        #  than picked by the owner from three named skeletons. `looked`
        #  is passed in when the plan has already worked it out, so the
        #  run does not ask twice and cannot get a different answer than
        #  the one that was shown.
        decided = looked or design(db, kit, wanted)
        wanted = wanted or ["Home"]
        #  ...and if the owner named no pages, the ones it proposed.
        #  Deciding what pages the content needs is most of what
        #  "arrange it for me" is asking for; a list somebody typed is
        #  never replaced, because `titles` only fills when empty.
        if not pages_wanted and decided.get("page_titles"):
            wanted = decided["page_titles"]
        #  A DOCUMENT IS ONE PAGE. When the owner gave content, it is
        #  rendered whole and in order on the front page (see
        #  _document_chunks), so the per-heading pages the design
        #  proposed would each re-render a slice of the same document and
        #  mis-attribute it. The headings still structure that one page;
        #  they are just not separate pages. A page the owner TYPED is
        #  still honoured -- this only overrides the proposal.
        if kit.get("source_text") and not pages_wanted:
            wanted = [wanted[0] if wanted else "Home"]
        chosen = decided.get("pages") or []
        pages = []
        for i, title in enumerate(wanted):
            key = (chosen[i] if i < len(chosen)
                   else layout_for(title, i, _signal_text(kit)))
            #  Pictures are the slow, paid part of a run, so how many
            #  there are is the owner's answer and not a default.
            #  HOW MANY PICTURES, as asked. This gave the first page a
            #  picture and no other page one unless every page was to
            #  have one -- so choosing "up to three" produced exactly
            #  one, and the number in the control meant nothing.
            #
            #  Still never more than one per page, and never more than
            #  the budget: pictures are the slow, paid part of a run,
            #  and the whole point of the control is that the owner
            #  says how many they are willing to wait for.
            wants = (len(wanted) if kit.get("banner_per_page", False)
                     else kit.get("image_budget", 1))
            chunks = layout_chunks(
                db, key, kit, fill_scope, use_ai_images,
                want_image=(i < wants),
                page_title=title,
                #  THE FRONT PAGE ONLY. A portrait on every page of a
                #  CV is a contact sheet.
                portrait=("left" if i == 0 and wants_portrait(kit) else ""),
                is_front=(i == 0))
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
    #  WHICH PAGE, not which shape. This listed three shape names --
    #  landing, poster, showcase -- so a front page in any of the
    #  three arrangements added since could come back as nothing but
    #  placeholder text and ship anyway, which is the exact outcome
    #  this guard exists to prevent. The fourth private list this file
    #  has been caught keeping beside a shared one.
    #
    #  The front page is the FIRST page. That is true whatever shapes
    #  exist, today and after the next one is added.
    #  From `pages`, which exists on every path -- `wanted` is bound
    #  only where the run was given a page list, and reading it here
    #  raised UnboundLocalError on the reskin path.
    front = (pages[0].get("title") if pages else "") or ""
    front_unwritten = any(u.get("page") == front
                          for u in (kit.get("unwritten") or []))
    if fill_scope != "none" and pages and (
            front_unwritten
            or len(kit.get("unwritten") or []) >= len(pages)):
        #  NAME THE PAGES. This said only what went wrong, so a run
        #  that refused told the owner nothing about WHERE -- and left
        #  whoever was debugging it guessing between five pages.
        why = (kit["unwritten"][0]["why"] if kit.get("unwritten") else "")
        named = [u.get("page") or u.get("layout") or "?"
                 for u in (kit.get("unwritten") or [])]
        raise ThemeGenError(
            (why or "The AI returned nothing at all.")
            + (" Nothing came back for: %s." % ", ".join(named) if named else ""))

    #  HOW MUCH OF THE DOCUMENT REACHED THE SITE. Reported, so a run
    #  that used a few lines of a CV says so rather than looking
    #  finished; enforced by the checker at 95% with the provider mute.
    if kit.get("source_text") and fill_scope != "none":
        kit["coverage"] = content_coverage(kit["source_text"], pages)

    pkg_dir, slug = build_package(
        db, name, pages,
        palette=kit.get("palette"),
        google_fonts_url=_fonts_url(kit.get("fonts")),
        shape=kit.get("shape"), shadow=kit.get("shadow"),
        composition=kit.get("composition"), ground=kit.get("ground"),
        ink=kit.get("ink"))
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
