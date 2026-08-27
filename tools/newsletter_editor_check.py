"""The newsletter editor is the email, and it has text tools.

Run against a running instance, with a browser, because that is the only
place the thing this checks actually happens: what the toolbar produces
is read back by a serialiser in JavaScript and rendered by one in Python,
and the two have to agree exactly. Nothing in either language can prove
that on its own -- and a drift between them does not raise anything, it
just quietly changes what somebody wrote.

    python tools/newsletter_editor_check.py <base-url> <session-cookie-file> <newsletter-id>

The newsletter is written into and SAVED, so point it at one you do not
mind changing.
"""

import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
ISSUE = sys.argv[3] if len(sys.argv) > 3 else "1"
ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-58s ok" % what)
    else:
        bad += 1
        print("  %-58s FAILED  %s" % (what, detail))


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1300, "height": 950})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0], "path": "/"}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text[:110]) if m.type == "error" else None)
    page.goto(BASE + "/admin/newsletters/issue/" + ISSUE, wait_until="networkidle")

    print()
    print("The editor is the email")
    print("-" * 68)
    check("the canvas is on the page", page.query_selector(".cms-issue-canvas") is not None)
    check("the toolbar is above it, not in it", page.evaluate("""
      () => {
        const bar = document.querySelector('.cms-issue-toolbar');
        const canvas = document.querySelector('.cms-issue-canvas');
        return !!bar && !!canvas && !canvas.contains(bar);
      }"""))
    check("what an email cannot honour is not offered", page.evaluate("""
      () => !document.querySelector('.cms-issue-toolbar [data-cmd="justifyCenter"]')
         && !document.querySelector('.cms-issue-toolbar [data-cmd="fontName"]')
         && !document.querySelector('.cms-issue-toolbar [data-cmd="foreColor"]')"""))
    check("headings, emphasis, a link and bullets are", page.evaluate("""
      () => ['bold','italic','createLink','insertUnorderedList'].every(
              c => document.querySelector('.cms-issue-toolbar [data-cmd="' + c + '"]'))
         && document.querySelector('.cms-issue-toolbar [data-value="h2"]')
         && document.querySelector('.cms-issue-toolbar [data-value="h3"]')"""))

    #  The email's own ground and font, as it will be in the inbox.
    look = page.evaluate("""
      () => {
        const g = document.querySelector('.cms-issue-canvas-ground');
        const c = document.querySelector('.cms-issue-canvas');
        return { ground: getComputedStyle(g).backgroundColor,
                 font: getComputedStyle(c).fontFamily };
      }""")
    check("the canvas stands on the site's own colour",
          look["ground"] not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"), str(look))

    print()
    print("Writing into it, with the tools")
    print("-" * 68)
    body = page.query_selector('[data-rich]')
    check("the body is written into directly", body is not None)
    #  Start from empty, so a rerun measures this run and not the last.
    page.evaluate("() => { document.querySelector('[data-rich]').innerHTML = '<p><br></p>'; }")
    body.click()
    page.keyboard.type("Autumn hours")
    #  Make that line a heading with the toolbar.
    page.click('.cms-issue-toolbar [data-value="h2"]')
    page.wait_for_timeout(120)
    made = page.evaluate("""
      () => {
        const h = document.querySelector('[data-rich] h2');
        if (!h) return null;
        const cs = getComputedStyle(h);
        return { size: cs.fontSize, weight: cs.fontWeight, styled: h.getAttribute('style') };
      }""")
    check("the toolbar makes a real heading", made is not None, str(made))
    check("...and it is styled like the sent one, not left bare",
          bool(made and made["styled"] and "font-size" in made["styled"]), str(made))

    #  A second line, with bold in it.
    page.keyboard.press("Enter")
    page.keyboard.type("We are open ")
    page.click('.cms-issue-toolbar [data-cmd="bold"]')
    page.keyboard.type("late on Thursdays")
    page.click('.cms-issue-toolbar [data-cmd="bold"]')
    page.wait_for_timeout(120)

    typed = page.evaluate("""
      () => document.querySelector('[data-slot-store="body"]').value""")
    check("the heading is written down as ##", typed.startswith("## Autumn hours"), repr(typed))
    check("the bold is written down as **", "**late on Thursdays**" in typed, repr(typed))

    #  A bullet list, and a link, through the same buttons.
    page.keyboard.press("Enter")
    page.click('.cms-issue-toolbar [data-cmd="insertUnorderedList"]')
    page.keyboard.type("Thursdays")
    page.keyboard.press("Enter")
    page.keyboard.type("Fridays")
    page.wait_for_timeout(120)
    listed = page.evaluate("""
      () => document.querySelector('[data-slot-store="body"]').value""")
    #  Two bullets, each on its own line with the marker. Whether the
    #  words inside also carry bold depends on what was switched on when
    #  the list was started, which is the browser's business, not this.
    bullet_lines = [ln for ln in listed.split(chr(10)) if ln.startswith("- ")]
    check("bullets are written down as -", len(bullet_lines) == 2
          and "Thursdays" in bullet_lines[0] and "Fridays" in bullet_lines[1],
          repr(bullet_lines))
    check("a list is styled like the sent one", page.evaluate("""
      () => {
        const ul = document.querySelector('[data-rich] ul');
        const li = ul && ul.querySelector('li');
        return !!ul && !!li && !!ul.getAttribute('style') && !!li.getAttribute('style');
      }"""))

    print()
    print("What is saved is what is sent")
    print("-" * 68)
    #  Everything written by now -- read after the last edit, not before.
    stored = page.evaluate("""
      () => { const el = document.querySelector('[data-rich]');
              el.dispatchEvent(new Event('blur'));
              return document.querySelector('[data-slot-store="body"]').value; }""")
    page.click('.cms-post-save-bar button[type="submit"]')
    page.wait_for_load_state("networkidle")
    #  The preview route renders the email exactly as it will be sent.
    sent = ctx.new_page()
    sent.goto(BASE + "/admin/newsletters/issue/" + ISSUE + "/preview", wait_until="networkidle")
    html = sent.content()
    check("the sent email has the heading", "Autumn hours" in html and "<h2" in html)
    check("the heading carries its style inline",
          "font-weight:700" in html.replace(" ", ""), "")
    check("the sent email has the bold", "<strong>late on Thursdays</strong>" in html)
    check("nothing editable travelled into the message",
          "contenteditable" not in html and "data-slot" not in html)

    #  ...and it reads back into the editor as it was written.
    page.goto(BASE + "/admin/newsletters/issue/" + ISSUE, wait_until="networkidle")
    back = page.evaluate("""
      () => document.querySelector('[data-slot-store="body"]').value""")
    check("it reads back the way it was written", back.strip() == stored.strip(),
          repr(back) + " vs " + repr(stored))

    check("no console errors", not errors, "; ".join(errors[:2]))
    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
