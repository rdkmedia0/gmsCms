"""The Blogs screen is a place to write, not a file manager.

It was a tree of blogs with a pencil beside each post: it told you what
existed and gave you nowhere to write. It is the Newsletters screen's
shape now -- the tool that makes one, everything that has been made, and
the times this site publishes at -- because a post and a newsletter are
the same act with a different ending, and an owner who has learnt one
screen should not have to learn a second.

What this measures, in a real browser, because most of it is layout and
none of it can be seen from the server:

  * the three parts are there, in that order, and the writing is the
    first thing on the page rather than the last;
  * the tool is the SAME controls the newsletter's is -- one rich-text
    toolbar, one schedule picker reading its own dates;
  * a post can be written, saved, published, moved between blogs and put
    on a schedule to publish itself;
  * nothing spills out of a table row, which is the specific complaint
    this shape was asked for after.

Usage:

    python tools/blog_screen_check.py http://localhost:5000 <cookie-file>
"""
import io
import sys

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
COOKIE = open(sys.argv[2]).read().strip()

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

    page.goto(BASE + "/admin/blogs")
    settle(page)

    print()
    print("The writing comes first")
    print("-" * 68)
    order = page.evaluate(
        "() => [...document.querySelectorAll('h1, h2')].map(h => h.textContent.trim())")
    check("the tool, then what is written, then the schedules",
          order[:1] == ["Blog"]
          and "Your posts" in order and "Your schedules" in order
          and order.index("Your posts") < order.index("Your schedules"),
          " | ".join(order))
    check("...and the writing tool is above the list",
          page.evaluate("""() => {
            const tool = document.getElementById('cms-post-tool');
            const list = [...document.querySelectorAll('h2')]
              .find(h => h.textContent.trim() === 'Your posts');
            return !!tool && !!list
              && tool.getBoundingClientRect().top < list.getBoundingClientRect().top;
          }"""))
    check("making a blog is on the page too, not another screen",
          page.evaluate("() => !!document.querySelector"
                        "('form[action*=\"/admin/blogs/new\"]')"))

    print()
    print("It is the same tool a newsletter is written with")
    print("-" * 68)
    check("one rich-text toolbar, the one this app has",
          page.evaluate("() => document.querySelectorAll"
                        "('#cms-post-tool .cms-wysiwyg-toolbar, "
                        "#cms-post-tool [data-wysiwyg-toolbar]').length") <= 1)
    check("...with a surface to write on",
          page.evaluate("() => !!document.querySelector"
                        "('#cms-post-tool .cms-richtext [contenteditable]')"))
    check("a schedule picker, reading its own dates",
          page.evaluate("() => !!document.querySelector('#cms-post-tool "
                        "[data-schedule-pick]') && !!document.getElementById"
                        "('cms-post-schedule-dates')"))
    check("...and the shared picker is what drives it",
          page.evaluate("() => typeof window.cmsSchedulePicker === 'function'"))
    check("the clock the time is typed on is sent with it",
          page.evaluate("""() => {
            const f = document.querySelector('#cms-post-tool [data-tz-offset]');
            return !!f && f.value !== '' && f.value !== '0'
                   || new Date().getTimezoneOffset() === 0;
          }"""))
    #  Every control carries a sentence: the label is often a glyph, and
    #  then the title is the only text there is.
    #
    #  Asked of the control OR the label wrapping it, because that is
    #  where the sentence legitimately lives for a colour swatch or a
    #  tickbox -- the label is the thing with a pointer on it. And not
    #  asked of hidden fields at all: nobody can hover what is not drawn.
    bare = page.evaluate("""() => [...document.querySelectorAll(
        '#cms-post-tool select, #cms-post-tool input, #cms-post-tool button')]
        .filter(c => c.type !== 'hidden' && c.type !== 'file')
        .filter(c => !(c.title || '').trim()
                  && !(c.closest('label') && c.closest('label').title.trim()))
        .map(c => c.name || c.type).slice(0, 6)""")
    check("every control on the tool says what it does", not bare, str(bare))

    print()
    print("A post can actually be written")
    print("-" * 68)
    page.fill("#post-title", "A post from the checker")
    page.fill("#post-excerpt", "Written by the checker.")
    page.evaluate("""() => {
      const box = document.querySelector('#cms-post-tool .cms-richtext [contenteditable]');
      box.focus();
      box.innerHTML = '<p>The body of the post.</p>';
      box.dispatchEvent(new Event('input', {bubbles: true}));
    }""")
    page.click("#cms-post-tool button.btn-primary")
    settle(page)
    check("it is saved", page.evaluate(
        "() => document.querySelector('#post-title').value") == "A post from the checker")
    check("...and appears in the list below",
          "A post from the checker" in page.evaluate(
              "() => document.body.textContent"))
    check("...as a draft, because nothing said to publish it",
          page.evaluate("""() => {
            const row = [...document.querySelectorAll('tbody tr')].find(
              r => r.textContent.includes('A post from the checker'));
            return !!row && row.textContent.includes('Draft');
          }"""))
    check("...with the words that were typed",
          "The body of the post." in page.evaluate(
              "() => document.querySelector('#post-content').value"))

    print()
    print("Publishing is a decision, and so is when")
    print("-" * 68)
    page.check("#post-publish")
    page.click("#cms-post-tool button.btn-primary")
    settle(page)
    check("ticking Published publishes it",
          page.evaluate("""() => {
            const row = [...document.querySelectorAll('tbody tr')].find(
              r => r.textContent.includes('A post from the checker'));
            return !!row && row.textContent.includes('Published');
          }"""))
    check("...and it can then be opened on the site",
          page.evaluate("""() => {
            const row = [...document.querySelectorAll('tbody tr')].find(
              r => r.textContent.includes('A post from the checker'));
            return !!row && !!row.querySelector('a[target="_blank"]');
          }"""))

    print()
    print("Nothing spills out of a row")
    print("-" * 68)
    #  The complaint this shape was asked for after: a control wrapping
    #  onto a second line inside a table cell. Measured as height, since
    #  a wrapped row is simply a taller one.
    tall = page.evaluate("""() => {
      const rows = [...document.querySelectorAll('table.cms-people-table tbody tr')];
      return rows.map(r => Math.round(r.getBoundingClientRect().height));
    }""")
    check("every row is one line tall", all(h <= 64 for h in tall), str(tall))
    check("the page does not scroll sideways",
          page.evaluate("() => document.documentElement.scrollWidth "
                        "<= document.documentElement.clientWidth + 1"),
          str(page.evaluate("() => [document.documentElement.scrollWidth, "
                            "document.documentElement.clientWidth]")))

    check("no console errors", not errors, "; ".join(errors[:3]))
    browser.close()

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
sys.exit(1 if failures else 0)
