"""Writes a newsletter, aims it, previews it and sends it — on its own site.

A newsletter is a page you can also post, and the things that can go
wrong with it are all "the page and the email disagree": the email goes
out with a link to a page nobody can read, or with three old issues
attached to the new one, or the preview shows something other than what
sends. So this walks the whole thing with the mail captured rather than
sent, on a throwaway site, and asks the questions an owner would:

  * does a new Newsletter page arrive with something to type over?
  * is it an ordinary page -- on the site or not, as chosen?
  * can a send be aimed at everything, at the latest, or at one section?
  * does the preview show exactly what the send would post?
  * does a page kept off the site leave the "read it online" link out?

Run inside the container:

    docker compose exec -T web python /tmp/nc.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="newsletter-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import mailer                                        # noqa: E402
from app.services import newsletter, subscribers              # noqa: E402

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = lambda settings, to, subject, html, text, from_name=None, headers=None: \
    SENT.append({"to": to, "subject": subject, "html": html, "text": text})

failures = []


def check(name, ok, detail=""):
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


app = create_app()
client = app.test_client()

with app.app_context():
    db = get_db()
    for key, value in (("legal_business", "Test Bakery GmbH"),
                       ("legal_address", "Bahnhofstrasse 1\n8001 Zurich"),
                       ("site_title", "Test Bakery")):
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    #  A fresh site refuses every admin screen until the password it
    #  generated has been replaced -- rightly, and it would silently
    #  redirect every request below. This site exists for ten seconds and
    #  is thrown away, so the flag is simply cleared.
    from app import bootstrap
    bootstrap.clear_generated_password_flag(db)
    #  One confirmed subscriber, the honest way: through the service.
    status, token = subscribers.add(db, "reader@example.com", "Yes please.", source="/", ip="1.2.3.4")
    subscribers.confirm(db, token, ip="1.2.3.4")
    db.commit()

with client.session_transaction() as s:
    s["user_id"] = uid

#  ------------------------------------------------- made like any page
r = client.post("/admin/pages/new", data={"title": "March issue", "page_layout": "newsletter"},
                headers={"Origin": "http://localhost"})
check("a Newsletter page can be created", r.status_code in (302, 200))
with app.app_context():
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE slug = 'march-issue'").fetchone()
    check("it exists", page is not None)
    rows = db.execute("SELECT * FROM sections WHERE page_id = ? ORDER BY position",
                      (page["id"],)).fetchall()
    check("it arrives with something to type over", len(rows) == 1 and "Write your issue" in rows[0]["content"])
    check("that something is a Text tool, not an embed", rows[0]["type"] == "text")
    check("it is on the site by default", bool(page["is_public"]))
    check("it is offered in the page pickers like any page", any(
        p["slug"] == "march-issue" for p in db.execute(
            "SELECT slug FROM pages WHERE is_public = 1").fetchall()))
    #  Two more sections, so "which part" means something. Written a
    #  moment apart so "latest" has an answer that is not a coin toss.
    db.execute("INSERT INTO sections (page_id, type, title, content, position) "
               "VALUES (?, 'text', 'Second', '<p>The second thing.</p>', 1)", (page["id"],))
    db.execute("INSERT INTO sections (page_id, type, title, content, position) "
               "VALUES (?, 'text', 'Third', '<p>The third thing.</p>', 2)", (page["id"],))
    db.commit()
    db.execute("UPDATE sections SET title = 'Second' WHERE page_id = ? AND position = 1", (page["id"],))
    db.commit()
    page_id = page["id"]
    #  The same columns the app's own query asks for -- including
    #  changed_seq, which is what "last changed" actually means now. A
    #  checker that asks a different question checks a different app.
    all_rows = db.execute("SELECT id, type, title, content, updated_at, changed_seq "
                          "FROM sections WHERE page_id = ? ORDER BY position",
                          (page_id,)).fetchall()
    check("every section knows when it changed", all(r["updated_at"] for r in all_rows))
    check("touching one moves its stamp to the front",
          max(all_rows, key=newsletter._changed_key)["title"] == "Second")

    #  --------------------------------------------------- aiming a send
    whole, what_all = newsletter.sections_for(all_rows, "all")
    latest, what_latest = newsletter.sections_for(all_rows, "latest")
    one, what_one = newsletter.sections_for(all_rows, str(all_rows[2]["id"]))
    check("'everything' means every section", len(whole) == 3, str(len(whole)))
    check("'latest' means the one that changed last",
          len(latest) == 1 and latest[0]["title"] == "Second", what_latest)
    check("'latest' says which one it picked", what_latest == "section 2 of 3", what_latest)
    check("a section can be picked by number", len(one) == 1 and one[0]["title"] == "Third", what_one)
    check("an id that is not on the page sends everything rather than nothing",
          len(newsletter.sections_for(all_rows, "99999")[0]) == 3)
    choices = newsletter.choices_for(all_rows)
    check("the menu offers everything, latest, and one line per section",
          [c[0] for c in choices][:2] == ["all", "latest"] and len(choices) == 5,
          str([c[0] for c in choices]))
    check("a section with no name is named by its own first words",
          "Hello" in choices[2][1], choices[2][1])

#  ------------------------------------------- the bar, on the page itself
client.get("/admin/view-mode/editing?next=/")
html = client.get("/march-issue").get_data(as_text=True)
check("the page carries its own send bar while editing", "cms-newsletter-bar" in html)
check("with a subject, a choice, a preview and a send",
      all(s in html for s in ('name="subject"', 'name="parts"',
                              "cms-newsletter-preview", "cms-newsletter-send")))
check("and it says who it would go to", "1 person on the list" in html)
client.get("/admin/view-mode/viewing?next=/")
check("a visitor's copy of the page has no send bar",
      "cms-newsletter-bar" not in client.get("/march-issue").get_data(as_text=True))

#  ------------------------------------------------------ preview = send
preview_all = client.get("/admin/newsletters/%d/preview?parts=all" % page_id).get_data(as_text=True)
preview_latest = client.get("/admin/newsletters/%d/preview?parts=latest" % page_id).get_data(as_text=True)
check("the preview of 'everything' has all three", preview_all.count("thing.</p>") == 2
      and "Write your issue" in preview_all)
check("the preview of 'latest' has only that one",
      "The second thing." in preview_latest and "The third thing." not in preview_latest)
check("the preview offers to read it online", "read it in your browser" in preview_all.lower()
      or "march-issue" in preview_all)

#  ------------------------------------------------------------ sending
SENT.clear()
r = client.post("/admin/newsletters/%d/send" % page_id,
                data={"subject": "March", "parts": "latest", "next": "/march-issue"},
                headers={"Origin": "http://localhost"})
check("sending lands back on the page it was sent from",
      r.status_code == 302 and r.headers["Location"].endswith("/march-issue"),
      r.headers.get("Location", ""))
check("one message went out", len(SENT) == 1, str(len(SENT)))
if SENT:
    check("with the subject that was typed", SENT[0]["subject"] == "March")
    check("carrying only the part that was aimed at",
          "The second thing." in SENT[0]["html"] and "The third thing." not in SENT[0]["html"])
    check("and an unsubscribe link", "/unsubscribe/" in SENT[0]["html"])

#  --------------------------------------------- a page kept off the site
with app.app_context():
    get_db().execute("UPDATE pages SET is_public = 0 WHERE id = ?", (page_id,))
    get_db().commit()
SENT.clear()
client.post("/admin/newsletters/%d/send" % page_id,
            data={"subject": "March again", "parts": "all"},
            headers={"Origin": "http://localhost"})
check("a private page still sends", len(SENT) == 1)
if SENT:
    check("but promises no online copy", "march-issue" not in SENT[0]["html"])
gone = client.get("/march-issue")
check("its owner can still open it", gone.status_code == 200)
visitor = app.test_client()
check("a visitor is told there is no such page", visitor.get("/march-issue").status_code == 404)
with app.app_context():
    check("and it is not in the archive",
          "March issue" not in client.get("/newsletters").get_data(as_text=True))
    check("nor offered as a link on other pages", not any(
        p["slug"] == "march-issue" for p in get_db().execute(
            "SELECT slug FROM pages WHERE is_public = 1").fetchall()))

#  ------------------------------------------- everyone, or the customers
with app.app_context():
    db = get_db()
    db.execute("UPDATE pages SET is_public = 1 WHERE id = ?", (page_id,))
    #  A second subscriber, and one paid order under the FIRST one's
    #  address -- so exactly one of the two is a customer, by the orders
    #  rather than by anybody's say-so.
    status, t2 = subscribers.add(db, "browser@example.com", "Yes please.", source="/", ip="1.2.3.4")
    subscribers.confirm(db, t2, ip="1.2.3.4")
    cur = db.execute("INSERT INTO customers (email, name) VALUES ('Reader@Example.com', 'Reader')")
    db.execute("INSERT INTO orders (provider, provider_ref, customer_id, amount_total, currency, status) "
               "VALUES ('stripe', 'x1', ?, 2000, 'chf', 'paid')", (cur.lastrowid,))
    db.commit()
    counts = subscribers.counts(db)
    check("both people are on the list", counts["active"] == 2, str(counts))
    check("one of them is a customer, worked out from an order", counts["customers"] == 1, str(counts))
    check("the match ignores the case the address was typed in",
          [p["email"] for p in subscribers.listing(db, confirmed_only=True, audience="customers")]
          == ["reader@example.com"])
    #  A refund takes it back.
    db.execute("UPDATE orders SET status = 'refunded'")
    db.commit()
    check("a refunded order stops counting", subscribers.counts(db)["customers"] == 0)
    db.execute("UPDATE orders SET status = 'paid'")
    #  And the owner's own flag adds somebody the orders never saw.
    other = db.execute("SELECT id FROM subscribers WHERE email = 'browser@example.com'").fetchone()
    subscribers.set_customer_flag(db, other["id"], True)
    db.commit()
    check("flagging by hand adds somebody the orders never saw",
          subscribers.counts(db)["customers"] == 2)
    subscribers.set_customer_flag(db, other["id"], False)
    db.commit()
    buyer = db.execute("SELECT id FROM subscribers WHERE email = 'reader@example.com'").fetchone()
    subscribers.set_customer_flag(db, buyer["id"], False)
    db.commit()
    check("unflagging somebody who really did buy leaves them a customer",
          subscribers.counts(db)["customers"] == 1)

SENT.clear()
client.post("/admin/newsletters/%d/send" % page_id,
            data={"subject": "Regulars only", "parts": "all", "audience": "customers"},
            headers={"Origin": "http://localhost"})
check("a send to customers reaches only them",
      [m["to"] for m in SENT] == ["reader@example.com"], str([m["to"] for m in SENT]))
SENT.clear()
client.post("/admin/newsletters/%d/send" % page_id,
            data={"subject": "Everyone", "parts": "all", "audience": "all"},
            headers={"Origin": "http://localhost"})
check("a send to everyone reaches both", sorted(m["to"] for m in SENT) ==
      ["browser@example.com", "reader@example.com"], str([m["to"] for m in SENT]))

with app.app_context():
    db = get_db()
    hist = newsletter.history(db, "page", page_id)
    check("the history remembers which audience each send was for",
          [h["audience"] for h in hist][:2] == ["all", "customers"],
          str([h["audience"] for h in hist]))
    #  Nobody to send to is said as the thing that is true.
    db.execute("UPDATE orders SET status = 'refunded'")
    db.commit()
    r = client.post("/admin/newsletters/%d/send" % page_id,
                    data={"subject": "x", "audience": "customers"},
                    headers={"Origin": "http://localhost"})
    check("with no customers, a customers-only send refuses and says why",
          r.status_code == 302)
    csv_text = subscribers.export_csv(db)
    check("the export says who is a customer and how much they bought",
          "customer" in csv_text.splitlines()[0] and "orders paid" in csv_text.splitlines()[0])

#  ------------------------------------------------- a post as an issue
from app.services import blog as blog_service                 # noqa: E402

with app.app_context():
    db = get_db()
    db.execute("UPDATE orders SET status = 'paid'")
    blog_id = blog_service.create_blog(db, "Journal")
    db.execute("INSERT INTO blog_posts (blog_id, title, slug, excerpt, content, position) "
               "VALUES (?, 'A quiet week', 'a-quiet-week', 'Short one.', "
               "'We baked bread.' || char(10) || char(10) || 'Then we went home.', 0)",
               (blog_id,))
    db.commit()
    post = db.execute("SELECT * FROM blog_posts WHERE slug = 'a-quiet-week'").fetchone()
    post_id = post["id"]
    check("a post starts as a draft", not post["published_at"])

preview = client.get("/admin/newsletters/post/%d/preview" % post_id).get_data(as_text=True)
check("a post can be previewed as an email", "We baked bread." in preview
      and "Then we went home." in preview)
check("its plain-text paragraphs become real paragraphs", preview.count("<p") >= 2)
check("a draft's preview promises no online copy", "a-quiet-week" not in preview)

SENT.clear()
r = client.post("/admin/newsletters/post/%d/send" % post_id,
                data={"subject": "This week", "audience": "all"},
                headers={"Origin": "http://localhost"})
check("sending a post works", r.status_code == 302 and len(SENT) == 2, str(len(SENT)))
with app.app_context():
    db = get_db()
    post = db.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,)).fetchone()
    check("a draft is published first, so the link works", bool(post["published_at"]))
if SENT:
    check("the email carries the post", "We baked bread." in SENT[0]["html"])
    check("and now offers to read it online", "a-quiet-week" in SENT[0]["html"])
    check("with the subject that was typed", SENT[0]["subject"] == "This week")

with app.app_context():
    db = get_db()
    last = newsletter.last_send(db, "post", post_id)
    check("the send is recorded against the POST, not a page",
          last is not None and last["target_kind"] == "post" and last["target_id"] == post_id)
    hist = newsletter.history(db)
    check("the history names the post", any(h["title"] == "A quiet week" for h in hist))
    check("and still names the page sends beside it", any(h["target_kind"] == "page" for h in hist))
    #  The record outlives what it was sent from.
    db.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
    db.commit()
    hist = newsletter.history(db)
    check("deleting the post keeps the record of having sent it",
          any(h["target_kind"] == "post" and h["subject"] == "This week" for h in hist))

#  --------------------------------- the greeting, and what cannot be edited
r = client.post("/admin/newsletters/wrapper",
                data={"newsletter_intro": "Hello there.\n\nHere is {{title}}.",
                      "newsletter_outro": "Thanks for reading.\nSee you next month."},
                headers={"Origin": "http://localhost"})
check("the greeting and sign-off can be saved", r.status_code == 302)

preview = client.get("/admin/newsletters/%d/preview?parts=all" % page_id).get_data(as_text=True)
check("the greeting opens the email", preview.index("Hello there.") < preview.index("Write your issue"))
check("the sign-off closes it", preview.index("Thanks for reading.") > preview.index("Write your issue"))
check("a blank line makes a second paragraph",
      preview.count("<p style=") >= 2 and "Here is" in preview)
check("{{title}} becomes the subject", "Here is March issue." in preview)
check("a single line break is a line break, not a paragraph",
      "Thanks for reading.<br>See you next month." in preview)
check("the sender line is still added underneath", "Test Bakery GmbH" in preview)
check("and the unsubscribe line with it", "Unsubscribe" in preview)

SENT.clear()
client.post("/admin/newsletters/%d/send" % page_id,
            data={"subject": "March", "parts": "all", "audience": "all"},
            headers={"Origin": "http://localhost"})
if SENT:
    check("what was sent carries them too", "Hello there." in SENT[0]["html"]
          and "Thanks for reading." in SENT[0]["html"])
    check("and the text half says the same", "Hello there." in SENT[0]["text"]
          and "Thanks for reading." in SENT[0]["text"])

#  ------------------------------------------------ in the site's own colours
with app.app_context():
    db = get_db()
    #  A site with nothing active has no colours to borrow, which is a
    #  real state (a fresh install) and not what this part is testing.
    tpl = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    if not tpl:
        tpl = db.execute("SELECT * FROM templates ORDER BY id LIMIT 1").fetchone()
        if tpl:
            db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (tpl["id"],))
    check("there is a template to take colours from", tpl is not None)
    db.execute("UPDATE templates SET palette_json = ?, color_overrides = NULL WHERE id = ?",
               ('[{"slug": "primary", "name": "Primary", "color": "#8a1b3d"}]', tpl["id"]))
    db.commit()

#  A link, because the accent is spent on links, headings and rules --
#  a letter with no link in it has nowhere to show a colour.
with app.app_context():
    db = get_db()
    db.execute("INSERT INTO sections (page_id, type, title, content, position) "
               "VALUES (?, 'text', '', ?, 9)",
               (page_id, '<p>Read <a href="https://example.com">this</a>.</p>'))
    db.commit()
coloured = client.get("/admin/newsletters/%d/preview?parts=all" % page_id).get_data(as_text=True)
check("a link is drawn in the site's own colour", "color:#8a1b3d" in coloured,
      "accent missing")
check("the ground behind the card is a wash of it",
      "#f4f6f8" not in coloured, "still the stock grey")
check("it stays a light card whatever the site does",
      "background:#ffffff" in coloured.replace(" ", ""))
with app.app_context():
    db = get_db()
    tpl = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    db.execute("UPDATE templates SET color_overrides = ? WHERE id = ?",
               ('{"primary": "#0f5132"}', tpl["id"]))
    db.commit()
recoloured = client.get("/admin/newsletters/%d/preview?parts=all" % page_id).get_data(as_text=True)
check("an owner's own colour override wins",
      "color:#0f5132" in recoloured and "#8a1b3d" not in recoloured)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (67, len(failures)))
if failures:
    print("failed:", ", ".join(failures))
sys.exit(1 if failures else 0)
