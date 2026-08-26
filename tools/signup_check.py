"""Walks a sign-up all the way through, on a site of its own.

Double opt-in is four separate acts spread over two channels -- a form, a
mail, a link, and another mail -- and testing it by hand means really
subscribing a real address through the owner's real mail server. So this
walks the whole path against a throwaway site, with the mail captured
instead of sent, and asserts the things that would be embarrassing to get
wrong:

  * the form's answer says an email is coming, and comes back as JSON
    when the page asks for JSON (which is what lets the answer appear in
    the box rather than after a reload);
  * nothing is sent to an address that has not confirmed;
  * confirming produces a second mail that carries an unsubscribe link,
    in the body AND in the headers a mail program reads;
  * that link works without a login, and works as a POST, which is what
    a one-click unsubscribe button sends;
  * the exported record can actually evidence the sequence.

Run inside the container:

    docker compose exec -T web python /app/tools/signup_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="signup-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import mailer                                        # noqa: E402
from app.services import blocks, subscribers                  # noqa: E402

SENT = []


def _capture(settings, to_email, subject, body, reply_to=None, from_name=None, headers=None):
    SENT.append({"to": to_email, "subject": subject, "body": body,
                 "headers": headers or {}})


mailer.send = _capture
mailer.is_configured = lambda settings: True

failures = []


def check(name, ok, detail=""):
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


app = create_app()
with app.app_context():
    db = get_db()
    #  A sender line needs a postal address, or the site refuses to send
    #  at all -- which is correct, and would make every check below fail
    #  for the wrong reason.
    for key, value in (("legal_business", "Test Bakery GmbH"),
                       ("legal_address", "Bahnhofstrasse 1\n8001 Zurich"),
                       ("site_title", "Test Bakery")):
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    #  A page with a sign-up on it, built the way the tool builds one.
    page = db.execute("SELECT id FROM pages ORDER BY id LIMIT 1").fetchone()
    markup = blocks.BLOCKS["newsletter"]["build"](blocks.BLOCKS["newsletter"]["defaults"])
    db.execute("INSERT INTO sections (page_id, type, content, position) VALUES (?, 'html', ?, 999)",
               (page["id"], markup))
    db.commit()

client = app.test_client()

#  ------------------------------------------------- the form, as a fetch
r = client.post("/subscribe", data={"email": "someone@example.com",
                                    "consent_text": "Yes, email me occasional updates."},
                headers={"X-Requested-With": "cms-subscribe", "Referer": "http://localhost/"})
answer = r.get_json() or {}
check("the form answers in words, not a redirect", r.status_code == 200 and bool(answer),
      "status %s" % r.status_code)
check("the answer says to go and look in the inbox",
      "email" in answer.get("message", "").lower() and "link" in answer.get("message", "").lower(),
      answer.get("message", ""))
check("a plain form post still redirects (no script, no change)",
      client.post("/subscribe", data={"email": "plain@example.com"},
                  headers={"Referer": "http://localhost/"}).status_code == 302)

#  ---------------------------------------------------- the invitation
invite = [m for m in SENT if m["to"] == "someone@example.com"]
check("one invitation was sent", len(invite) == 1, "%d sent" % len(invite))
confirm_url = ""
if invite:
    for word in invite[0]["body"].split():
        if "/subscribe/confirm/" in word:
            confirm_url = word
    check("the invitation carries a confirmation link", bool(confirm_url))
    check("the invitation quotes what was agreed to",
          "occasional updates" in invite[0]["body"])

with app.app_context():
    db = get_db()
    row = db.execute("SELECT * FROM subscribers WHERE email = 'someone@example.com'").fetchone()
    check("the address is on the table but not confirmed", row is not None and not row["confirmed_at"])
    check("when the invitation was sent is recorded", bool(row and row["confirm_sent_at"]))
    check("a send would skip them", not any(
        p["email"] == "someone@example.com" for p in subscribers.listing(db, confirmed_only=True)))

#  ------------------------------------------------------ the answer
SENT.clear()
path = confirm_url.split("localhost")[-1] if "localhost" in confirm_url else confirm_url
r = client.get(path)
check("following the link works", r.status_code == 200)
welcome = [m for m in SENT if m["to"] == "someone@example.com"]
check("confirming sends a welcome", len(welcome) == 1, "%d sent" % len(welcome))
unsubscribe_url = ""
if welcome:
    for word in welcome[0]["body"].split():
        if "/unsubscribe/" in word:
            unsubscribe_url = word
    check("the welcome carries an unsubscribe link", bool(unsubscribe_url))
    check("and carries it in the headers too",
          "List-Unsubscribe" in welcome[0]["headers"]
          and "One-Click" in welcome[0]["headers"].get("List-Unsubscribe-Post", ""))

#  Following it twice must not send a second welcome or read as a failure.
SENT.clear()
check("the link is safe to follow twice", client.get(path).status_code == 200 and not SENT)

with app.app_context():
    db = get_db()
    row = db.execute("SELECT * FROM subscribers WHERE email = 'someone@example.com'").fetchone()
    check("confirmed, and where from is recorded", bool(row["confirmed_at"]) and bool(row["confirm_ip"]))
    check("a send would now include them", any(
        p["email"] == "someone@example.com" for p in subscribers.listing(db, confirmed_only=True)))

#  ---------------------------------------------------------- leaving
upath = unsubscribe_url.split("localhost")[-1] if "localhost" in unsubscribe_url else unsubscribe_url
check("one-click unsubscribe (a POST) works", client.post(upath).status_code == 200)
with app.app_context():
    db = get_db()
    row = db.execute("SELECT * FROM subscribers WHERE email = 'someone@example.com'").fetchone()
    check("they are off the list and the row remains", bool(row) and bool(row["unsubscribed_at"]))
    check("a send skips them", not any(
        p["email"] == "someone@example.com" for p in subscribers.listing(db, confirmed_only=True)))

    #  ------------------------------------------------------ the record
    csv_text = subscribers.export_csv(db)
    head = csv_text.splitlines()[0]
    for column in ("signed up", "signed up from (IP)", "what they agreed to",
                   "confirmation sent", "confirmed", "confirmed from (IP)",
                   "status", "unsubscribed"):
        check("the record has a column for: %s" % column, column in head)

    #  --------------------------------------------------------- erasing
    victim = db.execute("SELECT id FROM subscribers WHERE email = 'someone@example.com'").fetchone()
    subscribers.erase(db, victim["id"])
    db.commit()
    check("erasing removes them completely", db.execute(
        "SELECT 1 FROM subscribers WHERE email = 'someone@example.com'").fetchone() is None)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (26, len(failures)))
if failures:
    print("failed:", ", ".join(failures))
sys.exit(1 if failures else 0)
