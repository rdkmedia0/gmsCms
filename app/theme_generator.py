"""AI Theme Generator — builds starter page content from a free-text brief,
using the CMS's own tools (Banner/Text/Card) rather than raw HTML, and the
site's existing multi-provider AI layer (see assistant.py) for the copy.

See app/theme_layouts.py for the fixed layout definitions this fills in,
and admin.py's theme_generator route + _insert_layout_chunks for how the
HTML chunks this produces get turned into real, editable sections.
"""
import json
import os
import re
import uuid
from html import escape

from flask import current_app, render_template

from . import assistant, ai_image
from .theme_layouts import LAYOUTS

PLACEHOLDER_IMAGE = "/static/img/placeholder.svg"


class ThemeGenError(Exception):
    pass


def _ai_json(db, prompt):
    try:
        result = assistant._call_provider(db, [{"role": "user", "content": prompt}], [])
    except assistant.ProviderError as e:
        raise ThemeGenError(f"AI request failed: {e}")
    content = (result.get("content") or "").strip()
    content = re.sub(r"^```(?:json)?", "", content).strip()
    content = re.sub(r"```$", "", content).strip()
    try:
        return json.loads(content)
    except (ValueError, TypeError) as e:
        raise ThemeGenError(f"The AI didn't return usable content ({e}). Try again, or simplify the brief.")


def _hero_chunk(headline, subtext, image_url):
    return (
        f'<div class="cms-banner" style="background-image:url(\'{escape(image_url, quote=True)}\')">'
        f'<div class="cms-banner-overlay"><h2>{escape(headline)}</h2><p>{escape(subtext)}</p></div></div>'
    )


def _text_chunk(heading, body):
    return f"<div><h2>{escape(heading)}</h2><p>{escape(body)}</p></div>"


def _cards_chunk(cards):
    cells = "".join(
        f'<div class="cms-card-shape"><h3>{escape(c.get("title", ""))}</h3><p>{escape(c.get("body", ""))}</p></div>'
        for c in cards
    )
    return f"<div>{cells}</div>"


def _maybe_generate_image(db, prompt, use_ai_images):
    if not use_ai_images:
        return PLACEHOLDER_IMAGE
    try:
        if not ai_image.is_configured(db):
            return PLACEHOLDER_IMAGE
        image_bytes = ai_image.generate_image(db, prompt, width=1600, height=600)
    except Exception:
        return PLACEHOLDER_IMAGE
    unique_name = f"{uuid.uuid4().hex}.png"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name), "wb") as f:
        f.write(image_bytes)
    url = f"/static/uploads/{unique_name}"
    db.execute("INSERT INTO generated_images (url, prompt) VALUES (?, ?)", (url, prompt))
    db.commit()
    return url


_SCHEMAS = {
    "landing": (
        '{"hero_headline": "...", "hero_subtext": "...", "intro_heading": "...", "intro_body": "...", '
        '"features": [{"title": "...", "body": "..."}, {"title": "...", "body": "..."}, {"title": "...", "body": "..."}], '
        '"cta_headline": "...", "cta_subtext": "..."}'
    ),
    "about": (
        '{"hero_headline": "...", "hero_subtext": "...", "story_heading": "...", "story_body": "...", '
        '"cta_headline": "...", "cta_subtext": "..."}'
    ),
    "simple": '{"hero_headline": "...", "hero_subtext": "...", "body_heading": "...", "body_text": "..."}',
}


def generate_layout_chunks(db, layout_key, brief, fill_scope, use_ai_images):
    """Returns a list of raw HTML chunks ready for admin.py's
    _insert_layout_chunks. `fill_scope` is "all" (AI-written copy) or
    "none" (blank starter text, layout only — no AI call at all)."""
    if layout_key not in LAYOUTS:
        raise ThemeGenError("Unknown layout.")

    fill = fill_scope != "none"
    copy = {}
    if fill:
        if not brief:
            raise ThemeGenError("Describe your site/business so the AI has something to write about.")
        prompt = render_template("prompts/theme_generator_brief.j2", brief=brief, schema=_SCHEMAS[layout_key])
        copy = _ai_json(db, prompt)

    def val(key, fallback):
        return (copy.get(key) or fallback) if fill else fallback

    chunks = []
    hero_image = _maybe_generate_image(db, f"A background image for a website hero banner about: {brief or layout_key}", use_ai_images)

    if layout_key == "landing":
        chunks.append(_hero_chunk(val("hero_headline", "Your Headline"), val("hero_subtext", "A short supporting line."), hero_image))
        chunks.append(_text_chunk(val("intro_heading", "Welcome"), val("intro_body", "Write an introduction here.")))
        features = copy.get("features") if fill else None
        if not features or len(features) < 3:
            features = [{"title": f"Feature {i + 1}", "body": "Describe this feature."} for i in range(3)]
        chunks.append(_cards_chunk(features[:6]))
        chunks.append(_hero_chunk(val("cta_headline", "Ready to get started?"), val("cta_subtext", "Get in touch today."), PLACEHOLDER_IMAGE))
    elif layout_key == "about":
        chunks.append(_hero_chunk(val("hero_headline", "Our Story"), val("hero_subtext", "A short supporting line."), hero_image))
        chunks.append(_text_chunk(val("story_heading", "About Us"), val("story_body", "Tell your story here.")))
        chunks.append(_hero_chunk(val("cta_headline", "Let's talk"), val("cta_subtext", "Reach out anytime."), PLACEHOLDER_IMAGE))
    else:  # simple
        chunks.append(_hero_chunk(val("hero_headline", "Your Headline"), val("hero_subtext", "A short supporting line."), hero_image))
        chunks.append(_text_chunk(val("body_heading", "Welcome"), val("body_text", "Write something here.")))

    return chunks
