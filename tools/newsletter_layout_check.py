"""The Template dropdown IS the choice, so it has to make it well.

There was a picker on the Newsletters screen -- four specimens to choose
between before writing a word. It is gone: the choice does not belong
before the work, and this dropdown already makes it better, at full size
with the blocks in front of you.

Which puts the whole weight on this control, and it was quietly broken.
"Has anybody written in this?" was implemented as "does any block contain
words", and a template lays out "A heading" and "What you want to say" --
so a brand-new newsletter answered YES, and changing the shape asked to
replace work that did not exist. Every time. The question is whether it
still MATCHES what it was laid out as, which is what this checks.

    python tools/newsletter_layout_check.py <base-url> <cookie-file> <id>

The newsletter is written into and SAVED, so point it at one you do not
mind changing.
"""

import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
ISSUE = sys.argv[3]
HOST = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]
EDIT = BASE + "/admin/newsletters/issue/" + ISSUE

ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-56s ok" % what)
    else:
        bad += 1
        print("  %-56s FAILED  %s" % (what, detail))


def kinds(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-block]'))"
        ".map(b => b.dataset.blockType)")


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 1000})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": HOST, "path": "/"}])
    page = ctx.new_page()
    errs = []
    page.on("console",
            lambda m: errs.append(m.text[:100]) if m.type == "error" else None)

    print()
    print("A newsletter opens ready to write in")
    print("-" * 66)
    page.goto(EDIT, wait_until="networkidle")
    check("it starts with the plainest shape",
          kinds(page) == ["heading", "text"], str(kinds(page)))
    check("the Template dropdown is the way to change that",
          page.query_selector("#layout-select") is not None)

    print()
    print("Changing it lays out at once, with nothing to lose")
    print("-" * 66)
    for choice, want in (("story", ["image", "heading", "text", "button"]),
                         ("two-up", ["heading", "text", "divider",
                                     "heading", "text"]),
                         ("announcement", ["heading", "text", "button"])):
        page.select_option("#layout-select", choice)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        asked = page.query_selector("#cms-modal-backdrop:not([hidden])")
        check("%s: it does not ask, because nothing is written" % choice,
              asked is None)
        check("%s: the canvas is the new arrangement" % choice,
              kinds(page) == want, str(kinds(page)))
        check("%s: and the dropdown agrees with the canvas" % choice,
              page.input_value("#layout-select") == choice,
              page.input_value("#layout-select"))

    print()
    print("...but it asks once there IS something to lose")
    print("-" * 66)
    body = page.query_selector("[data-rich]")
    body.click()
    page.keyboard.type("Words I would rather not lose")
    page.wait_for_timeout(150)
    page.evaluate(
        "() => Array.from(document.querySelectorAll('.cms-compose-actions button'))"
        ".find(x => x.textContent.trim() === 'Save').click()")
    page.wait_for_load_state("networkidle")

    page.select_option("#layout-select", "letter")
    page.wait_for_timeout(300)
    check("it asks first", page.query_selector(
        "#cms-modal-backdrop:not([hidden])") is not None)
    page.click("#cms-modal-cancel")
    page.wait_for_timeout(250)
    check("saying no keeps what was written",
          "Words I would rather not lose" in page.inner_text(".cms-issue-canvas"))
    check("...and puts the dropdown back to what is actually laid out",
          page.input_value("#layout-select") == "announcement",
          page.input_value("#layout-select"))

    check("no console errors", not errs, "; ".join(errs[:2]))
    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
