"""Sending a newsletter later actually sends it, once.

A scheduled send is the hardest thing in this app to be sure of by
looking: it happens on a background thread, in a process nobody is
watching, in TWO gunicorn workers at the same time. The failure it
invites is mailing everybody twice, and you find out from your readers.

So this walks the whole path with the mail captured rather than sent, on
a throwaway site, and asks the questions an owner would:

  * does a job put on the clock come off it at the right time, and not
    before?
  * if two workers wake up together, does exactly ONE of them send?
  * does it make the same refusals a live send makes -- no email set up,
    nobody on the list, no postal address -- rather than mailing anyway?
  * does a failure get written down instead of retried?
  * does cancelling work, and does it stop pretending once it is too
    late?

Run inside the container:

    docker compose exec -T web python tools/schedule_check.py
"""
import datetime
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="schedule-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                        # noqa: E402
from app.db import get_db                                         # noqa: E402
from app import mailer                                            # noqa: E402
from app.services import (email_layouts, newsletter, scheduling,   # noqa: E402
                          site, subscribers)

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = lambda settings, to, subject, html, text, from_name=None, headers=None: \
    SENT.append({"to": to, "subject": subject})

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


def make_newsletter(db, subject="A scheduled one"):
    nid = newsletter.create_composed(db, "letter", subject=subject)
    newsletter.save_blocks(db, nid, subject, [
        {"type": "heading", "text": "Hello", "level": 2, "style": {}},
        {"type": "text", "text": "Something worth reading.", "style": {}},
    ])
    return nid


def confirmed(db, address):
    subscribers.add(db, address, "Yes please", "/", ip="127.0.0.1")
    db.execute("UPDATE subscribers SET confirmed_at = CURRENT_TIMESTAMP WHERE email = ?",
               (address,))


