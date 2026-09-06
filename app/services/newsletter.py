"""
Newsletters: a page you can also post.

The idea is that there is nothing special about a newsletter. It is a page
— built with the same tools, in the same editor, living at its own address
so anyone can read it — and "send" is an action performed on it, not a
separate authoring system with its own editor, its own templates and its
own way of going wrong.

That has one consequence worth stating: an email is not a browser. Mail
clients disagree about stylesheets, and several still drop anything that
is not on the element itself, so what gets sent is the page's content
walked through a translator that puts the styling inline and drops what
email cannot do. The result is a plainer version of the page, on purpose.
It is not a screenshot of the site and should not pretend to be.

Two things are attached to every send because they have to be: an
unsubscribe link that works without logging in, and the sender's real
postal identity. Commercial email without both is unlawful in most of the
places this app is likely to be used, and the address is already on file
from the legal pages.
"""
import datetime
import json
import re
import time

#  A small, conservative sheet. Everything here is applied to the element
#  itself, because Gmail and Outlook between them will strip or ignore a
#  <style> block often enough that relying on one is a coin toss.
INLINE = {
    "h1": "margin:0 0 16px;font-size:26px;line-height:1.25;font-weight:700;color:#15181c;",
    "h2": "margin:28px 0 12px;font-size:21px;line-height:1.3;font-weight:700;color:#15181c;",
    "h3": "margin:22px 0 8px;font-size:17px;line-height:1.35;font-weight:700;color:#15181c;",
    "p": "margin:0 0 14px;font-size:16px;line-height:1.65;color:#2c3238;",
    "li": "margin:0 0 8px;font-size:16px;line-height:1.6;color:#2c3238;",
    "ul": "margin:0 0 16px;padding-left:22px;",
    "ol": "margin:0 0 16px;padding-left:22px;",
    "a": "color:#1a5fd0;text-decoration:underline;",
    "img": "max-width:100%;height:auto;display:block;border:0;margin:0 0 16px;border-radius:6px;",
    "blockquote": "margin:0 0 18px;padding:12px 18px;border-left:3px solid #c9d2dd;"
                  "font-size:17px;line-height:1.6;color:#2c3238;font-style:italic;",
    "table": "width:100%;border-collapse:collapse;margin:0 0 18px;",
    "th": "text-align:left;padding:8px 10px;border-bottom:2px solid #d7dde5;font-size:14px;",
    "td": "text-align:left;padding:8px 10px;border-bottom:1px solid #eceff3;font-size:15px;",
    "figcaption": "font-size:13px;color:#6b7480;margin:-8px 0 18px;",
    "hr": "border:0;border-top:1px solid #e3e8ee;margin:26px 0;",
}

#  Things that mean nothing in an email and are removed rather than sent
#  broken: forms cannot submit, video will not play, and an accordion is
#  a click away from being useless.
DROP_SELECTORS = ("form", "script", "style", "video", "iframe", "button", "input", "textarea")


#  What a look can change, and what it deliberately cannot.
#
#  Colour, weight and the rules between things travel to an inbox. Two
#  things do not, and pretending otherwise is how an email ends up
#  unreadable in somebody's client:
#
#  * The site's actual TYPEFACE. Gmail strips @font-face, so a
#    self-hosted webfont never loads. What can travel is the FALLBACK in
#    the stack the theme already declares -- "Georgia, serif" against a
#    system sans is a real, visible difference, and it is honest.
#  * A dark ground. Several clients invert colours themselves, and
#    Outlook's engine will not draw a border-radius at all. So the email
#    stays a light card whatever the site does, and the site's colour is
#    spent on headings, links, rules and the ground behind the card.
DEFAULT_BODY_FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def look_from(ramps, fonts=None):
    """The email's own look, worked out from the site's.

    `ramps` is `palette.role_ramps(template)`; `fonts` is a FONT_PAIRINGS
    entry or None. Everything is optional -- a template with no palette
    of its own sends exactly what this app sent before.
    """
    primary = (ramps or {}).get("primary") or {}
    accent = primary.get("base")
    return {
        "accent": accent if _is_hex(accent) else "#1a5fd0",
        #  A wash of the site's colour behind the card, so an email opens
        #  looking like the site rather than like a form letter. Pale on
        #  purpose: it is the one large area, and it sits under text in
        #  clients that ignore the card.
        "ground": primary.get("lightest") if _is_hex(primary.get("lightest")) else "#f4f6f8",
        "heading_font": (fonts or {}).get("heading") or DEFAULT_BODY_FONT,
        "body_font": (fonts or {}).get("body") or DEFAULT_BODY_FONT,
    }


def _is_hex(value):
    return bool(value) and bool(re.match(r"^#[0-9a-fA-F]{6}$", str(value)))


