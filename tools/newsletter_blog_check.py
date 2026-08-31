"""A newsletter kept on the site, as well as sent.

A newsletter is written once and read once, in an inbox, by whoever was
on the list that day. Ticking "keep it on the site" publishes the same
words as a blog entry the moment the email goes -- so the question this
answers is whether the two really happen together, on BOTH paths, and
whether what lands on the site is a page's writing rather than an
email's.

The three things it would be easy to get wrong, and easy not to notice:

  * the copy is made by the button but not by the SCHEDULER, or the
    other way round -- silent either way, because the email arrives and
    nobody is looking at the blog on a Monday morning;
  * the entry carries the greeting and the sign-off, which are addressed
    to somebody who has just been written to and read as nonsense to
    somebody who finds the page in a search six weeks later;
  * the entry carries the EMAIL's inline styles, so one paragraph is
    pinned to 16px Arial in the middle of the site's own type.

Run inside the container:

    docker compose exec -T web python tools/newsletter_blog_check.py
"""
import datetime
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="nlblog-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                          # noqa: E402
from app.db import get_db                                           # noqa: E402
from app import mailer                                              # noqa: E402
from app.services import (blog as blog_service, newsletter,          # noqa: E402
                          scheduling, site, subscribers)

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = (
    lambda settings, to, subject, html, text, from_name=None, headers=None:
    SENT.append({"to": to, "subject": subject}))

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


app = create_app()


def setting(db, key, value):
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


BODY = [
    {"type": "text", "text": "Hello,", "style": {}, "role": "intro"},
    {"type": "heading", "text": "The **big** one", "level": 2, "style": {}},
    {"type": "text", "style": {},
     "text": "Two things happened.\n\n- One\n- Two\n\n"
             "Read [the notes](https://example.test/notes)."},
    {"type": "button", "label": "Book a table", "url": "https://example.test/book",
     "style": {}},
    {"type": "divider", "style": {}},
    {"type": "text", "text": "Thanks for reading.", "style": {}, "role": "exit"},
]


