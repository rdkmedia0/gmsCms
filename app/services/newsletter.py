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
    body = wrapper_html(text_body)
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


def save_blocks(db, newsletter_id, subject, blocks, layout=None):
    """Blocks are the whole of what a newsletter is now."""
    from app.services import email_layouts
    stored = {"blocks": email_layouts.normalise(blocks)}
    if layout:
        db.execute("UPDATE newsletters SET layout = ? WHERE id = ?", (layout, newsletter_id))
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
    """Who is sending, in a form that satisfies the rules about it.

    An address is required on commercial email in the EU, Switzerland and
    the US alike. It is already on file from the legal pages, so this
    reuses it rather than asking again — and says plainly when it is
    missing, because sending without it is the kind of thing nobody
    notices until somebody complains.
    """
    name = (legal_settings.get("business") or site_title or "").strip()
    address = " ".join(part.strip() for part in (legal_settings.get("address") or "").splitlines() if part.strip())
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