def styles_for(look):
    """The inline sheet for one look. Same shapes as INLINE, coloured."""
    if not look:
        return dict(INLINE)
    styles = dict(INLINE)
    heading = look["heading_font"]
    for tag in ("h1", "h2", "h3"):
        styles[tag] = styles[tag] + "font-family:%s;" % heading
    styles["a"] = "color:%s;text-decoration:underline;" % look["accent"]
    styles["blockquote"] = styles["blockquote"].replace("#c9d2dd", look["accent"])
    styles["th"] = styles["th"].replace("#d7dde5", look["accent"])
    return styles


def wrapper_html(text, subject="", view_url=""):
    """A greeting or a sign-off, as the owner typed it.

    Plain text with blank lines between paragraphs, so there is no raw
    HTML box anywhere in this app for something an owner writes. Two
    placeholders, and an unknown one is left as it was typed rather than
    disappearing -- a mistyped {{titel}} should look like a mistake, not
    like nothing.
    """
    if not (text or "").strip():
        return ""
    from html import escape
    filled = text.replace("{{title}}", subject or "").replace("{{link}}", view_url or "")
    paragraphs = [p.strip() for p in filled.split("\n\n") if p.strip()]
    return "\n".join("<p>%s</p>" % escape(p).replace("\n", "<br>") for p in paragraphs)


def _strip(html, tag):
    return re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", "", html, flags=re.S | re.I)


