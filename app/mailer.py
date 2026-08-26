"""
Sends the site's outgoing mail via plain SMTP (stdlib only — no new
dependency). Settings are stored in the `settings` table, configured from
the admin's own Gmail (or any SMTP provider) at /admin/settings/email —
see app/routes/admin.py's get_email_settings().
"""
import smtplib
from email.message import EmailMessage


def is_configured(settings):
    return bool(settings.get("smtp_host") and settings.get("smtp_username") and settings.get("to_email"))


def send(settings, to_email, subject, body, reply_to=None, from_name=None, headers=None):
    """One place that talks SMTP. Raises on failure — callers decide how to
    surface that, because the right answer differs: a contact form can ask
    the visitor to try again, while a post-purchase email must never take
    the order down with it."""
    msg = EmailMessage()
    sender = settings.get("from_email") or settings["smtp_username"]
    msg["Subject"] = subject
    msg["From"] = f"{from_name or settings.get('from_name') or 'Website'} <{sender}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    #  List-Unsubscribe and friends. A mail program shows its own
    #  unsubscribe control when it finds these, which is both a kindness
    #  and the difference between somebody leaving the list and somebody
    #  pressing "spam" -- and a spam report costs the sender far more.
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)

    port = int(settings.get("smtp_port") or 587)
    with smtplib.SMTP(settings["smtp_host"], port, timeout=15) as smtp:
        if settings.get("smtp_use_tls", "1") != "0":
            smtp.starttls()
        smtp.login(settings["smtp_username"], settings["smtp_password"])
        smtp.send_message(msg)


def send_contact_message(settings, name, email, message):
    """Raises on failure — callers decide how to surface that to the user."""
    body = "From: {} <{}>\n\n{}".format(name, email, message)
    send(
        settings,
        settings["to_email"],
        f"New contact form message from {name}",
        body,
        reply_to=email or None,
        from_name=settings.get("from_name") or "Website Contact Form",
    )


def send_html(settings, to_email, subject, html_body, text_body, from_name=None, headers=None):
    """A message with both halves.

    Text as well as HTML because some people read mail as text, and
    because a message carrying only HTML looks more like spam to a filter
    than one carrying both — which matters more for a newsletter than for
    a single transactional email.
    """
    msg = EmailMessage()
    sender = settings.get("from_email") or settings["smtp_username"]
    msg["Subject"] = subject
    msg["From"] = f"{from_name or settings.get('from_name') or 'Website'} <{sender}>"
    msg["To"] = to_email
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    port = int(settings.get("smtp_port") or 587)
    with smtplib.SMTP(settings["smtp_host"], port, timeout=20) as smtp:
        if settings.get("smtp_use_tls", "1") != "0":
            smtp.starttls()
        smtp.login(settings["smtp_username"], settings["smtp_password"])
        smtp.send_message(msg)
