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
              image_budget="1"):
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
        "palette": palette or None,
        "fonts": fonts if fonts in FONT_PAIRINGS else "",
        "shape": shape if shape in SHAPE_PRESETS else "",
        "shadow": shadow if shadow in SHADOW_PRESETS else "",
        "image_budget": budget,
        #  One direction for every picture in a run. Generating each from
        #  its own section's words is why AI sites look assembled out of
        #  stock: five photographs by five photographers.
        "image_direction": _image_direction(brief, tone),
    }


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


# ---------------------------------------------------------- the plan
#
#  What a run WILL do, worked out before it does any of it. A generator
#  that spends real money and minutes on a misunderstanding, and only
#  says so afterwards, gets used once.


def plan(kit, layout_key, name, page_title="Home", use_ai_images=True,
         fill_scope="all"):
    """(what it will make, what it will cost) without asking anybody.

    Takes the same answers the run takes, including whether pictures are
    wanted at all -- a plan that promises a photograph the run will not
    make is worse than no plan, and that is exactly what it did before
    the checker caught it: it read the budget and ignored whether the
    provider could make one.
    """
    if layout_key not in LAYOUTS:
        raise ThemeGenError("Unknown layout.")
    sections = {
        "landing": ["a banner across the top",
                    "a short introduction",
                    "three cards side by side",
                    "a closing banner"],
        "about": ["a banner across the top",
                  "the story, as running text",
                  "a closing banner"],
        "simple": ["a banner across the top", "one block of writing"],
    }[layout_key]
    writes = bool(kit["brief"]) and fill_scope != "none"
    #  One picture: the banner at the top. The rest of a layout's banners
    #  take the placeholder, which is a picture the owner replaces from
    #  their own Media Library.
    pictures = 1 if (use_ai_images and kit["image_budget"] > 0) else 0
    banners = len([s for s in sections if "banner" in s])
    return {
        "name": name or "Generated look",
        "layout": LAYOUTS[layout_key]["label"],
        "pages": [{"title": page_title or "Home", "sections": sections}],
        "sections": len(sections),
        "pictures": pictures,
        "placeholders": max(0, banners - pictures),
        #  One call for the words, one per picture. Named rather than
        #  hidden, because it is what the run costs.
        "calls": (1 if writes else 0) + pictures,
        "writes": writes,
        "language": kit["language"],
        "tone": kit["tone_label"],
    }


# ------------------------------------------------- asking the provider


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
    template = current_app.jinja_env.get_template("prompts/theme_generator_brief.j2")
    return template.render(kit=kit, schema=schema)


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



def layout_chunks(db, layout_key, kit, fill_scope, use_ai_images):
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
        use_ai_images and kit["image_budget"] > 0)

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


def generate(db, static_folder, name, layout_key, kit, fill_scope,
             use_ai_images, page_title=None):
    """Generate a look, install it as a template, and say which one.

    Installed, NOT activated. That is the whole difference from what this
    did before: it hands back something to look at, keep, throw away or
    export, rather than editing a live page in a way that has to be
    undone by hand.

    The look the kit asks for travels WITH the package -- its palette,
    its fonts, its shape and shadow -- rather than being written over
    whatever happens to be active. Generating something you have not seen
    yet must not change the site you are looking at.
    """
    from . import packages
    name = (name or "").strip() or "Generated look"
    chunks = layout_chunks(db, layout_key, kit, fill_scope, use_ai_images)
    pages = [{
        "title": (page_title or "Home").strip() or "Home",
        "slug_suffix": "",
        "sections": sections_for(chunks),
    }]
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
