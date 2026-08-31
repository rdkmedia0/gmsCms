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
    print("Laid out the way a mail composer is")
    print("-" * 68)
    #  Tools, who it is for, the message, then what to do with it.
    #
    #  This used to put the actions THIRD, above the message. Send is a
    #  button you press last, and it sat above everything you do first --
    #  live, over a message that was still empty. Everything before the
    #  canvas is what the message needs; everything after it is what
    #  happens to the message. Which is also the order of an envelope.
    order = page.evaluate("""
      () => {
        const want = ['.cms-issue-toolbar', '.cms-compose-header',
                      '.cms-issue-canvas-ground', '.cms-compose-actions'];
        const tops = want.map(sel => {
          const el = document.querySelector(sel);
          return el ? el.getBoundingClientRect().top : -1;
        });
        return tops;
      }""")
    check("tools, recipients, the message, then what to do with it",
          all(t > 0 for t in order) and order == sorted(order), str(order))
    check("who it goes to is a field in the header, not a card at the bottom",
          page.evaluate("() => !!document.querySelector('.cms-compose-header #audience')"))
    check("...and the subject is beside it",
          page.evaluate("() => !!document.querySelector('.cms-compose-header #subject')"))
    check("all four actions are there", page.evaluate(
        """() => {
             const bar = document.querySelector('.cms-compose-actions');
             const words = Array.from(bar.querySelectorAll('button'))
               .map(b => b.textContent.trim());
             return ['Send','Schedule','Save','Preview'].every(w => words.includes(w));
           }"""))
    check("it says Preview, not a sentence about sending", page.evaluate(
        """() => Array.from(document.querySelectorAll('.cms-compose-actions button'))
             .some(b => b.textContent.trim() === 'Preview')"""))
    check("one form, told apart by formaction", page.evaluate(
        """() => document.querySelectorAll('form.cms-issue-form').length === 1
             && document.querySelectorAll('.cms-compose-actions button[formaction]').length >= 3"""))
    check("Schedule has a time to send at", page.evaluate(
        "() => !!document.querySelector('.cms-compose-actions input[type=\"datetime-local\"]')"))
    check("the browser's own clock is what gets sent", page.evaluate(
        """() => {
             const f = document.querySelector('[data-tz-offset]');
             return !!f && f.value === String(new Date().getTimezoneOffset());
           }"""))
    #  A hidden field is not a control anybody can see, so it is exempt --
    #  the rule is about a label that might be a glyph, not about markup.
    check("every action carries a sentence", page.evaluate(
        """() => Array.from(document.querySelectorAll('.cms-compose-actions button, '
             + '.cms-compose-actions input, .cms-compose-header select, '
             + '.cms-compose-header input, .cms-compose-header label'))
             .filter(c => c.type !== 'hidden')
             .every(c => c.title && c.title.trim())"""))

    #  Send cannot be taken back, so it asks. Schedule can, so it does not.
    page.click("[data-send]")
    page.wait_for_timeout(250)
    check("Send asks before it goes",
          page.query_selector("#cms-modal-backdrop:not([hidden])") is not None)
    page.click("#cms-modal-cancel")
    page.wait_for_timeout(200)
    check("...and saying no sends nothing", page.url.endswith(ISSUE))

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
    #  The control is on the BLOCK, not in the toolbar: what you are
    #  about to remove is the thing you are pointing at, and there is
    #  nothing to read to find out which one it will take.
    page.click("[data-block][data-block-type='image']")
    page.wait_for_timeout(150)
    check("choosing a block puts its own controls on it",
          page.query_selector(".cms-block-handle") is not None)
    check("...including one to take it away",
          page.query_selector(".cms-block-handle-remove") is not None)
    page.click(".cms-block-handle-remove")
    settle(page)
    check("and removed again", "image" not in kinds(page), str(kinds(page)))
    check("...leaving everything else where it was",
          kinds(page) == ["heading", "text", "button"], str(kinds(page)))

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
    page.click(".cms-block-handle [data-handle='1']")
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
    page.evaluate("""
      () => Array.from(document.querySelectorAll('.cms-compose-actions button'))
              .find(b => b.textContent.trim() === 'Save').click()""")
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

    print()
    print("The tools look like tools")
    print("-" * 68)
    #  Four things an owner reported as "messy", each measured rather
    #  than eyeballed, because every one of them is a number.

    #  1. Where a button points was a CARD under the message holding one
    #     field. It is a property of the selected block, exactly as its
    #     alignment is, so it belongs with those in the ribbon.
    page.click("[data-add-block='button']")
    settle(page)
    page.click("[data-block][data-block-type='button']")
    page.wait_for_timeout(200)
    where = page.evaluate(
        """() => { const f = document.getElementById('block-url');
             if (!f) return 'missing';
             const bar = document.querySelector('.cms-issue-toolbar');
             const canvas = document.querySelector('.cms-issue-canvas-ground');
             const r = f.getBoundingClientRect();
             return { inToolbar: !!bar && bar.contains(f),
                      aboveCanvas: r.top < canvas.getBoundingClientRect().top,
                      width: Math.round(r.width),
                      card: !!f.closest('.card') }; }""")
    check("a block's link is in the ribbon with its other controls",
          where != "missing" and where["inToolbar"], str(where))
    check("...not a card under the message",
          where != "missing" and not where["card"] and where["aboveCanvas"], str(where))
    check("...and is a control's width, not a form's",
          where != "missing" and where["width"] <= 260, str(where))

    #  2. To and Subject were full-width boxes 40px tall: 120px of chrome
    #     to hold an address and one line, reading as the biggest thing
    #     on a screen whose subject is the message below them.
    fields = page.evaluate(
        """() => ['#audience', '#subject'].map(sel => {
             const r = document.querySelector(sel).getBoundingClientRect();
             return { w: Math.round(r.width), h: Math.round(r.height) };
           })""")
    check("To and Subject are capped, not stretched to the window",
          all(f["w"] <= 470 for f in fields), str(fields))
    check("...and are one row each, not a form field each",
          all(f["h"] <= 34 for f in fields), str(fields))
    header = page.evaluate(
        """() => Math.round(document.querySelector(
             '.cms-compose-header').getBoundingClientRect().height)""")
    check("...so the two of them together are one strip", header <= 100, str(header))

    #  3. Schedule and its time are one control, drawn as one. They were
    #     a button and a 240px date box with a gap between them and no
    #     visible relationship.
    sched = page.evaluate(
        """() => { const wrap = document.querySelector('.cms-compose-schedule');
             const input = wrap.querySelector('input[type=datetime-local]');
             const btn = wrap.querySelector('button');
             const w = wrap.getBoundingClientRect();
             const i = input.getBoundingClientRect();
             const b = btn.getBoundingClientRect();
             return { joined: Math.round(i.left - b.right),
                      bordered: getComputedStyle(wrap).borderStyle !== 'none',
                      width: Math.round(w.width) }; }""")
    check("Schedule and its time read as one control",
          sched["bordered"] and abs(sched["joined"]) <= 2, str(sched))

    #  4. Everything that happens TO the newsletter is in one row under
    #     it, Delete included -- it used to sit alone in a card under
    #     everything else.
    acts = page.evaluate(
        """() => { const bar = document.querySelector('.cms-compose-actions');
             const canvas = document.querySelector('.cms-issue-canvas-ground');
             return { below: bar.getBoundingClientRect().top
                              > canvas.getBoundingClientRect().top,
                      has: ['[data-send]', '[data-schedule]', '[data-delete-issue]']
                             .every(sel => !!bar.querySelector(sel)),
                      strayCards: document.querySelectorAll(
                        '.card form[action*="/delete"]').length }; }""")
    check("send, schedule, save, preview and delete are under the message",
          acts["below"] and acts["has"], str(acts))
    check("...and delete is not in a card of its own",
          acts["strayCards"] == 0, str(acts))

    #  5. The ribbon must not change SHAPE as it is used. It was 163px
    #     with nothing selected and 122px once a block was clicked -- it
    #     got shorter when you selected something -- because the label
    #     saying which block the controls act on swung 57px between
    #     "Nothing selected" and "Words 2", enough to wrap a row.
    def ribbon():
        #  Reports the GROUPS, not just a height. A check that says "164
        #  and 122 differ" leaves whoever reads it to go and find out
        #  which part grew; this one says.
        return page.evaluate(
            """() => { const bar = document.querySelector('.cms-issue-toolbar');
                 const rows = [];
                 bar.querySelectorAll('button,select,input').forEach(el => {
                   const t = el.getBoundingClientRect().top;
                   if (!rows.some(r => Math.abs(r - t) < 16)) rows.push(t);
                 });
                 const groups = [];
                 bar.querySelectorAll('.cms-toolbar-group').forEach(g => {
                   const r = g.getBoundingClientRect();
                   groups.push(String(g.className).split(' ').pop()
                     + ':' + Math.round(r.width) + 'x' + Math.round(r.height));
                 });
                 const kids = [];
                 Array.from(bar.children).forEach(c => {
                   const r = c.getBoundingClientRect();
                   kids.push((c.className || c.tagName)
                     + '@' + Math.round(r.top) + ':' + Math.round(r.width)
                     + 'x' + Math.round(r.height));
                 });
                 const cs = getComputedStyle(bar);
                 return { h: Math.round(bar.getBoundingClientRect().height),
                          rows: rows.length, pad: cs.padding,
                          kids: kids.join(' | ') }; }""")

    #  Deselected by clicking the ground's own top edge, where there is
    #  certainly no block. Clicking its centre lands ON the card and
    #  selects whatever is there -- which measured a selected image's
    #  Link field and called the result "idle".
    #  Dispatched ON the canvas, which is where the handler lives. The
    #  first attempt fired at the canvas's PARENT -- events bubble up,
    #  not down, so nothing was deselected and the check measured a still
    #  selected image and called it idle.
    page.evaluate(
        """() => { const c = document.querySelector('.cms-issue-canvas');
             c.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); }""")
    page.wait_for_timeout(250)
    idle = ribbon()
    page.click("[data-block][data-block-type='text']")
    page.wait_for_timeout(250)
    busy = ribbon()
    check("the ribbon is the same height whether or not a block is chosen",
          idle["h"] == busy["h"], "idle %s, selected %s" % (idle, busy))
    check("...and no taller than three rows",
          busy["rows"] <= 3, str(busy))

    print()
    print("The picture picker is a picker, on an admin screen too")
    print("-" * 68)
    #  Its styles lived in inline-editor.css, which admin pages do not
    #  load -- so here it opened unstyled: measured, a 332px dialog
    #  holding 79 tiles at their natural 1200x2000, one under another,
    #  64,805px of grid. They travel with cms_modal.html now.
    page.click("[data-add-block='image']")
    settle(page)
    slot = page.query_selector("[data-pick-image]")
    if slot:
        slot.click()
        page.wait_for_timeout(1200)
        grid = page.evaluate(
            """() => { const g = document.getElementById('cms-image-picker-grid');
                 if (!g) return 'missing';
                 const s = getComputedStyle(g), box = g.getBoundingClientRect();
                 const first = g.children[0];
                 const f = first ? first.getBoundingClientRect() : {width: 0, height: 0};
                 const img = first && first.querySelector('img');
                 return { display: s.display,
                          overflowY: s.overflowY,
                          gridHeight: Math.round(box.height),
                          tile: Math.round(f.width) + 'x' + Math.round(f.height),
                          tileW: Math.round(f.width),
                          fit: img ? getComputedStyle(img).objectFit : '-',
                          count: g.children.length }; }""")
        check("it is a grid", grid != "missing" and grid["display"] == "grid", str(grid))
        check("...whose tiles are thumbnails, not full-size pictures",
              grid != "missing" and grid["tileW"] <= 260, str(grid))
        check("...cropped to fit rather than squashed",
              grid != "missing" and grid["fit"] == "cover", str(grid))
        check("...and the pictures scroll inside the dialog",
              grid != "missing" and grid["overflowY"] == "auto"
              and grid["gridHeight"] < 1000, str(grid))
        check("Cancel is still reachable without scrolling the page",
              page.evaluate(
                  """() => { const c = document.getElementById('cms-image-picker-cancel');
                       const r = c.getBoundingClientRect();
                       return r.top >= 0 && r.bottom <= window.innerHeight; }"""))
        page.click("#cms-image-picker-cancel")
        page.wait_for_timeout(200)

    print()
    print("An arrangement you like can be kept")
    print("-" * 68)
    #  A layout is a starting arrangement, not a kind -- so saving one is
    #  storing its blocks under a name, and it joins the same dropdown.
    #  By NAME, never by count. An earlier run of this checker that died
    #  midway leaves its arrangement behind, and saving the same name
    #  replaces it rather than adding a second -- so "one more option
    #  than before" is false on the second run even though everything
    #  worked. Presence and absence are what is actually being claimed.
    def options():
        return page.evaluate(
            """() => Array.from(document.querySelectorAll('#layout-select option'))
                 .map(o => o.value + '|' + o.text)""")
    page.evaluate("""() => {
      window.__savedName = 'Checker arrangement';
      window.cmsModal = async (opts) => (opts.showInput
        ? { confirmed: true, value: window.__savedName }
        : { confirmed: true });
    }""")
    page.click("[data-save-layout]")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)
    after = options()
    mine = [o for o in after if o.startswith("saved:")
            and "Checker arrangement" in o]
    check("it appears in the Template list", bool(mine), str(after))
    check("...under the name that was given, so it can be recognised",
          any(o.endswith("|Checker arrangement") for o in mine), str(mine))
    check("...and the built-in ones are still there",
          all(any(o.startswith(k + "|") for o in after)
              for k in ("letter", "story", "two-up", "announcement")), str(after))

    #  ...and can be taken away again, which is the half that keeps
    #  getting left out.
    #
    #  Driven by setting the value and firing `change` rather than by
    #  select_option: choosing a layout lays the blocks out again, and
    #  waiting out that reload three times in a row makes this check
    #  about timing rather than about the button.
    key = mine[0].split("|")[0]
    check("Remove wakes up for one of your own", page.evaluate(
        """(k) => { const s = document.querySelector('#layout-select');
             s.value = k;
             s.dispatchEvent(new Event('change'));
             return !document.querySelector('[data-delete-layout]').disabled; }""",
        key))
    check("...and stays asleep on a built-in one", page.evaluate(
        """() => { const s = document.querySelector('#layout-select');
             s.value = 'letter';
             s.dispatchEvent(new Event('change'));
             return document.querySelector('[data-delete-layout]').disabled; }"""))

    #  The route itself, posted the way the button posts it.
    removed = page.evaluate(
        """async (k) => { const url = document.querySelector(
               '[data-delete-layout]').dataset.deleteLayoutUrl;
             const body = new FormData();
             body.append('key', k);
             const res = await fetch(url, { method: 'POST',
               headers: { 'X-Inline-Edit': '1' }, body });
             return (await res.json()).ok; }""", key)
    check("removing it is one post", removed is True, str(removed))
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(500)
    left = options()
    check("...and it is gone from the Template list",
          not any("Checker arrangement" in o for o in left), str(left))
    check("...without taking the built-in ones with it",
          all(any(o.startswith(k + "|") for o in left)
              for k in ("letter", "story", "two-up", "announcement")), str(left))
    #  A shipped one is in the code and would be back on the next boot,
    #  so the route refuses rather than pretending.
    refused = page.evaluate(
        """async () => { const url = document.querySelector(
               '[data-delete-layout]').dataset.deleteLayoutUrl;
             const body = new FormData();
             body.append('key', 'letter');
             const res = await fetch(url, { method: 'POST',
               headers: { 'X-Inline-Edit': '1' }, body });
             return (await res.json()).ok; }""")
    check("a built-in one cannot be removed", refused is False, str(refused))

    check("no console errors", not errors, "; ".join(errors[:2]))
    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
