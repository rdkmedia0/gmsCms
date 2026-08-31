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


# ------------------------------------------------- asking the provider


def _prompt(brief, schema):
    """The brief, as the prompt file writes it.

    Rendered through the Jinja environment rather than `render_template`,
    which runs the app's context processors -- and one of those reads the
    session. A service must be callable without a request: from a script,
    from a checker, from the scheduler. Dragging Flask's request context
    into one is the thing CLAUDE.md's service rule exists to prevent, and
    it showed up here as "Working outside of request context" the first
    time this was tested outside a browser.
    """
    template = current_app.jinja_env.get_template("prompts/theme_generator_brief.j2")
    return template.render(brief=brief, schema=schema)


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



def layout_chunks(db, layout_key, brief, fill_scope, use_ai_images):
    """The HTML chunks for one layout. `fill_scope` "none" asks nobody."""
    if layout_key not in LAYOUTS:
        raise ThemeGenError("Unknown layout.")

    fill = fill_scope != "none"
    copy = {}
    if fill:
        if not brief:
            raise ThemeGenError(
                "Describe your site or business, so the AI has something to "
                "write about.")
        copy = _ai_json(db, _prompt(brief, _SCHEMAS[layout_key]))

    def val(key, fallback):
        return (copy.get(key) or fallback) if fill else fallback

    hero = _maybe_generate_image(
        db, "A background image for a website hero banner about: %s"
        % (brief or layout_key), use_ai_images)

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
                  work_dir=None):
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


def generate(db, static_folder, name, layout_key, brief, fill_scope,
             use_ai_images, palette=None, page_title=None):
    """Generate a look, install it as a template, and say which one.

    Installed, NOT activated. That is the whole difference from what this
    did before: it hands back something to look at, keep, throw away or
    export, rather than editing a live page in a way that has to be
    undone by hand.
    """
    from . import packages
    name = (name or "").strip() or "Generated look"
    chunks = layout_chunks(db, layout_key, brief, fill_scope, use_ai_images)
    pages = [{
        "title": (page_title or "Home").strip() or "Home",
        "slug_suffix": "",
        "sections": sections_for(chunks),
    }]
    pkg_dir, slug = build_package(db, name, pages, palette=palette)
    try:
        packages.install_theme_package(
            db, slug, static_folder, pkg_dir_override=pkg_dir, is_builtin=False)
    finally:
        #  The working copy is not the installed one -- install copies it
        #  into static/themes/<slug>/ -- so it goes.
        shutil.rmtree(os.path.dirname(pkg_dir), ignore_errors=True)
    return slug