with app.app_context():
    db = get_db()

    print()
    print("The clock: what is typed is local, what is stored is UTC")
    print("-" * 70)
    #  60 minutes west of UTC: 13:00 there is 14:00 UTC.
    got = scheduling.to_utc("2027-03-01T13:00", 60)
    check("a local time is stored as UTC",
          got == datetime.datetime(2027, 3, 1, 14, 0, tzinfo=datetime.timezone.utc), str(got))
    check("the other direction too",
          scheduling.to_utc("2027-03-01T13:00", -120)
          == datetime.datetime(2027, 3, 1, 11, 0, tzinfo=datetime.timezone.utc))
    check("a time this app cannot read is refused, not guessed",
          scheduling.to_utc("next tuesday", 0) is None)
    check("...and so is an empty one", scheduling.to_utc("", 0) is None)

    print()
    print("Nothing goes early, and nothing goes twice")
    print("-" * 70)
    setting(db, "site_title", "Check Co")
    for key, value in (("legal_business", "Check Co"), ("legal_address", "1 Test Street"),
                       ("legal_city", "Testville"), ("legal_country", "Testland")):
        setting(db, key, value)
    site.set_base(db, "https://check.example")
    confirmed(db, "reader@example.test")
    db.commit()

    nid = make_newsletter(db)
    later = scheduling.utcnow() + datetime.timedelta(hours=2)
    scheduling.schedule(db, "newsletter", nid, "A scheduled one", "all", later)
    db.commit()

    check("it is waiting", scheduling.pending_for(db, "newsletter", nid) is not None)
    check("nothing is due yet", scheduling.due(db) == [])

    #  Bring it forward rather than waiting two hours.
    db.execute("UPDATE newsletter_schedule SET send_at = ? WHERE target_id = ?",
               (scheduling._stamp(scheduling.utcnow() - datetime.timedelta(minutes=1)), nid))
    db.commit()
    rows = scheduling.due(db)
    check("now it is due", len(rows) == 1, str(len(rows)))

    #  The whole point: two workers wake together and both try to take it.
    first = scheduling.claim(db, rows[0]["id"])
    second = scheduling.claim(db, rows[0]["id"])
    check("the first worker takes it", first)
    check("the second one cannot", not second)
    check("...and it is no longer due to anybody", scheduling.due(db) == [])

    from app.routes.admin.newsletters import _run_scheduled
    SENT[:] = []
    _run_scheduled(app, rows[0])
    check("it was sent, once, to the one confirmed reader",
          len(SENT) == 1 and SENT[0]["to"] == "reader@example.test", str(SENT))
    check("with the subject it was given",
          SENT and SENT[0]["subject"] == "A scheduled one", str(SENT[:1]))

    done = db.execute("SELECT * FROM newsletter_schedule WHERE id = ?",
                      (rows[0]["id"],)).fetchone()
    check("the job is written down as done", done["done_at"] is not None)
    check("...with how many it reached", done["sent"] == 1, str(done["sent"]))
    check("...and no error", not done["error"], str(done["error"]))
    check("and the send is on the permanent record",
          newsletter.last_send(db, "newsletter", nid) is not None)

    print()
    print("It refuses for the same reasons a live send refuses")
    print("-" * 70)

    def run_fresh(**broken):
        """One scheduled job under some broken condition. Returns its row."""
        nid2 = make_newsletter(db, "Refusal test")
        scheduling.schedule(db, "newsletter", nid2, "Refusal test", "all",
                            scheduling.utcnow() - datetime.timedelta(minutes=1))
        db.commit()
        row = scheduling.due(db)[0]
        scheduling.claim(db, row["id"])
        SENT[:] = []
        was = {}
        for key, value in broken.items():
            was[key] = db.execute("SELECT value FROM settings WHERE key = ?",
                                  (key,)).fetchone()
            setting(db, key, value)
        db.commit()
        _run_scheduled(app, row)
        for key, old in was.items():
            setting(db, key, old["value"] if old else "")
        db.commit()
        return db.execute("SELECT * FROM newsletter_schedule WHERE id = ?",
                          (row["id"],)).fetchone()

    no_address = run_fresh(legal_address="", legal_city="", legal_country="")
    check("no postal address: nothing is sent", not SENT, str(SENT))
    check("...and the reason is written down where a person will see it",
          no_address["error"] and "postal address" in no_address["error"],
          str(no_address["error"]))

    no_base = run_fresh(site_public_url="")
    check("no site address: nothing is sent", not SENT, str(SENT))
    check("...because there would be nowhere to unsubscribe",
          no_base["error"] and "web address" in no_base["error"], str(no_base["error"]))

    #  A failure is never retried by itself -- it is done, with a reason.
    check("a failed job is finished, not left to go again",
          no_base["done_at"] is not None and scheduling.due(db) == [])

    print()
    print("Taking it back")
    print("-" * 70)
    nid3 = make_newsletter(db, "Cancel me")
    scheduling.schedule(db, "newsletter", nid3, "Cancel me", "all",
                        scheduling.utcnow() + datetime.timedelta(days=1))
    db.commit()
    check("cancelling removes it", scheduling.cancel(db, "newsletter", nid3) == 1)
    check("...and there is nothing left waiting",
          scheduling.pending_for(db, "newsletter", nid3) is None)

    nid4 = make_newsletter(db, "Too late")
    scheduling.schedule(db, "newsletter", nid4, "Too late", "all",
                        scheduling.utcnow() - datetime.timedelta(minutes=1))
    db.commit()
    scheduling.claim(db, scheduling.due(db)[0]["id"])
    check("a job already going out cannot be recalled",
          scheduling.cancel(db, "newsletter", nid4) == 0)

    print()
    print("Scheduling twice means the second time")
    print("-" * 70)
    nid5 = make_newsletter(db, "Twice")
    first_at = scheduling.utcnow() + datetime.timedelta(days=1)
    second_at = scheduling.utcnow() + datetime.timedelta(days=2)
    scheduling.schedule(db, "newsletter", nid5, "Twice", "all", first_at)
    scheduling.schedule(db, "newsletter", nid5, "Twice", "all", second_at)
    db.commit()
    waiting = db.execute(
        "SELECT COUNT(*) c FROM newsletter_schedule WHERE target_id = ? AND claimed_at IS NULL",
        (nid5,)).fetchone()["c"]
    check("there is one pending job, not two", waiting == 1, str(waiting))
    check("...and it is the later time",
          scheduling.pending_for(db, "newsletter", nid5)["send_at"]
          == scheduling._stamp(second_at))

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