with app.app_context():
    db = get_db()
    setting(db, "site_title", "Keep Co")
    for key, value in (("legal_business", "Keep Co"), ("legal_address", "1 Test Street"),
                       ("legal_city", "Testville"), ("legal_country", "Testland")):
        setting(db, key, value)
    site.set_base(db, "https://keep.example")
    subscribers.add(db, "reader@example.test", "Yes please", "/", ip="127.0.0.1")
    db.execute("UPDATE subscribers SET confirmed_at = CURRENT_TIMESTAMP")
    blog_id = blog_service.create_blog(db, "News")
    db.commit()

    print()
    print("What lands on the site is a page's writing, not an email's")
    print("-" * 70)
    html = newsletter.page_html(BODY)
    check("the words are there", "Two things happened." in html, html[:120])
    check("a heading is a heading", "<h2>" in html and "big" in html)
    check("...and what was bold in the email is bold here",
          "<strong>big</strong>" in html, html[:200])
    check("a list is a list", "<ul>" in html and html.count("<li>") == 2, html[:200])
    check("a link survives", 'href="https://example.test/notes"' in html)
    check("a button is a link somebody can press",
          '<a class="btn" href="https://example.test/book">Book a table</a>' in html, html)
    check("a rule survives", "<hr>" in html)

    #  The whole reason this is not simply the email again.
    check("the opening is left out", "Hello," not in html, html[:160])
    check("the sign-off is left out", "Thanks for reading." not in html, html[-160:])

    #  An email is inline-styled because a client strips a stylesheet. A
    #  page HAS the stylesheet, and carrying those styles onto it pins
    #  one paragraph to 16px Arial in the middle of the site's own type.
    check("nothing carries the email's inline styles", "style=" not in html, html[:200])

    print()
    print("It is kept when it is sent, and not before")
    print("-" * 70)
    nid = newsletter.create_composed(db, "letter", "Monday news")
    newsletter.save_blocks(db, nid, "Monday news", BODY, blog_id=blog_id)
    db.commit()
    row = newsletter.get_composed(db, nid)
    check("the newsletter remembers which blog", row["blog_id"] == blog_id,
          str(row["blog_id"]))
    check("nothing is posted just for asking",
          len(blog_service.posts_for(db, blog_id, published_only=False)) == 0)

    made = newsletter.keep_as_post(db, blog_service, row)
    db.commit()
    posts = blog_service.posts_for(db, blog_id, published_only=False)
    check("sending it makes one entry", bool(made) and len(posts) == 1, str(len(posts)))
    check("...titled with the subject", posts[0]["title"] == "Monday news",
          posts[0]["title"])
    check("...published, not left as a draft", bool(posts[0]["published_at"]),
          repr(posts[0]["published_at"]))
    check("...dated the day it went",
          posts[0]["published_at"] == datetime.datetime.utcnow().strftime("%Y-%m-%d"),
          str(posts[0]["published_at"]))
    check("...and holding the newsletter's words",
          "Two things happened." in (posts[0]["content"] or ""))

    #  Two sends are two entries, and two entries must not collide on one
    #  address -- which is the whole reason create_post owns the slug.
    newsletter.keep_as_post(db, blog_service, row)
    db.commit()
    again = blog_service.posts_for(db, blog_id, published_only=False)
    check("a second send does not collide with the first",
          len({p["slug"] for p in again}) == len(again) == 2,
          ", ".join(p["slug"] for p in again))

    print()
    print("A newsletter that was not asked to be kept, is not")
    print("-" * 70)
    plain = newsletter.create_composed(db, "letter", "Just an email")
    newsletter.save_blocks(db, plain, "Just an email", BODY, blog_id=None)
    db.commit()
    check("no blog, no entry",
          newsletter.keep_as_post(
              db, blog_service, newsletter.get_composed(db, plain)) is None)

    #  Unticking has to be able to turn it OFF. The picker is disabled
    #  rather than absent for exactly this reason, and a save that only
    #  ever set the column would leave it on forever.
    newsletter.save_blocks(db, nid, "Monday news", BODY, blog_id=None)
    db.commit()
    check("unticking it turns it off",
          newsletter.get_composed(db, nid)["blog_id"] is None)

    #  A blog somebody deleted is not a crash.
    newsletter.save_blocks(db, nid, "Monday news", BODY, blog_id=blog_id)
    db.commit()
    blog_service.delete_blog(db, blog_id)
    db.commit()
    check("a blog that has been deleted is simply not written to",
          newsletter.keep_as_post(
              db, blog_service, newsletter.get_composed(db, nid)) is None)

    print()
    print("Both send paths do it, through one function")
    print("-" * 70)
    #  Source-level, deliberately: the failure this guards against is a
    #  path that never calls it, and a path that never calls it is
    #  invisible to any test of the path that does.
    routes = open("/app/app/routes/admin/newsletters.py", encoding="utf-8").read()
    check("the button's path keeps a copy", routes.count("_keep_a_copy(") >= 3,
          str(routes.count("_keep_a_copy(")))
    check("the scheduler's path keeps a copy",
          '_keep_a_copy(db, row["kind"], row["target_id"])' in routes)
    check("neither has its own copy of the rule",
          routes.count("keep_as_post(") == 1, str(routes.count("keep_as_post(")))
    check("...and it is only done when the send actually went",
          "if sent else None" in routes and "if sent:" in routes)

    print()
    print("The real thing: a scheduled send publishes as it sends")
    print("-" * 70)
    blog2 = blog_service.create_blog(db, "Journal")
    nid2 = newsletter.create_composed(db, "letter", "Scheduled and kept")
    newsletter.save_blocks(db, nid2, "Scheduled and kept", BODY, blog_id=blog2)
    scheduling.schedule(db, "newsletter", nid2, "Scheduled and kept", "all",
                        scheduling.utcnow() - datetime.timedelta(minutes=1))
    db.commit()

    from app.routes.admin.newsletters import _run_scheduled          # noqa: E402
    due = scheduling.due(db)
    check("the job is due", len(due) == 1, str(len(due)))
    #  claim() says WHETHER this worker got it, not what it got -- the
    #  claim is the lock, and exactly one worker can match. The row is
    #  the one that was due.
    check("this worker claims it", scheduling.claim(db, due[0]["id"]) is True)
    db.commit()
    _run_scheduled(app, due[0])

    db2 = get_db()
    check("the email went", any(m["subject"] == "Scheduled and kept" for m in SENT),
          str(SENT))
    kept = blog_service.posts_for(db2, blog2, published_only=False)
    check("and the entry is on the site", len(kept) == 1, str(len(kept)))
    if kept:
        body = kept[0]["content"] or ""
        check("...with the newsletter's words and none of its greeting",
              "Two things happened." in body and "Thanks for reading." not in body,
              body[:160])
        check("...published the day it was sent", bool(kept[0]["published_at"]))

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
shutil.rmtree(DATA_DIR, ignore_errors=True)
sys.exit(1 if failures else 0)
