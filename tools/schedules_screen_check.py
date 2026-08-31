"""The times this site does things, in one place.

A schedule was defined on the Newsletters screen and again on the Blog
screen -- one list, two homes -- and picked on a third, Backups, which
could only offer what the other two happened to have made. Landing on
Backups first, you could see the picker and had no way to fill it.

So this asks the questions that arrangement failed:

  * is there ONE place the list lives, and is it gone from the others?
  * does a schedule made here reach every screen that picks one?
  * does the form remove what does not apply rather than greying it --
    the rule this app follows, and the one `hidden` quietly loses when
    a CSS rule sets a display?
  * does the screen say what is waiting on the clock, whatever kind of
    thing it is?

Usage:

    python tools/schedules_screen_check.py http://localhost:5000 <cookie-file>
"""
import io
import sys
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
COOKIE = open(sys.argv[2]).read().strip()
NAME = "Checker schedules screen"

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


def post(path, data):
    request = urllib.request.Request(
        BASE + path, data=urllib.parse.urlencode(data).encode(),
        headers={"Cookie": "session=" + COOKIE, "Origin": BASE,
                 "Referer": BASE + "/admin/schedules"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code


def settle(page):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(200)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": "localhost", "path": "/"}])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    print()
    print("One home for the list")
    print("-" * 68)
    page.goto(BASE + "/admin/schedules")
    settle(page)
    check("the screen exists", "Schedules" in page.title(), page.title())
    check("...and it makes them", page.evaluate(
        "() => !!document.querySelector('[data-schedule-form]')"))
    #  What is on the clock is the OTHER tab now: that list only grows,
    #  and it was sitting under the short list of times you change twice
    #  a year.
    check("...and points at what is waiting on them", page.evaluate(
        """() => [...document.querySelectorAll('nav.tabs a')]
             .some(a => a.textContent.trim() === 'Scheduled items')"""))

    #  The Dashboard is where you find it.
    page.goto(BASE + "/admin/")
    settle(page)
    check("the Dashboard has a button for it", page.evaluate(
        """() => [...document.querySelectorAll('a.btn')]
             .some(a => a.getAttribute('href') === '/admin/schedules')"""))

    for path, screen in (("/admin/newsletters", "Newsletters"),
                         ("/admin/blogs", "Blog")):
        page.goto(BASE + path)
        settle(page)
        check("%s no longer defines schedules" % screen, page.evaluate(
            """() => ![...document.querySelectorAll('h2')]
                 .some(h => h.textContent.trim() === 'Your schedules')"""))
        check("...and has no form for making one" , page.evaluate(
            "() => !document.querySelector('[data-schedule-form]')"))

    print()
    print("One made here reaches everywhere it is picked")
    print("-" * 68)
    post("/admin/schedules/save", {
        "name": NAME, "repeat_kind": "weekly", "weekday": "0",
        "hour": "9", "minute": "0", "tz_offset": "0", "month_day": "first"})
    page.goto(BASE + "/admin/schedules")
    settle(page)
    check("it is kept", NAME in page.evaluate("() => document.body.innerText"))
    check("...and says what it means in words", page.evaluate(
        """(n) => { const row = [...document.querySelectorAll('tbody tr')]
             .find(r => r.innerText.indexOf(n) >= 0);
             return row ? row.innerText.indexOf('Monday') >= 0 : false; }""", NAME))

    #  The whole point of moving it: a schedule made in one place is
    #  offered in all three, including the one that could never make one.
    for path, screen in (("/admin/newsletters", "the newsletter editor"),
                         ("/admin/backups", "the backups screen")):
        page.goto(BASE + path)
        settle(page)
        check("offered in %s" % screen, page.evaluate(
            """(n) => [...document.querySelectorAll('option')]
                 .some(o => o.textContent.indexOf(n) >= 0)""", NAME))

    print()
    print("The form removes what does not apply")
    print("-" * 68)
    #  `hidden` loses to a rule that gives the element a display: the
    #  labels are inline-flex, so every "hide what does not apply" set an
    #  attribute the CSS then overruled, and the fields sat there greyed
    #  instead of gone. Checked as "is it actually not displayed".
    page.goto(BASE + "/admin/schedules")
    settle(page)

    def gone(sel):
        return page.evaluate(
            """(s) => { const e = document.querySelector(s);
                 if (!e) return true;
                 const l = e.closest('[data-when]') || e;
                 return l.hidden && getComputedStyle(l).display === 'none'; }""",
            sel)

    page.select_option("#sched-repeat", "monthly")
    page.wait_for_timeout(250)
    check("monthly: the weekday is gone, not greyed", gone("#sched-weekday"))
    check("...and the day-of-month choice is there", not gone("#sched-monthday-kind"))
    page.select_option("#sched-repeat", "weekly")
    page.wait_for_timeout(250)
    check("weekly: the weekday is there", not gone("#sched-weekday"))
    check("...and the day of the month is gone", gone("#sched-monthday-kind"))
    page.select_option("#sched-repeat", "once")
    page.wait_for_timeout(250)
    check("once: a date and a time, and nothing else",
          not gone("#sched-when") and gone("#sched-hour") and gone("#sched-weekday"))

    #  The clock it was typed on travels with it, or "9am" is 9am UTC.
    #  RAW getTimezoneOffset, which is what `scheduling.to_utc` reads:
    #  "minutes to ADD to local to reach UTC". Two files were filling
    #  this same field with opposite signs -- local-time.js raw, the blog
    #  editor negated -- so a post scheduled for 14:00 in Zurich in
    #  summer was booked for 12:00 UTC instead of 16:00. Four hours
    #  early, silently.
    check("the browser's own clock is sent with it", page.evaluate(
        """() => { const f = document.querySelector('[data-tz-offset]');
             return !!f && f.value === String(new Date().getTimezoneOffset()); }"""),
          page.evaluate("() => { const f = document.querySelector('[data-tz-offset]');"
                        " return (f ? f.value : 'missing') + ' vs ' "
                        "+ String(new Date().getTimezoneOffset()); }"))
    check("...and its zone, not just its offset", page.evaluate(
        "() => { const f = document.querySelector('[data-tz-name]'); "
        "return !!f && f.value.length > 0; }"))

    print()
    print("Two tabs, because they are two questions")
    print("-" * 68)
    #  "What times do I have" is a short list you change twice a year.
    #  "What is on the clock" only ever grows: every send, every publish
    #  and every backup leaves a row, and a year of automatic backups is
    #  365 of them in front of the one thing you were looking for.
    page.goto(BASE + "/admin/schedules")
    settle(page)
    check("the screen has tabs", page.evaluate(
        "() => document.querySelectorAll('nav.tabs a.tab').length == 2"),
          page.evaluate("() => [...document.querySelectorAll('nav.tabs a')]"
                        ".map(a => a.textContent.trim()).join(' | ')"))
    check("...and they are links, so they can be bookmarked", page.evaluate(
        """() => [...document.querySelectorAll('nav.tabs a.tab')]
             .every(a => (a.getAttribute('href') || '').startsWith('/admin/'))"""))
    check("the waiting list is not on the schedules tab", page.evaluate(
        """() => ![...document.querySelectorAll('h2')]
             .some(h => h.textContent.trim() === 'What is waiting')"""))

    page.goto(BASE + "/admin/schedules/items")
    settle(page)
    check("the items tab exists", "Scheduled items" in page.title(), page.title())
    check("...and can be filtered", page.evaluate(
        "() => document.querySelectorAll('.cms-state-filter a').length >= 4"))
    for state in ("waiting", "failed", "done", "all"):
        page.goto(BASE + "/admin/schedules/items?state=" + state)
        settle(page)
        check("...%s is a real address" % state,
              ("state=" + state) in page.url and not page.evaluate(
                  "() => document.body.innerText.includes('Internal Server Error')"))

    print()
    print("An item can be taken off, and only when that is true")
    print("-" * 68)
    #  A claimed one is already going out and cannot be recalled --
    #  offering a button that would refuse is worse than offering none.
    page.goto(BASE + "/admin/schedules/items?state=waiting")
    settle(page)
    check("a waiting item offers a way off the clock", page.evaluate(
        """() => { const rows = [...document.querySelectorAll('tbody tr')];
             if (!rows.length) return true;
             return rows.every(r => !!r.querySelector('form[action*="/cancel"]')); }"""))
    page.goto(BASE + "/admin/schedules/items?state=done")
    settle(page)
    check("...and a finished one does not", page.evaluate(
        """() => [...document.querySelectorAll('tbody tr')]
             .every(r => !r.querySelector('form[action*="/cancel"]'))"""))
    check("...but the finished can be tidied away", page.evaluate(
        """() => { const rows = document.querySelectorAll('tbody tr').length;
             return !rows || !!document.querySelector('form[action*="/items/clear"]'); }"""))

    print()
    print("Deleting a schedule says what it does to what uses it")
    print("-" * 68)
    #  Reported: "if I delete an assigned schedule it doesn't warn of the
    #  assigned items, how are they impacted". Two different impacts, and
    #  the second is the quiet one -- backups store a schedule by NAME,
    #  so deleting it stops them without an error, because nothing failed.
    page.goto(BASE + "/admin/schedules")
    settle(page)
    row = page.evaluate(
        """(n) => { const r = [...document.querySelectorAll('tbody tr')]
             .find(x => x.innerText.indexOf(n) >= 0);
             if (!r) return null;
             const f = r.querySelector('form[action*="/schedules/delete"]');
             return { confirm: f ? f.getAttribute('data-confirm') : '',
                      uses: r.innerText,
                      edit: !!r.querySelector('a[href*="edit="]') }; }""", NAME)
    check("the row is there", row is not None)
    if row:
        check("...and says what is relying on it", "waiting" in row["uses"]
              or "\u2014" in row["uses"] or "-" in row["uses"], row["uses"][:70])
        check("...and the confirm names the consequence",
              "booked" in (row["confirm"] or "") or "Nothing is relying"
              in (row["confirm"] or ""), (row["confirm"] or "")[:110])
        #  The gap: add and delete existed, edit did not.
        check("...and it can be changed, not only added and removed",
              row["edit"], "no edit action on the row")

    page.goto(BASE + "/admin/schedules?edit=" + NAME.replace(" ", "+"))
    settle(page)
    check("editing prefills the form it is editing", page.evaluate(
        """(n) => { const f = document.querySelector('#sched-name');
             return !!f && f.value === n; }""", NAME))
    check("...and says it is changing rather than adding", page.evaluate(
        """() => [...document.querySelectorAll('button')]
             .some(b => b.textContent.trim() === 'Save changes')"""))
    check("...and carries the name it had, so a rename does not leave a twin",
          page.evaluate("() => !!document.querySelector('input[name=\"was\"]')"))

    print()
    print("Tidying up")
    print("-" * 68)
    post("/admin/schedules/delete", {"name": NAME})
    page.goto(BASE + "/admin/schedules")
    settle(page)
    check("removing one works", NAME not in page.evaluate("() => document.body.innerText"))

    check("no console errors", not errors, "; ".join(errors[:3]))
    browser.close()

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
sys.exit(1 if failures else 0)