def to_email_html(sections, site_title, unsubscribe_url, sender_line, view_url=None,
                  look=None, intro="", outro=""):
    """One page's sections as an email body."""
    styles = styles_for(look)
    look = look or {"accent": "#1a5fd0", "ground": "#f4f6f8",
                    "heading_font": DEFAULT_BODY_FONT, "body_font": DEFAULT_BODY_FONT}
    parts = []
    if intro:
        parts.append(intro)
    for section in sections:
        content = section["content"] or ""
        if section["type"] == "media":
            #  A video cannot play in an email; a link to it can.
            if view_url:
                parts.append(
                    f'<p style="{styles["p"]}">'
                    f'<a href="{view_url}" style="{styles["a"]}">Watch this on the website</a></p>')
            continue
        for tag in DROP_SELECTORS:
            content = _strip(content, tag)
        content = re.sub(r"<(img|hr|br)\b([^>]*)/?>", r"<\1\2>", content)
        if section["title"]:
            parts.append(f'<h2 style="{styles["h2"]}">{section["title"]}</h2>')
        parts.append(content)

    if outro:
        parts.append(outro)
    body = "\n".join(parts)
    #  Inline the styles last, so anything the sections carried is styled
    #  the same way as what was added above.
    for tag, style in styles.items():
        #  MERGED, not prepended and not skipped. Prepending made a second
        #  style attribute and a browser reads the first, so a layout that
        #  set white text on a coloured button had the look's link colour
        #  put in front of it and the label vanished into the button.
        #  Skipping styled elements instead would stop the look reaching
        #  anything that carries a style of its own, which is most of what
        #  a section contains. So: the look goes in FIRST and the
        #  element's own declarations follow, which is the order that lets
        #  the later one win inside a single attribute.
        def _dress(match, s=style, t=tag):
            attrs = match.group(1)
            found = re.search(r'style\s*=\s*"([^"]*)"', attrs, flags=re.I)
            if found:
                merged = s + found.group(1)
                return f"<{t}" + attrs[:found.start()] + f'style="{merged}"' + attrs[found.end():] + ">"
            return f'<{t} style="{s}"{attrs}>'
        body = re.sub(rf"<{tag}\b([^>]*)>", _dress, body, flags=re.I)

    #  Background images do not survive most clients and leave an empty
    #  box where a banner was.
    body = re.sub(r'style="[^"]*background-image:[^"]*"', "", body)

    read_online = (f'<p style="font-size:13px;color:#6b7480;margin:0 0 18px;">'
                   f'<a href="{view_url}" style="color:#6b7480;">Read this on the website</a></p>'
                   if view_url else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{look['ground']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{look['ground']};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="width:600px;max-width:100%;background:#ffffff;border-radius:10px;padding:32px;
              font-family:{look['body_font']};">
<tr><td>
{read_online}
{body}
<hr style="{styles['hr']}">
<p style="font-size:12px;line-height:1.6;color:#8a939d;margin:0;">
{sender_line}<br>
You are getting this because you asked us to.
<a href="{unsubscribe_url}" style="color:#8a939d;">Unsubscribe</a>.
</p>
</td></tr></table>
</td></tr></table>
</body></html>"""


def to_transactional_html(text_body, site_title, sender_line, look=None):
    """One receipt or confirmation, dressed like the site.

    The same card, ground, colour and font stack a newsletter gets -- and
    deliberately NOT the same footer. A newsletter says "you are getting
    this because you asked us to" and carries an unsubscribe link,
    because it is a message to a list. An order confirmation is not: it
    is one half of a transaction the person just made, there is nothing
    to unsubscribe from, and offering it would be inviting somebody to
    opt out of their own receipt.

    The words are the plain-text body already written for each message,
    converted to paragraphs -- so there is one wording to keep true, and
    the text half of the mail is the same words rather than a second
    draft that can drift.
    """
    styles = styles_for(look)
    look = look or {"accent": "#1a5fd0", "ground": "#f4f6f8",
                    "heading_font": DEFAULT_BODY_FONT, "body_font": DEFAULT_BODY_FONT}
    #  The SAME small vocabulary the editor writes and its preview shows:
    #  `##` a heading, `**bold**`, `[words](address)`, `- ` a list. It
    #  used to be plain-text-to-paragraphs, so a message written with any
    #  of them arrived with the markers in it -- and the editor showed it
    #  correctly the whole time, which is the worst version: the screen
    #  saying one thing and the inbox another.
    #
    #  Imported here rather than at module level: email_layouts imports
    #  nothing from this module, and keeping it that way is what stops
    #  the two becoming one.
    from . import email_layouts
    body = "".join(email_layouts.rich(text_body, look))
    #  Links are not marked up in the plain text, so make bare URLs
    #  clickable -- a receipt whose link has to be copied out by hand is a
    #  worse receipt.
    body = re.sub(r'(?<!")(https?://[^\s<>"]+)',
                  lambda m: '<a href="%s">%s</a>' % (m.group(1), m.group(1)), body)
    for tag, style in styles.items():
        body = re.sub(rf"<{tag}\b([^>]*)>",
                      lambda m, st=style, t=tag: f'<{t} style="{st}"{m.group(1)}>',
                      body, flags=re.I)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{look['ground']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{look['ground']};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="width:600px;max-width:100%;background:#ffffff;border-radius:10px;padding:32px;
              font-family:{look['body_font']};">
<tr><td>
{body}
<hr style="{styles['hr']}">
<p style="font-size:12px;line-height:1.6;color:#8a939d;margin:0;">{sender_line}</p>
</td></tr></table>
</td></tr></table>
</body></html>"""


def plain_text(sections, unsubscribe_url, sender_line, intro="", outro=""):
    """The text half. Some people read mail as text, and a message with no
    text part looks more like spam to a filter than one with it."""
    out = []
    #  The greeting and the sign-off, stripped of their markup like
    #  everything else here -- written once and used by both halves of
    #  the message, so they cannot say different things.
    if intro:
        out.append(re.sub(r"<[^>]+>", "", intro).strip())
    for section in sections:
        if section["title"]:
            out.append(section["title"].upper())
        text = re.sub(r"<br\s*/?>", "\n", section["content"] or "")
        text = re.sub(r"</(p|h1|h2|h3|li|tr)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        out.append(text.strip())
    if outro:
        out.append(re.sub(r"<[^>]+>", "", outro).strip())
    return "\n\n".join(p for p in out if p) + (
        f"\n\n---\n{sender_line}\nUnsubscribe: {unsubscribe_url}\n")


#  A newsletter of its own -- a layout and the words in it. See db.py for
#  why the values are JSON and why this is not a page.
def list_composed(db):
    return db.execute("SELECT * FROM newsletters ORDER BY id DESC").fetchall()


def get_composed(db, newsletter_id):
    return db.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,)).fetchone()


def create_composed(db, layout, subject=""):
    cur = db.execute(
        "INSERT INTO newsletters (subject, layout, values_json) VALUES (?, ?, '{}')",
        (subject, layout))
    return cur.lastrowid


def save_composed(db, newsletter_id, subject, values):
    db.execute(
        "UPDATE newsletters SET subject = ?, values_json = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (subject, json.dumps(values or {}), newsletter_id))


def composed_blocks(row):
    """One newsletter's blocks, whatever shape it was saved in.

    A newsletter written under the old named-slot model still opens: its
    values are read as blocks rather than discarded. An upgrade that
    silently empties somebody's draft is worse than one that refuses to
    run.
    """
    from app.services import email_layouts
    stored = composed_values(row)
    if isinstance(stored, dict) and "blocks" in stored:
        return email_layouts.normalise(stored.get("blocks"))
    return email_layouts.from_named_slots(stored if isinstance(stored, dict) else {})


_UNSET = object()


def save_blocks(db, newsletter_id, subject, blocks, layout=None, blog_id=_UNSET):
    """Blocks are the whole of what a newsletter is now."""
    from app.services import email_layouts
    stored = {"blocks": email_layouts.normalise(blocks)}
    if layout:
        db.execute("UPDATE newsletters SET layout = ? WHERE id = ?", (layout, newsletter_id))
    if blog_id is not _UNSET:
        #  A column, not a key in values_json: it is read by the SCHEDULER
        #  when the newsletter is nowhere near a form, and a setting
        #  buried in a blob is one nothing else can ask about.
        db.execute("UPDATE newsletters SET blog_id = ? WHERE id = ?",
                   (blog_id or None, newsletter_id))
    save_composed(db, newsletter_id, subject, stored)


def composed_values(row):
    """The filled-in slots, forgiving of a row written before a layout
    changed -- a missing slot is empty, not an error."""
    try:
        #  A dict as well as a row: the live preview builds one from the
        #  form rather than from the database, so nothing is saved while
        #  somebody is still typing.
        return json.loads((row["values_json"] if not isinstance(row, dict)
                           else row.get("values_json")) or "{}")
    except (ValueError, TypeError):
        return {}


def delete_composed(db, newsletter_id):
    db.execute("DELETE FROM newsletters WHERE id = ?", (newsletter_id,))


def record_send(db, kind, target_id, subject, sent, failed, audience="all"):
    #  Including who it was for. "Sent to 40" cannot say whether that was
    #  the whole list or the customers on it, and the difference is the
    #  first thing anybody asks a month later.
    db.execute(
        "INSERT INTO newsletter_sends (target_kind, target_id, subject, recipients, failed, audience) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kind, target_id, subject, sent, failed, audience),
    )


def history(db, kind=None, target_id=None, limit=50):
    """What has gone out, newest first, whatever it was sent from.

    The title is worked out by looking outwards at a page or a post, and
    falls back to the subject line that was stored -- a record of forty
    emails is worth keeping after somebody deletes the page it came from,
    which is exactly why the foreign key went away.
    """
    sql = """
        SELECT s.*,
               COALESCE(p.title, b.title, s.subject) AS title,
               p.slug AS page_slug, b.slug AS post_slug, bl.slug AS blog_slug,
               p.is_public AS page_public, b.published_at AS post_published
        FROM newsletter_sends s
        LEFT JOIN pages p ON s.target_kind = 'page' AND p.id = s.target_id
        LEFT JOIN blog_posts b ON s.target_kind = 'post' AND b.id = s.target_id
        LEFT JOIN blogs bl ON bl.id = b.blog_id
    """
    where, params = [], []
    if kind:
        where.append("s.target_kind = ?")
        params.append(kind)
    if target_id:
        where.append("s.target_id = ?")
        params.append(target_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.execute(sql + " ORDER BY s.id DESC LIMIT ?", (*params, limit)).fetchall()


def forget_send(db, send_id):
    """Removes one line from what has gone out.

    Kept deliberate rather than easy. The send record is evidence: it is
    how an owner answers "you emailed me" a year later, and it survives
    the page or post being deleted for exactly that reason. So removing
    one is a per-row act with a confirmation, not a Clear History button
    -- the same distinction the subscriber screen already draws between
    unsubscribing somebody and erasing them.

    What it does NOT touch is anybody's subscription or consent record.
    Those live on `subscribers` and are a different question.
    """
    db.execute("DELETE FROM newsletter_sends WHERE id = ?", (send_id,))


def last_send(db, kind, target_id):
    return db.execute(
        "SELECT * FROM newsletter_sends WHERE target_kind = ? AND target_id = ? "
        "ORDER BY id DESC LIMIT 1", (kind, target_id)
    ).fetchone()


def sent_issues(db):
    """Everything that has actually gone out AND can still be read.

    Both kinds, in one list, newest first. Two conditions do the work:
    it was sent at least once, and there is something at the other end to
    read -- a page still on the site, or a post still published. A page
    the owner has since made private, or a deleted post, drops out of the
    archive while its send record stays where it belongs, in the history.
    """
    return db.execute("""
        SELECT s.target_kind, s.target_id,
               COALESCE(p.title, b.title) AS title,
               COALESCE(p.meta_description, b.excerpt) AS blurb,
               p.slug AS page_slug, b.slug AS post_slug, bl.slug AS blog_slug,
               MIN(s.sent_at) AS first_sent
        FROM newsletter_sends s
        LEFT JOIN pages p
               ON s.target_kind = 'page' AND p.id = s.target_id AND p.is_public = 1
        LEFT JOIN blog_posts b
               ON s.target_kind = 'post' AND b.id = s.target_id AND b.published_at IS NOT NULL
        LEFT JOIN blogs bl ON bl.id = b.blog_id
        WHERE p.id IS NOT NULL OR b.id IS NOT NULL
        GROUP BY s.target_kind, s.target_id
        ORDER BY first_sent DESC
    """).fetchall()


def as_sections(title, content_html):
    """One post, in the shape `to_email_html` reads.

    A post is not made of sections -- it is a title and a piece of
    writing -- so it is handed over as one, rather than teaching the
    translator about a second kind of input. The title becomes the
    heading at the top of the email, which is what a reader expects and
    what the subject line usually repeats.
    """
    return [{"type": "text", "title": title, "content": content_html}]


def sender_line(legal_settings, site_title):
    """Who is sending, and whether that is enough to send a list mail on.

    Returns (line, ok). The mandatory core of commercial email everywhere
    is a truthful sender identity and an easy opt-out. A physical postal
    address is REQUIRED by US CAN-SPAM, and best practice in the EU and
    Switzerland -- but NOT strictly mandated there for the email itself,
    where it is the WEBSITE's Impressum that must carry the address. So
    whether the address is repeated in emails is the owner's choice
    (`email_include_address`, default on), separate from the website.

    `ok` is False only when the owner wants the address in their mail but
    has not set one -- that is the case worth blocking a send over. With
    the address off, or on file, `ok` is True.
    """
    name = (legal_settings.get("business") or site_title or "").strip()
    address = " ".join(part.strip() for part in (legal_settings.get("address") or "").splitlines() if part.strip())
    include = (legal_settings.get("email_include_address", "1") != "0")
    if not include:
        #  The owner keeps the address off their emails on purpose. It is
        #  still on the site, which is what the Impressum needs; nothing to
        #  block. (Turn it back on if mailing US recipients -- see the
        #  toggle on the Sending-email screen.)
        return name or "", True
    if not address:
        return name or "", False
    return f"{name}, {address}", True


#  What a send can be pointed at. "Everything" is the common case; the
#  other two exist because a newsletter page is a page and people keep
#  writing on it -- an issue is often the newest thing on a page that
#  already carries three older ones, and sending the lot again is not
#  what anybody meant.
SEND_CHOICES = (
    ("all", "Everything on this page"),
    ("latest", "Just the latest — whichever section changed last"),
)


def _changed_key(row):
    """How recently this section changed, as something that cannot tie.

    `changed_seq` is a counter the database bumps on every write (see
    db.py), so it is a total order. The fallback is the old comparison,
    for a caller whose SELECT names its columns and does not ask for it --
    no worse than it ever was, and never mixed with a real sequence,
    since every row in one query comes back with the same columns.
    """
    try:
        seq = row["changed_seq"]
    except (IndexError, KeyError):
        seq = None
    return (seq if seq is not None else -1, row["updated_at"] or "", row["id"])


def sections_for(sections, choice):
    """(what to send, how to describe it). `sections` in page order.

    `choice` is "all", "latest", or a section id as a string. An id that
    is not on the page falls back to everything rather than sending an
    empty message -- a send that quietly goes out blank is worse than one
    that sends more than was asked.
    """
    rows = list(sections)
    if not rows:
        return [], "nothing"
    if choice == "latest":
        #  Last changed, and the position it holds, so the description can
        #  say WHICH one it picked -- "the latest" is not something an
        #  owner should have to take on trust before pressing send.
        newest = max(range(len(rows)), key=lambda i: _changed_key(rows[i]))
        return [rows[newest]], "section %d of %d" % (newest + 1, len(rows))
    if choice and choice not in ("all", "latest"):
        for index, row in enumerate(rows):
            if str(row["id"]) == str(choice):
                return [row], "section %d of %d" % (index + 1, len(rows))
    return rows, ("the whole page" if len(rows) > 1 else "the page")


def choices_for(sections):
    """The send menu for one page: the two standing answers, then a line
    per section so one can be picked by number."""
    out = list(SEND_CHOICES)
    for index, row in enumerate(sections):
        label = (row["title"] or "").strip() or _first_words(row["content"])
        out.append((str(row["id"]), "Section %d%s" % (index + 1, " — " + label if label else "")))
    return out


def _first_words(content, words=6):
    """Enough of a section to recognise it by, with the markup taken off."""
    text = re.sub(r"<[^>]+>", " ", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split(" ")
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


#  ---------------------------------------------------------------
#  Everything a send has to be sure of, once
#  ---------------------------------------------------------------
#
#  These checks were inside the route, tangled with `request.form`,
#  `flash` and `redirect` -- which was fine while a send only ever
#  happened because somebody had just pressed a button. A SCHEDULED send
#  happens on a background thread with no request and nobody to flash a
#  message at, and the one thing that must not happen is a second copy of
#  these rules that drifts from the first. So they live here, answering in
#  plain data, and both callers say what they like about the answer.
#
#  The same rule already applies to `_send_it`: extract the guards first,
#  then add the caller, or the two drift.

class Blocked(object):
    """Why a send cannot go, in words for the person who has to fix it.

    `where` is an admin endpoint to send them to when the fix lives on
    another screen -- a refusal that does not say where to go is only
    half a refusal.
    """

    def __init__(self, message, where=None):
        self.message = message
        self.where = where

    def __repr__(self):
        return "Blocked(%r, %r)" % (self.message, self.where)


class Ready(object):
    """Who it goes to, and what it signs off as."""

    def __init__(self, people, sender_line, site_title):
        self.people = people
        self.sender_line = sender_line
        self.site_title = site_title


def preflight(db, mailer, subscribers, legal, sections, audience,
              email_settings, legal_settings, site_title):
    """Ready(...) or Blocked(...). No Flask, so a thread can ask too.

    The modules come in as arguments rather than as imports because a
    service in this project never reaches sideways for its collaborators
    -- and because passing them is what lets a checker hand in a mailer
    that captures instead of sends.
    """
    if not mailer.is_configured(email_settings):
        return Blocked("Email isn't set up yet, so there is nothing to send with.",
                       "admin.settings_email")
    if not sections:
        return Blocked("There's nothing in this to send — write it first.")

    if audience not in dict(subscribers.AUDIENCES):
        audience = "all"
    #  Confirmed only. An address that was typed into the form and never
    #  answered its confirmation mail is on the table so it can be shown
    #  and so a second attempt does not make a second row -- it is not a
    #  subscriber, and sending to it is the exact thing double opt-in
    #  exists to prevent.
    people = subscribers.listing(db, confirmed_only=True, audience=audience)
    if not people:
        counts = subscribers.counts(db)
        if audience == "customers":
            return Blocked(
                "Nobody on the list has bought anything yet, so there are no customers to "
                "send to. You can flag somebody as a customer by hand on the Email list "
                "screen.")
        return Blocked("Nobody has confirmed yet." if counts["pending"]
                       else "Nobody is on the list yet.")

    line, ok = sender_line(legal_settings, site_title)
    if not ok:
        #  Only reached when the owner WANTS the address in their mail (the
        #  default) but has not set one. Either add it, or turn the setting
        #  off if they would rather keep it off their emails -- their choice
        #  now, not a hard rule, because outside the US the address is best
        #  practice for the mail rather than mandated (it is the website's
        #  Impressum that must carry it).
        return Blocked(
            "Add your postal address on the Legal pages screen, or switch off "
            "“Include my postal address in emails” on the Sending-email screen "
            "if you would rather keep it out of your mail.",
            "admin.legal_pages")
    return Ready(people, line, site_title)


def deliver(db, mailer, email_settings, ready, sections, subject, view_url,
            look, intro, outro, audience, kind, target_id, link_for):
    """Build it, send it, write down that it went. (sent, failed).

    The other half of preflight(): between them they are the whole of a
    send, with no Flask in either, so the route and the scheduler run the
    same code rather than two copies of it.
    """
    html = to_email_html(sections, ready.site_title, "{{UNSUBSCRIBE}}", ready.sender_line,
                         view_url, look=look, intro=intro, outro=outro)
    text = plain_text(sections, "{{UNSUBSCRIBE}}", ready.sender_line,
                      intro=intro, outro=outro)
    sent, failed = send_to_list(db, mailer, email_settings, ready.people, subject,
                                html, text, ready.site_title, link_for)
    record_send(db, kind, target_id, subject, sent, failed, audience)
    return sent, failed


def send_to_list(db, mailer, settings, people, subject, html, text, from_name, link_for):
    """Sends one message per person, so each carries its own unsubscribe
    link. Returns (sent, failed).

    Deliberately one at a time and paced. A shared BCC would put every
    subscriber's address in front of every other subscriber, and a burst
    of a few hundred through somebody's ordinary mail account is how that
    account stops being allowed to send at all.
    """
    sent = failed = 0
    for person in people:
        try:
            unsubscribe_url = link_for(person["token"])
            mailer.send_html(
                settings, person["email"], subject,
                html.replace("{{UNSUBSCRIBE}}", unsubscribe_url),
                text.replace("{{UNSUBSCRIBE}}", unsubscribe_url),
                from_name=from_name,
                #  The same link again, where the mail PROGRAM can find
                #  it: a reader that knows about these shows its own
                #  unsubscribe button, and the button somebody reaches for
                #  instead is the one marked spam.
                headers={"List-Unsubscribe": f"<{unsubscribe_url}>",
                         "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
            )
            sent += 1
        except Exception:  # noqa: BLE001 - one bad address must not stop the rest
            failed += 1
        time.sleep(0.4)
    return sent, failed


def overview(db, scheduling, audiences):
    """Every newsletter, once, whatever point of its life it is at.

    The screen showed three lists -- "Yours" (written, not sent), "Going
    out on its own" (on the clock) and "What has gone out" (sent). Those
    are not three things. They are one thing at three moments, and
    splitting them meant a newsletter moved between cards as it aged, so
    "where is the one about the autumn hours" depended on remembering
    whether it had gone yet.

    One row each, carrying what the list has to answer: when it was
    written, when it went, what it is called, who it went to, and -- when
    it is waiting -- which named schedule it is waiting on.

    Sends of a PAGE or a POST are included as rows of their own. They are
    not composed newsletters and cannot be edited as one, but they went
    to the list and the record of that outlives whatever it was sent
    from -- which is the whole reason newsletter_sends carries no foreign
    key.
    """
    labels = dict(audiences)
    rows = []

    pending = {}
    for job in scheduling.recent(db, limit=200):
        if job["kind"] == "newsletter" and not job["claimed_at"] and not job["done_at"]:
            pending[job["target_id"]] = job

    for item in list_composed(db):
        last = last_send(db, "newsletter", item["id"])
        job = pending.get(item["id"])
        rows.append({
            "kind": "newsletter",
            "id": item["id"],
            "subject": item["subject"] or "Untitled",
            "created": item["created_at"],
            "sent": last["sent_at"] if last else None,
            "audience": labels.get(
                (job or last or {})["audience"] if (job or last) else None, ""),
            "schedule": (job["template_name"] if job and job["template_name"]
                         else (job["send_at"] if job else "")),
            "waiting": bool(job),
            "editable": True,
            "send_id": None,
            "recipients": last["recipients"] if last else None,
            "failed": last["failed"] if last else 0,
        })

    #  Anything that went to the list from somewhere else. Keyed by what
    #  it was sent from, so two sends of one post are two rows -- they
    #  were two emails.
    for send in history(db, limit=200):
        #  `target_kind`, not `kind`. sqlite3.Row raises on a missing
        #  key, so this 500s the moment the site has ANY send history --
        #  and an install with none never reaches the loop body, which is
        #  exactly why it passed every check here and failed on the
        #  owner's site the first time they opened the screen.
        if send["target_kind"] == "newsletter":
            continue
        rows.append({
            "kind": send["target_kind"],
            "id": send["target_id"],
            "subject": send["subject"] or send["title"] or "(no subject)",
            "created": None,
            "sent": send["sent_at"],
            "audience": labels.get(send["audience"], ""),
            "schedule": "",
            "waiting": False,
            "editable": False,
            #  The send's own id, so the one table can carry what the
            #  "What has gone out" card carried: removing a LINE from the
            #  record, which is a deliberate act and not tidying.
            "send_id": send["id"],
            "recipients": send["recipients"],
            "failed": send["failed"],
        })

    #  Newest activity first: what somebody is looking for is almost
    #  always the thing that moved most recently, sent or written.
    rows.sort(key=lambda r: (r["sent"] or r["created"] or ""), reverse=True)
    return rows


def copy_composed(db, newsletter_id):
    """Last month's, as a starting point for this month's.

    The obvious way to write a newsletter is to start from the one that
    worked, and without this the choice was retyping it or editing the
    original -- which loses the copy that was actually sent.

    The subject gains "(copy)" rather than being left identical: two rows
    with one name in a list is a thing somebody has to open both of to
    tell apart.
    """
    row = get_composed(db, newsletter_id)
    if not row:
        return None
    new_id = create_composed(db, row["layout"] or "letter",
                             ((row["subject"] or "Untitled") + " (copy)")[:200])
    save_blocks(db, new_id, ((row["subject"] or "Untitled") + " (copy)")[:200],
                composed_blocks(row), layout=row["layout"])
    return new_id


def post_rows_for(db, blog_service, blog_id, post_id, link_for, excerpt_words=28):
    """One chosen post of one blog, flattened for an email.

    Resolved HERE rather than inside email_layouts, which renders an
    email and knows nothing about blogs -- that is what keeps it callable
    from a template, a checker and a scheduled send alike.

    Published only, which also means a post chosen and later unpublished
    simply drops out: a draft has no address to link to, so including one
    would put a "Read it" link into somebody's inbox pointing at a 404,
    and unlike a page an email cannot be corrected once it has gone.
    """
    try:
        blog = blog_service.get_blog(db, int(blog_id))
    except (TypeError, ValueError):
        return []
    if not blog:
        return []
    #  ONE post, chosen. It used to take the latest N, which is a feed
    #  rather than a choice -- and an owner deciding what goes in this
    #  issue is choosing a post. Two posts means two blocks.
    rows = []
    chosen = [p for p in blog_service.posts_for(db, blog["id"], published_only=True)
              if str(p["id"]) == str(post_id)]
    for post in chosen:
        words = re.sub(r"<[^>]+>", " ", post["content"] or "")
        words = re.sub(r"\s+", " ", words).strip().split(" ")
        excerpt = " ".join(words[:excerpt_words])
        if len(words) > excerpt_words and excerpt:
            excerpt += "\u2026"
        rows.append({
            "title": post["title"] or "Untitled",
            "date": (post["published_at"] or "")[:10],
            "excerpt": excerpt,
            "url": link_for(blog, post) if link_for else "",
        })
    return rows


def sent_composed(db, limit=6):
    """Composed newsletters that have already gone, newest send first.

    A newsletter that went out is an arrangement somebody approved and a
    reader received, which is why "start from last month's" is how most
    people write this month's. Distinct rows only: sending one twice does
    not make it two templates.
    """
    return db.execute(
        "SELECT n.id, n.subject, MAX(s.sent_at) AS sent_at "
        "FROM newsletters n "
        "JOIN newsletter_sends s ON s.target_kind = 'newsletter' AND s.target_id = n.id "
        "GROUP BY n.id ORDER BY sent_at DESC LIMIT ?", (limit,)).fetchall()


def blocks_of(db, newsletter_id):
    """One newsletter's blocks, by id -- for starting another from it."""
    row = get_composed(db, newsletter_id)
    return composed_blocks(row) if row else []


# --------------------------------------------------- the same words, on the site


def page_html(blocks, look=None):
    """A newsletter's body as writing for a PAGE, not an inbox.

    The opening and the sign-off are left out. They are addressed to a
    reader who has just been written to -- "Hello," at the top and
    "Thanks for reading." at the bottom -- and a blog entry has no such
    reader: it is found weeks later by somebody who was never sent
    anything. That is the whole reason this is not simply the email
    again.

    Everything else survives. Words, headings, pictures, a button and a
    rule are all things a page can show, and they come out as ordinary
    tags with no inline styles, so the site's own fonts, colours and
    shape reach them (see `email_layouts.rich(plain=True)`). An email is
    inline-styled because a mail client strips a stylesheet; a page has
    the stylesheet, and carrying the email's styles onto it would pin one
    paragraph to 16px Arial in the middle of the site's own type.

    A `posts` block is dropped: it is a marker resolved against the blog
    at send time, and a blog entry made of a list of that same blog's
    entries is a mirror pointing at itself.
    """
    from html import escape
    from . import email_layouts
    out = []
    for block in email_layouts.normalise(blocks):
        if block.get("role") in email_layouts.ROLES:
            continue
        kind = block["type"]
        if kind == "heading":
            level = 3 if str(block.get("level")) == "3" else 2
            words = email_layouts.rich(block.get("text") or "", look, plain=True)
            #  A heading is one line, so its own text is taken rather than
            #  whatever `rich` decided to wrap it in -- otherwise "## Sale"
            #  typed INTO a heading would arrive as a heading inside a
            #  heading.
            text = escape((block.get("text") or "").strip())
            if text:
                out.append("<h%d>%s</h%d>" % (level, _inline(text), level))
            elif words:
                out.extend(words)
        elif kind == "text":
            out.extend(email_layouts.rich(block.get("text") or "", look, plain=True))
        elif kind == "image":
            src = (block.get("src") or "").strip()
            if src:
                img = '<img src="%s" alt="%s">' % (escape(src), escape(block.get("alt") or ""))
                url = (block.get("url") or "").strip()
                if url.startswith(email_layouts.LINK_SCHEMES):
                    img = '<a href="%s">%s</a>' % (escape(url), img)
                out.append("<p>%s</p>" % img)
        elif kind == "button":
            label = (block.get("label") or "").strip()
            url = (block.get("url") or "").strip()
            if label and url.startswith(email_layouts.LINK_SCHEMES):
                out.append('<p><a class="btn" href="%s">%s</a></p>'
                           % (escape(url), escape(label)))
            elif label:
                out.append("<p>%s</p>" % escape(label))
        elif kind == "divider":
            out.append("<hr>")
    return "\n".join(out)


def _inline(escaped):
    """Bold, italic and a link inside one already-escaped line."""
    from . import email_layouts
    email_layouts._LINK_STYLE[0] = ""
    return email_layouts._spans(escaped)


def keep_as_post(db, blogs, row, blocks=None, when=None):
    """The newsletter that just went out, kept as a blog entry.

    Called from BOTH send paths -- the button and the scheduler -- for
    the reason the guards are: two copies of "and also publish it" is how
    one of them comes to be forgotten when something changes. It is the
    last thing either does, and only if the send itself succeeded: an
    entry announcing a letter nobody received is worse than no entry.

    Returns the post's id, or None when this newsletter is not kept --
    which is the ordinary case, and not a failure.

    The date is the date it was SENT, because that is the day it is about.
    A subject is required and stands as the title: an untitled entry in a
    list of entries is unfindable, and the subject is already the name the
    newsletter is known by.
    """
    blog_id = None
    try:
        blog_id = row["blog_id"]
    except (IndexError, KeyError):
        blog_id = None
    if not blog_id or not blogs.get_blog(db, blog_id):
        return None
    title = (row["subject"] or "").strip()
    if not title:
        return None
    html = page_html(composed_blocks(row) if blocks is None else blocks)
    if not html:
        return None
    stamp = (when or datetime.datetime.utcnow()).strftime("%Y-%m-%d")
    return blogs.create_post(db, blog_id, title, content=html, published_at=stamp)
