"""The words an owner writes reach the messages that go out on their own.

Four messages send themselves — an order lands, somebody signs up,
somebody confirms — so nobody is watching when they are wrong. The
failure this is the net under is quiet in both directions: a greeting
that never arrives, and a FACT that an owner managed to delete.

Walked with the mail captured rather than sent, on a throwaway site:

  * does what the owner wrote actually reach the message?
  * do the facts survive, whatever the owner wrote?
  * is a placeholder this app cannot fill left visible rather than
    becoming a blank?
  * does the preview show the same words the real thing sends?

Run inside the container:

    docker compose exec -T web python tools/site_emails_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="site-emails-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import mailer                                        # noqa: E402
from app.services import site_emails, subscribers             # noqa: E402

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = lambda settings, to, subject, html, text, from_name=None, headers=None: \
    SENT.append({"to": to, "subject": subject, "html": html, "text": text})

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

with app.test_request_context("/"):
    db = get_db()

    print()
    print("Every message this site sends on its own is here")
    print("-" * 70)
    check("four of them, in a fixed order",
          sorted(site_emails.ORDER) == sorted(site_emails.MESSAGES),
          str(site_emails.ORDER))
    for key in site_emails.ORDER:
        spec = site_emails.MESSAGES[key]
        check("%s: says when it goes and what it always says" % key,
              bool(spec["name"] and spec["when"] and spec["fixed"]))
        check("%s: every placeholder says what it means" % key,
              all(p["name"] and p["means"] for p in spec["placeholders"]))

    print()
    print("What the owner writes reaches the message")
    print("-" * 70)
    site_emails.save(db, "order", "Hello from {{site}}!", "Any questions, just reply.")
    db.commit()
    got = site_emails.wrap(db, "order", "THE FACTS",
                           {"site": "Flour & Salt", "link": "https://x.test"})
    check("the greeting arrives, filled in", got.startswith("Hello from Flour & Salt!"), got)
    check("the facts are still in the middle", "THE FACTS" in got, got)
    check("the sign-off arrives last", got.rstrip().endswith("just reply."), got)
    check("nothing is run together",
          got.count(chr(10) * 2) == 2, repr(got))

    #  An empty half must cost nothing -- not a gap at the top.
    site_emails.save(db, "order", "", "Bye.")
    db.commit()
    empty = site_emails.wrap(db, "order", "THE FACTS", {})
    check("an empty greeting leaves no gap", empty.startswith("THE FACTS"), repr(empty))

    print()
    print("A placeholder this app cannot fill is visible, not blank")
    print("-" * 70)
    #  A blank is a mistake nobody notices until a customer asks; the
    #  literal braces are one somebody can see and fix.
    odd = site_emails.fill("Hello {{site}}, about {{discount}}", {"site": "Flour"})
    check("the known one is filled", "Hello Flour" in odd, odd)
    check("the unknown one stays visible", "{{discount}}" in odd, odd)

    print()
    print("The facts survive whatever the owner writes")
    print("-" * 70)
    #  There is no field that can remove them: the owner writes AROUND a
    #  body the code renders. Proved by writing nonsense in both halves
    #  and finding the body intact.
    for key in site_emails.ORDER:
        site_emails.save(db, key, "x", "y")
    db.commit()
    for key, must in (("order", "https://your.site"),
                      ("confirm", "confirm"),
                      ("subscribed", "Unsubscribe")):
        body = {"order": "Everything is here:" + chr(10) + "https://your.site/a",
                "confirm": "To confirm, open this link:",
                "subscribed": "Unsubscribe: https://your.site/u"}[key]
        out = site_emails.wrap(db, key, body, site_emails.SAMPLE)
        check("%s: its own facts are untouched" % key, must.lower() in out.lower(), out)

    print()
    print("The preview shows what would really be sent")
    print("-" * 70)
    site_emails.save(db, "subscribed", "Lovely to have you, {{site}}.", "")
    db.commit()
    shown = site_emails.preview(db, "subscribed", "THE FACTS")
    live = site_emails.wrap(db, "subscribed", "THE FACTS", site_emails.SAMPLE)
    check("the preview is the same words, filled the same way", shown == live, shown)
    check("...against believable data, not the placeholders repeated back",
          "{{" not in shown, shown)

    print()
    print("It refuses what it cannot send, and can be put back")
    print("-" * 70)
    ok_, error = site_emails.save(db, "not-a-message", "a", "b")
    check("a message this site does not send is refused", not ok_ and error, str(error))
    site_emails.reset(db, "order")
    db.commit()
    back = site_emails.wording(db, "order")
    check("resetting restores the standard wording",
          back[0] == site_emails.MESSAGES["order"]["intro_default"], str(back))
    #  Deleting is a choice, and different from never having touched it.
    site_emails.save(db, "order", "", "")
    db.commit()
    check("an owner who deletes the greeting gets no greeting",
          site_emails.wording(db, "order")[0] == "",
          str(site_emails.wording(db, "order")))

    print()
    print("The live senders go through it")
    print("-" * 70)
    #  A statement about the code: every one of the four had its own
    #  hardcoded body and now wraps it, and a fifth added later that
    #  forgot to would be invisible from here otherwise.
    public = open("/app/app/routes/public.py", encoding="utf-8").read()
    for key in site_emails.ORDER:
        check("%s is wrapped where it is sent" % key,
              'site_emails.wrap(' in public and '"%s"' % key in public)
    check("the screen exists and is reachable",
          "site_emails" in open("/app/app/templates/partials/email_tabs.html",
                                encoding="utf-8").read())

    #  The screen shows the MESSAGE, not a description of it. It was two
    #  textareas and a collapsed preview, which asked somebody to hold
    #  three things at once: what they were typing, where it would land,
    #  and what it would look like there.
    screen = open("/app/app/templates/admin/site_emails.html",
                  encoding="utf-8").read()
    check("each message is shown in the card it arrives in",
          "cms-issue-canvas" in screen)
    check("...the owner's parts written into directly",
          'contenteditable="true"' in screen and "data-wording" in screen)
    check("...and the code's parts greyed and inert",
          "cms-wording-fixed" in screen)
    css = open("/app/app/static/css/admin.css", encoding="utf-8").read()
    check("greyed really means it cannot be clicked",
          ".cms-wording-fixed { opacity" in css and "pointer-events: none" in css)
    #  Grey carries it for somebody who notices grey. A person who does
    #  not should not have to hover to find out which half is theirs.
    check("...and it is said in words, not only in grey",
          "cms-wording-note" in screen
          and "The greyed lines are written for you" in screen)
    check("the sender line is shown so nobody writes it twice",
          "cms-issue-canvas-foot" in screen)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
