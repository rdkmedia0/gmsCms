"""Writing the first draft of a newsletter from a sentence about it.

A blank newsletter is the hardest one to write, and an owner who sends
one a month spends most of that month not sending it. This asks what the
issue is about and lays out a draft: a subject, an opening, the middle,
and a sign-off.

**A draft, and never a send.** It creates a newsletter and opens it in
the editor exactly as "Write a newsletter" does. Nothing here can send
anything, and nothing it produces reaches anybody until a person has read
it and pressed Send. That is not a nicety: an AI writing to somebody
else's mailing list, over their name, is the one place in this app where
a plausible-sounding mistake goes out to real people and cannot be taken
back.

**It composes only from blocks the editor already has.** The prompt names
the allowed types and everything that comes back is put through
`email_layouts.normalise`, which drops anything else. So a model that
invents a "columns" block or returns raw HTML produces a shorter
newsletter, never a broken one -- the same rule this project applies to
demo content: if an owner could not have made it from the Tool menu,
neither can generated content.

**The opening and the sign-off are roled blocks**, like every other
newsletter's, so a generated one is an ordinary newsletter afterwards and
nothing downstream has to ask where it came from.
"""
import json
import re

from flask import render_template

from .. import assistant
from . import email_layouts

#  What the model is allowed to produce. Deliberately not the whole of
#  BLOCK_TYPES: a picture needs a file that exists in this install's
#  Media Library, and a Blog-posts block needs a blog id -- neither is
#  something a model can know, and both would arrive as an empty slot the
#  owner has to notice and fix.
ALLOWED = ("heading", "text", "button")


class Refused(Exception):
    """Something an owner can act on, said in their terms."""


def _json_from(text):
    """The object out of a reply, with fences and chatter stripped.

    Forgiving on purpose: a small model very often wraps its answer in
    ```json even when told not to, and refusing over that would be
    refusing over punctuation.
    """
    body = (text or "").strip()
    body = re.sub(r"^```(?:json)?", "", body).strip()
    body = re.sub(r"```$", "", body).strip()
    #  Some models add a sentence before the object. Take the outermost
    #  braces rather than giving up.
    if not body.startswith("{"):
        start, end = body.find("{"), body.rfind("}")
        if start >= 0 and end > start:
            body = body[start:end + 1]
    try:
        found = json.loads(body)
    except (ValueError, TypeError):
        return None
    return found if isinstance(found, dict) else None


def draft(db, brief, site_title):
    """(subject, blocks) for one newsletter, or Refused with a reason."""
    brief = (brief or "").strip()
    if not brief:
        raise Refused("Say what the newsletter is about, in a sentence or two.")
    if not assistant.is_configured(db):
        raise Refused("No AI provider is set up yet, so there is nothing to write "
                      "this. You can still write one yourself.")

    prompt = render_template("prompts/newsletter_brief.j2", brief=brief,
                             site_title=site_title or "this site",
                             allowed=", ".join(ALLOWED))
    try:
        result = assistant._call_provider(db, [{"role": "user", "content": prompt}], [])
    except assistant.ProviderError as e:
        raise Refused("The AI could not be reached: %s" % e)

    found = _json_from(result.get("content") or "")
    if found is None:
        #  A model that returns nothing is answered in words, and the
        #  words differ by provider -- "try a larger model" is useless
        #  advice to somebody on Gemini.
        raise Refused(assistant._nothing_came_back(db))

    middle = []
    for raw in (found.get("blocks") or []):
        if not isinstance(raw, dict) or raw.get("type") not in ALLOWED:
            continue
        middle.append(raw)
    if not middle:
        raise Refused("The AI didn't come back with anything usable. Try saying "
                      "what the newsletter is about in plainer words.")

    #  The opening and the sign-off are roled blocks like every other
    #  newsletter's, so a generated one is an ordinary newsletter
    #  afterwards and nothing downstream asks where it came from.
    blocks = []
    opening = str(found.get("opening") or "").strip()
    if opening:
        blocks.append({"type": "text", "text": opening, "role": "intro"})
    blocks.extend(middle)
    sign_off = str(found.get("sign_off") or "").strip()
    if sign_off:
        blocks.append({"type": "text", "text": sign_off, "role": "exit"})

    #  Everything through normalise: anything the model invented is
    #  dropped here rather than reaching the editor. A shorter newsletter
    #  is a fixable outcome; a broken one is not.
    blocks = email_layouts.normalise(blocks)
    if not blocks:
        raise Refused("The AI didn't come back with anything this editor can use.")

    subject = str(found.get("subject") or "").strip()[:200]
    return subject or "Untitled", blocks
