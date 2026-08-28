"""Putting a picture in comes from the Media Library, not a file dialog.

The toolbar's Image button went straight to a hidden file input, so the
only way to put a picture in a post or a page was to find the file again
on disk: no way to reuse one already uploaded, and no sight of what the
site already has. Reported as "the blog image option exists but no insert
from library", and true of the live page editor too, since both use the
one shared toolbar.

It opens the picker now, with Upload inside it -- both routes in one
dialog rather than a choice before a choice.

    python tools/image_picker_check.py <cookie-file> <a-blog-post-url>
"""

import io
import sys

from playwright.sync_api import sync_playwright

COOKIE = io.open(sys.argv[1], encoding="utf-8").read().strip()
URL = sys.argv[2]

ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-56s ok" % what)
    else:
        bad += 1
        print("  %-56s FAILED  %s" % (what, detail))


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 1000})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": "localhost", "path": "/"}])
    page = ctx.new_page()
    errs = []
    page.on("console",
            lambda m: errs.append(m.text[:110]) if m.type == "error" else None)
    page.goto(URL, wait_until="networkidle")

    check("the picker module is loaded", page.evaluate(
        "() => !!(window.cmsImagePicker && window.cmsImagePicker.open)"))
    btn = page.query_selector(".cms-insert-image-btn")
    check("the toolbar has an Image button", btn is not None)

    btn.click()
    page.wait_for_timeout(900)
    open_now = page.query_selector("#cms-image-picker-backdrop:not([hidden])")
    check("clicking it opens the Media Library, not a file dialog",
          open_now is not None)
    if open_now:
        shown = page.evaluate(
            "() => { const g = document.getElementById('cms-image-picker-grid');"
            " return { pictures: g ? g.children.length : 0,"
            " upload: !!document.querySelector('.cms-image-picker-upload'),"
            " words: document.querySelector('.cms-image-picker p').textContent }; }")
        check("it shows what the site already has",
              shown["pictures"] > 0, str(shown["pictures"]) + " pictures")
        #  Both routes in one dialog: choosing what exists, or adding one.
        check("...and offers to upload a new one", shown["upload"], str(shown))
        check("...and says so", "upload" in shown["words"].lower(), shown["words"])

        #  Choosing one sets the post's featured picture, which is what
        #  this button does in the blog editor.
        page.evaluate(
            "() => document.getElementById('cms-image-picker-grid').children[0].click()")
        page.wait_for_timeout(400)
        check("choosing one closes the dialog", page.query_selector(
            "#cms-image-picker-backdrop:not([hidden])") is None)
        got = page.evaluate(
            "() => { const f = document.querySelector('[data-featured-store]');"
            " return f ? f.value : null; }")
        check("...and sets the post's picture", bool(got), repr(got))
        check("...and it is shown where it will appear", page.evaluate(
            "() => { const s = document.querySelector('[data-featured-slot]');"
            " return !!s && !s.hidden; }"))

    check("no console errors", not errs, "; ".join(errs[:2]))
    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
