"""The newsletter editor is the email, and everything in it is optional.

Run against a running instance, with a browser, because that is the only
place the thing this checks actually happens: what the toolbar produces
is read back by a serialiser in JavaScript and rendered by one in Python,
and the two have to agree exactly. Neither language can prove that on its
own -- and a drift between them does not raise anything, it just quietly
changes what somebody wrote.

    python tools/newsletter_editor_check.py <base-url> <cookie-file> <id>

The newsletter is written into and SAVED, so point it at one you do not
mind changing.
"""
import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
ISSUE = sys.argv[3] if len(sys.argv) > 3 else "1"
HOST = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]
EDIT = BASE + "/admin/newsletters/issue/" + ISSUE

ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-58s ok" % what)
    else:
        bad += 1
        print("  %-58s FAILED  %s" % (what, detail))


def kinds(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-block]'))"
        ".map(b => b.dataset.blockType)")


def stored(page):
    return page.evaluate(
        "() => JSON.parse(document.querySelector('[data-blocks-store]').value || '[]')")


def settle(page):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(150)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1400, "height": 1000})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": HOST, "path": "/"}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text[:110]) if m.type == "error" else None)

    #  Start from a known arrangement, so a rerun measures this run.
    page.goto(EDIT, wait_until="networkidle")
    page.evaluate("""
      () => {
        const f = document.querySelector('[data-blocks-store]');
        f.value = JSON.stringify([
          {type: 'heading', level: 2, text: 'Autumn hours', style: {}},
          {type: 'text', text: 'We are open late.', style: {}}
        ]);
        document.querySelector('.cms-issue-form').submit();
      }""")
    settle(page)

    print()
    print("One toolbar, and the template is a control in it")
    print("-" * 68)
    check("the template is a dropdown, not a separate screen",
          page.query_selector(".cms-issue-toolbar #layout-select") is not None)
    check("everything is in one bar", page.evaluate(
        "() => document.querySelectorAll('.cms-issue-toolbar').length === 1"))
    check("every kind of block can be added", page.evaluate(
        """() => ['heading','text','image','button','divider'].every(
             k => document.querySelector('[data-add-block=\"' + k + '\"]'))"""))
    check("the writing tools are in it too", page.evaluate(
        """() => !!document.querySelector('.cms-issue-toolbar [data-cmd=\"bold\"]')
             && !!document.querySelector('.cms-issue-toolbar [data-value=\"h2\"]')"""))
    check("so are the style controls", page.evaluate(
        """() => ['align','font','color','bg'].every(
             k => document.querySelector('[data-block-style=\"' + k + '\"]'))"""))
    check("every control carries a sentence", page.evaluate(
        """() => Array.from(document.querySelectorAll(
             '.cms-issue-toolbar button, .cms-issue-toolbar select, .cms-issue-toolbar input'))
             .every(c => (c.title && c.title.trim())
                      || (c.closest('label[title]') && c.closest('label[title]').title.trim()))"""))
    check("the style controls are dead until a block is chosen", page.evaluate(
        """() => document.querySelector('[data-block-style=\"align\"]').disabled"""))

    print()
    print("A button and a picture are optional, added from the toolbar")
    print("-" * 68)
    before = kinds(page)
    check("it starts as the two blocks it was given", before == ["heading", "text"], str(before))

    page.click("[data-block][data-block-type='text']")
    page.wait_for_timeout(100)
    page.click("[data-add-block='button']")
    settle(page)
    after = kinds(page)
    check("a button can be added", "button" in after, str(after))
    check("...below whatever was selected", after == ["heading", "text", "button"], str(after))

    page.click("[data-add-block='image']")
    settle(page)
    check("a picture can be added too", "image" in kinds(page), str(kinds(page)))
    check("an empty picture slot is visible, so it can be filled",
          page.query_selector("[data-pick-image]") is not None)

    #  ...and taken away again, which is the other half of "optional".
    page.click("[data-block][data-block-type='image']")
    page.wait_for_timeout(100)
    page.click("[data-block-remove]")
    settle(page)
    check("and removed again", "image" not in kinds(page), str(kinds(page)))

    print()
    print("A block can be moved and styled, and the email carries it")
    print("-" * 68)
    page.click("[data-block][data-block-type='heading']")
    page.wait_for_timeout(100)
    check("choosing one wakes the style controls", page.evaluate(
        """() => !document.querySelector('[data-block-style=\"align\"]').disabled"""))
    check("...and says which one", page.evaluate(
        "() => document.querySelector('[data-selected-name]').textContent").startswith("Heading"))

    page.select_option("[data-block-style='align']", "center")
    settle(page)
    page.click("[data-block][data-block-type='heading']")
    page.wait_for_timeout(100)
    page.select_option("[data-block-style='font']", "Georgia, 'Times New Roman', serif")
    settle(page)
    page.click("[data-block][data-block-type='heading']")
    page.wait_for_timeout(100)
    page.evaluate("""
      () => {
        const c = document.querySelector("[data-block-style='bg']");
        c.value = '#fff3cd';
        c.dispatchEvent(new Event('change', {bubbles: true}));
      }""")
    settle(page)

    saved = stored(page)
    head = next((blk for blk in saved if blk["type"] == "heading"), {})
    check("the alignment is recorded", head.get("style", {}).get("align") == "center", str(head))
    check("the font is recorded", "Georgia" in (head.get("style", {}).get("font") or ""), str(head))
    check("the background is recorded", head.get("style", {}).get("bg") == "#fff3cd", str(head))
    check("the canvas shows the background at once", page.evaluate(
        """() => {
             const td = document.querySelector("[data-block-type='heading']");
             return getComputedStyle(td).backgroundColor;
           }""") == "rgb(255, 243, 205)")

    #  Moving it. The words have to come with it, not stay behind.
    page.click("[data-block][data-block-type='heading']")
    page.wait_for_timeout(100)
    page.click("[data-block-move='1']")
    settle(page)
    moved = kinds(page)
    check("a block can be moved", moved[0] == "text" and moved[1] == "heading", str(moved))
    check("...and its words move with it", any(
        blk["type"] == "heading" and blk.get("text") == "Autumn hours" for blk in stored(page)),
        str(stored(page)))

    print()
    print("Writing into it, with the tools")
    print("-" * 68)
    body = page.query_selector("[data-rich]")
    page.evaluate("() => { document.querySelector('[data-rich]').innerHTML = '<p><br></p>'; }")
    body.click()
    page.keyboard.type("Thursdays now run late")
    page.click('.cms-issue-toolbar [data-value="h3"]')
    page.wait_for_timeout(120)
    page.keyboard.press("Enter")
    page.keyboard.type("We are open until ")
    page.click('.cms-issue-toolbar [data-cmd="bold"]')
    page.keyboard.type("eight")
    page.wait_for_timeout(120)
    typed = next((blk["text"] for blk in stored(page) if blk["type"] == "text"), "")
    check("a heading inside the words is written down as ###",
          "### Thursdays now run late" in typed, repr(typed))
    check("bold is written down as **", "**eight**" in typed, repr(typed))
    check("a heading made by the toolbar is styled like the sent one", page.evaluate(
        """() => {
             const h = document.querySelector('[data-rich] h3');
             return !!h && !!h.getAttribute('style') && h.getAttribute('style').includes('font-size');
           }"""))

    print()
    print("What is on screen is what is sent")
    print("-" * 68)
    page.click('.cms-post-save-bar button[type="submit"]')
    settle(page)
    sent = ctx.new_page()
    sent.goto(EDIT + "/preview", wait_until="networkidle")
    html = sent.content()
    check("the words arrive", "Thursdays now run late" in html)
    check("the heading arrives as a heading", "<h3" in html)
    check("the bold arrives", "<strong>eight</strong>" in html)
    check("the block's background arrives on the cell",
          "#fff3cd" in html.lower() or "255, 243, 205" in html)
    check("the block's font arrives", "Georgia" in html)
    check("it is a table, which is what an inbox renders", "<table" in html)
    check("nothing editable travelled into the message",
          "contenteditable" not in html and "data-block" not in html
          and "data-field" not in html)

    print()
    print("Changing the template lays it out again, and asks first")
    print("-" * 68)
    page.goto(EDIT, wait_until="networkidle")
    page.select_option("#layout-select", "announcement")
    page.wait_for_timeout(250)
    check("it asks before replacing what is written",
          page.query_selector("#cms-modal-backdrop:not([hidden])") is not None)
    page.click("#cms-modal-confirm")
    settle(page)
    laid = kinds(page)
    check("the new arrangement is laid out",
          laid == ["heading", "text", "button"], str(laid))
    check("...and it is the one the server declares", page.evaluate(
        """() => {
             const starts = JSON.parse(
               document.getElementById('cms-layout-starts').textContent);
             return starts.announcement.map(b => b.type).join(',');
           }""") == ",".join(laid))

    check("no console errors", not errors, "; ".join(errors[:2]))
    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
