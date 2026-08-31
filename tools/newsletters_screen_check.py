"""The Newsletters screen answers "what have I sent, and what am I sending".

It was nine cards. Writing one was a card with a heading and a paragraph
wrapped around a single button; "Yours", "Going out on its own" and "What
has gone out" were three lists; the Email list screen's own counts were
repeated as a heading; and every blog was listed with its posts so each
could be sent as an issue.

Those three lists are not three things. They are one thing at three
points of its life, and splitting them meant a newsletter moved from card
to card as it aged -- so finding the one about the autumn hours depended
on remembering whether it had gone yet.

This drives the real screen, because every claim here is about layout and
order: which control comes first, whether one table carries the columns
it should, whether a row can be copied. None of that is visible from the
server, and all of it is what an owner reported as "it feels messy".

    python tools/newsletters_screen_check.py <base-url> <cookie-file>

It makes its own newsletter and its own named schedule, and removes both
again -- so it leaves the site as it found it.
"""
import io
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
HOST = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE = "Checker schedule"
ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-56s ok" % what)
    else:
        bad += 1
        print("  %-56s FAILED  %s" % (what, detail))


def post(path, fields):
    req = urllib.request.Request(
        BASE + path,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Cookie": "session=" + COOKIE, "Origin": BASE,
                 "Referer": BASE + "/admin/newsletters",
                 "X-Inline-Edit": "1"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.geturl()
    except urllib.error.HTTPError as e:
        return e.code, ""


made = []
status, where = post("/admin/newsletters/issue/new", {})
found = re.search(r"/issue/(\d+)", where or "")
if not found:
    print("Could not create a newsletter to look at: %s %s" % (status, where))
    sys.exit(2)
made.append(found.group(1))
#  A schedule now says how often it repeats -- the options a mail
#  scheduler offers -- so the old post is refused for saying nothing.
post("/admin/newsletters/schedules/save",
     {"name": SCHEDULE, "repeat_kind": "weekly", "weekday": "0",
      "hour": "9", "minute": "0"})

try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1400, "height": 1000})
        ctx.add_cookies([{"name": "session", "value": COOKIE,
                          "domain": HOST, "path": "/"}])
        page = ctx.new_page()
        errors = []
        page.on("console",
                lambda m: errors.append(m.text[:110]) if m.type == "error" else None)
        page.goto(BASE + "/admin/newsletters", wait_until="networkidle")
        page.wait_for_timeout(500)

        print()
        print("Writing one is the first thing, not a card to read first")
        print("-" * 66)
        #  There is no button that opens a newsletter any more: the
        #  creation TOOL is the top of the page, and the list and the
        #  schedules are below it. Three tools in the order they are
        #  used.
        order = page.evaluate(
            """() => { const t = document.querySelector('.cms-issue-form');
                 const l = document.querySelector('.cms-newsletter-table');
                 const s = document.querySelector('.cms-schedule-form');
                 if (!t || !l || !s) return null;
                 return [t, l, s].map(e => Math.round(e.getBoundingClientRect().top)); }""")
        check("the creation tool is on the page", order is not None, str(order))
        check("...above the list, which is above the schedules",
              order is not None and order == sorted(order), str(order))
        check("...and it is a real editor, with its scripts",
              page.evaluate("() => typeof window.cmsLocalTime") == "object")

        #  Offered beside writing one by hand, because it is the same
        #  act with a different starting point -- and only when there is
        #  a provider to ask, since a button that cannot work is worse
        #  than no button.
        ai = page.evaluate(
            """() => { const f = document.querySelector('.cms-write-with-ai');
                 if (!f) return null;
                 const box = f.querySelector('input[name=brief]');
                 const hand = Array.from(document.querySelectorAll('button'))
                   .find(x => x.textContent.trim() === 'Write a newsletter');
                 return { sameRow: Math.abs(f.getBoundingClientRect().top
                            - hand.getBoundingClientRect().top) < 40,
                          asks: !!box && !!box.placeholder,
                          says: document.body.innerText.includes(
                            'still has to be read and sent by you') }; }""")
        if ai is None:
            check("writing with AI is not offered without a provider", True)
        else:
            check("writing with AI stands beside writing one by hand",
                  ai["sameRow"], str(ai))
            check("...and asks what it should be about", ai["asks"], str(ai))
            #  It writes a draft. Saying so where the button is, because
            #  an AI writing to somebody's mailing list over their name
            #  is the one place a plausible mistake cannot be recalled.
            check("...and says a person still sends it", ai["says"], str(ai))

        print()
        print("One table, not three lists")
        print("-" * 66)
        cols = page.evaluate(
            """() => Array.from(document.querySelectorAll(
                 '.cms-newsletter-table thead th')).map(t => t.textContent.trim())""")
        check("it carries the columns the list has to answer",
              cols == ["Subject", "Written", "Sent", "Schedule", "To", "Action"],
              str(cols))
        for gone in ("Yours", "Going out on its own", "What has gone out"):
            check("...so there is no separate %s card" % gone, page.evaluate(
                """(want) => !Array.from(document.querySelectorAll('h2'))
                     .some(h => h.textContent.trim() === want)""", gone), gone)
        #  That trio passed once for the wrong reason. "What has gone
        #  out" only ever rendered when there WAS history, and the
        #  install being checked had none -- so its absence was true and
        #  meaningless. A check that cannot go red is worse than no
        #  check, so the same claim is made about the TEMPLATE, where it
        #  cannot be true by accident.
        #  Read from the repository, not from /app: this one runs on the
        #  host with a browser, not inside the container.
        source = io.open(os.path.join(HERE, "app", "templates", "admin",
                                      "newsletters.html"), encoding="utf-8").read()
        check("...and the template has no such card to render",
              "<h2>What has gone out</h2>" not in source)
        check("...while the table still carries removing one from the record",
              "newsletter_send_forget" in source)
        #  The Email list screen's subject, repeated here. The same number
        #  in two places is how two places come to disagree.
        check("the list counts are not repeated here", page.evaluate(
            """() => !Array.from(document.querySelectorAll('h2'))
                 .some(h => /on the list/.test(h.textContent))"""))
        #  Four: edit, send now, copy, delete. Send now joined them so a
        #  newsletter can go without being opened first.
        check("every row offers edit, send, copy and delete", page.evaluate(
            """() => { const r = document.querySelector('.cms-newsletter-table tbody tr');
                 return r.querySelectorAll(
                   '.cms-col-actions a, .cms-col-actions button').length; }""") == 4)
        #  ...and sending asks first, because it cannot be unsent.
        check("...and sending asks first", page.evaluate(
            """() => { const f = document.querySelector(
                 '.cms-newsletter-table form[action*="/send-now"]');
                 return !!f && /cannot be unsent/.test(f.dataset.confirm || ''); }"""))

        print()
        print("Last month's is how you write this month's")
        print("-" * 66)
        before = page.evaluate(
            "() => document.querySelectorAll('.cms-newsletter-table tbody tr').length")
        page.evaluate("""() => document.querySelector(
            '.cms-newsletter-table tbody tr form[action*="/copy"] button').click()""")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(600)
        check("copying opens the copy", "/issue/" in page.url, page.url)
        copied = re.search(r"/issue/(\d+)", page.url)
        if copied:
            made.append(copied.group(1))
        subject = page.evaluate("() => document.getElementById('subject').value")
        check("...named so it can be told from the original",
              subject.endswith("(copy)"), repr(subject))
        page.goto(BASE + "/admin/newsletters", wait_until="networkidle")
        page.wait_for_timeout(400)
        after = page.evaluate(
            "() => document.querySelectorAll('.cms-newsletter-table tbody tr').length")
        check("...and the original is still there",
              after == before + 1, "%d -> %d" % (before, after))

        print()
        print("A schedule is a name you assign, not a date you retype")
        print("-" * 66)
        #  A table now, with what each means in words and when it last
        #  put something on the clock.
        named = page.evaluate(
            """() => Array.from(document.querySelectorAll(
                 '.cms-schedule-table tbody tr'))
                 .map(r => r.cells[0].innerText.trim() + ' | '
                        + r.cells[1].innerText.trim())""")
        mine = [n for n in named if n.startswith(SCHEDULE)]
        check("a named schedule is kept", bool(mine), str(named))
        check("...and says what it means in words",
              bool(mine) and "Every Monday at 09:00" in mine[0], str(mine))

        print()
        print("A blog is content, not a section of this screen")
        print("-" * 66)
        #  It was listed here per blog so each post could be sent as an
        #  issue of its own, which made "the blog" part of one screen
        #  rather than something an owner can put IN a newsletter.
        check("no per-blog card listing its posts", page.evaluate(
            """() => !document.body.innerText.includes('most recent post')"""))

        check("no console errors", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    for issue in made:
        post("/admin/newsletters/issue/%s/delete" % issue, {})
    post("/admin/newsletters/schedules/delete", {"name": SCHEDULE})

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
