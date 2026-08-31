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


def pick(page, kind):
    """Click a block the way a person does -- on the block's own words.

    Not the middle of its cell. A selected block opens space at its top
    for its tool panel (see `showBlockHandle`), and on a short block --
    a button, a divider -- that space contains the cell's geometric
    centre, which is where a naive click lands. Clicking the content is
    both what a person does and what the panel must never cover.
    """
    cell = page.query_selector("[data-block][data-block-type='%s']" % kind)
    box = cell.bounding_box()
    page.mouse.click(box["x"] + 30, box["y"] + box["height"] - 8)
    page.wait_for_timeout(150)


def panel_clear_of_other_blocks(page):
    """Does the tool panel cover a block it is not about?

    This is the failure the space exists to prevent: floating the panel
    above the selected block put it over the block ABOVE, and a short
    one was covered completely -- unselectable, because its own controls
    ate every click aimed at it.
    """
    return page.evaluate("""() => {
      const h = document.querySelector('.cms-block-handle');
      if (!h) return 'no panel';
      const sel = document.querySelector('[data-block].cms-block-selected');
      const p = h.getBoundingClientRect();
      const bad = [];
      document.querySelectorAll('[data-block]').forEach(function (c) {
        if (c === sel) return;
        const r = c.getBoundingClientRect();
        const over = Math.min(p.bottom, r.bottom) - Math.max(p.top, r.top);
        const across = Math.min(p.right, r.right) - Math.max(p.left, r.left);
        if (over > 2 && across > 2) bad.push(c.dataset.blockType + ' by ' + Math.round(over) + 'px');
      });
      return bad.length ? bad.join(', ') : '';
    }""")


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
        """() => !!document.querySelector('[data-cmd=\"bold\"]')
             && !!document.querySelector('[data-value=\"h2\"]')
             && document.querySelectorAll('.cms-toolbar-writing').length === 1"""))
    check("so are the style controls", page.evaluate(
        """() => ['align','font','color','bg'].every(
             k => document.querySelector('[data-block-style=\"' + k + '\"]'))"""))
    #  A HIDDEN input is machinery behind a button that carries the
    #  sentence, not a control somebody points at -- the same exclusion
    #  the screen audit already makes, for the same reason.
    check("every control carries a sentence", page.evaluate(
        """() => Array.from(document.querySelectorAll(
             '.cms-issue-toolbar button, .cms-issue-toolbar select, .cms-issue-toolbar input'))
             .filter(c => c.type !== 'hidden')
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
    #  Send, Save, Delete. There WAS a Schedule button here, and it was
    #  the only thing that booked anything -- so choosing a schedule and
    #  pressing Save set a control and threw it away. Reported exactly
    #  that way: "I added a schedule and saved, but the schedule and
    #  recipients do not show." Save does the work now, and a control
    #  that needs a second button pressed beside it is a control that is
    #  discarded on save wearing a button.
    check("the actions are the things that happen to it", page.evaluate(
        """() => {
             const bar = document.querySelector('.cms-compose-actions');
             const words = Array.from(bar.querySelectorAll('button'))
               .map(b => b.textContent.trim());
             return ['Send','Save'].every(w => words.includes(w)); }"""))
    check("...and Schedule is not one of them any more", page.evaluate(
        """() => !Array.from(document.querySelectorAll('.cms-compose-actions button'))
             .some(b => b.textContent.trim() === 'Schedule')"""))
    check("when it goes is a control, with Not scheduled as its default",
          page.evaluate("""() => {
             const s = document.querySelector('[data-schedule-pick]');
             return !!s && s.options.length >= 2
                 && s.options[0].value === 'none'
                 && s.value === 'none'; }"""))
    check("one form, told apart by formaction", page.evaluate(
        """() => document.querySelectorAll('form.cms-issue-form').length === 1
             && document.querySelectorAll('[formaction]').length >= 3"""))
    check("a time of your own is still possible", page.evaluate(
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

    pick(page, "text")
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
    pick(page, "image")
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
    pick(page, "heading")
    check("choosing one wakes the style controls", page.evaluate(
        """() => !document.querySelector('[data-block-style=\"align\"]').disabled"""))
    check("...and says which one", page.evaluate(
        "() => document.querySelector('[data-selected-name]').textContent").startswith("Heading"))

    #  The panel is ABOUT one block and must not sit on another. It used
    #  to float above the selected block, which is over the block above
    #  it -- and a short one was covered whole, so it could not be
    #  clicked at all while its neighbour was selected.
    covering = panel_clear_of_other_blocks(page)
    check("the panel covers no other block", covering == "", covering)

    page.select_option("[data-block-style='align']", "center")
    settle(page)
    pick(page, "heading")
    page.select_option("[data-block-style='font']", "Georgia, 'Times New Roman', serif")
    settle(page)
    pick(page, "heading")
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
    pick(page, "heading")
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
    page.click('[data-value="h3"]')
    page.wait_for_timeout(120)
    page.keyboard.press("Enter")
    page.keyboard.type("We are open until ")
    page.click('[data-cmd="bold"]')
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
    #  Every arrangement now opens and closes with the owner's own words
    #  -- an opening and a sign-off are blocks IN the newsletter, not two
    #  settings applied invisibly to every send. So what this asserts is
    #  the shape between them, plus the fact that they are there.
    check("the new arrangement is laid out",
          laid[1:-1] == ["heading", "text", "button"], str(laid))
    check("...opening and closing with the owner's own words", page.evaluate(
        """() => { const b = JSON.parse(
               document.querySelector('[data-blocks-store]').value);
             return b.length > 2 && b[0].role === 'intro'
                    && b[b.length - 1].role === 'exit'; }"""))
    check("...and it is the one the server declares", page.evaluate(
        """() => {
             const starts = JSON.parse(
               document.getElementById('cms-layout-starts').textContent);
             return starts.announcement.map(b => b.type).join(',');
           }""") == ",".join(laid))

    print()
    print("Changing a block does not reload the page")
    print("-" * 68)
    #  Restyling submitted the whole form and loaded the whole page. The
    #  scroll position and the selection were carried across, so it READ
    #  as an update -- but on anything slower than a local container you
    #  watched the screen go white to change one alignment. The canvas is
    #  still rendered by the SERVER (two renderers would drift); it is
    #  fetched and swapped instead of navigated to.
    page.evaluate("() => { window.__same = 'this document'; }")
    loads = []
    page.on("load", lambda _: loads.append(1))
    pick(page, "heading")
    page.select_option("[data-block-style='align']", "center")
    page.wait_for_timeout(900)
    check("no page load happened", not loads, "%d loads" % len(loads))
    check("...it is the same document", page.evaluate(
        "() => window.__same || 'RELOADED'") == "this document")
    check("...and the change is on the block", "center" in page.evaluate(
        """() => { const c = document.querySelector(
             "[data-block][data-block-type='heading']");
             return c ? getComputedStyle(c).textAlign : ''; }"""))
    check("...with the block still selected",
          page.evaluate("() => !!document.querySelector('.cms-block-selected')"))
    check("...and typing still reaching the store", page.evaluate(
        """() => { const f = document.querySelector('[data-field]');
             f.focus(); f.textContent = 'Typed after the swap';
             f.dispatchEvent(new Event('input', {bubbles: true}));
             return document.querySelector('[data-blocks-store]')
                    .value.indexOf('Typed after the swap') >= 0; }"""))

    print()
    print("A control is offered only where it does something")
    print("-" * 68)
    #  COLOUR is the colour of WORDS. A picture has none, and the control
    #  was offered on one anyway: set, stored, and read by nothing that
    #  renders a picture. Reported as "COLOUR doesn't appear to do
    #  anything", which is exactly what it did.
    pick(page, "heading")
    check("a heading is offered a colour", page.evaluate(
        """() => { const w = document.querySelector("[data-set='words']");
             return !!w && !w.hidden; }"""))
    page.click("[data-add-block='image']")
    settle(page)
    check("a picture is not", page.evaluate(
        """() => { const w = document.querySelector("[data-set='words']");
             return !!w && w.hidden; }"""))
    #  Behind is a different question: a picture narrower than the card
    #  has a box around it, and that box is what Behind paints.
    check("...but a picture is still offered what is behind it", page.evaluate(
        """() => { const w = document.querySelector("[data-set='behind']");
             return !!w && !w.hidden; }"""))

    #  With nothing selected the controls have nothing to act on. They
    #  are parked in the ribbon between selections -- that row holds the
    #  only copy of them -- and a greyed row reading "NO BLOCK" is a row
    #  of chrome explaining that it does nothing.
    #  Deselecting means clicking the CANVAS somewhere that is not a
    #  block -- clicking the page outside it does nothing, which is
    #  correct and is what made an earlier version of this check wrong
    #  rather than the code.
    page.evaluate("""() => {
      const foot = document.querySelector('.cms-issue-canvas-foot');
      const r = foot.getBoundingClientRect();
      foot.dispatchEvent(new MouseEvent('mousedown', {bubbles: true,
        clientX: r.left + 5, clientY: r.top + 5}));
    }""")
    page.wait_for_timeout(250)
    check("with nothing selected the parked row is not drawn", page.evaluate(
        """() => { const t = document.querySelector('[data-block-tools]');
             return !!t && getComputedStyle(t).display === 'none'; }"""),
          page.evaluate("""() => { const t = document.querySelector('[data-block-tools]');
             return t ? getComputedStyle(t).display : 'GONE'; }"""))

    #  What the field is called. It is one field on purpose -- a title and
    #  a subject that can disagree is two -- and while somebody is writing
    #  it is the subject line, which is the job that decides whether the
    #  message is opened.
    check("the subject field says Subject", page.evaluate(
        """() => { const l = document.querySelector("label[for='subject']");
             return l ? l.textContent.trim() : 'missing'; }""") == "Subject")

    print()
    print("The writing tools stand where the writing is")
    print("-" * 68)
    #  Bold, a heading and a link act on the block you are IN, and they
    #  sat in the ribbon three rows above it -- and on a block with no
    #  words they acted on nothing at all.
    WHERE = """() => { const w = document.querySelector('.cms-toolbar-writing');
      if (!w) return 'MISSING';
      if (w.hidden) return 'parked';
      return w.closest('.cms-block-handle') ? 'on the block' : 'in the ribbon'; }"""
    pick(page, "text")
    check("on a block of words, they are on the block",
          page.evaluate(WHERE) == "on the block", page.evaluate(WHERE))
    pick(page, "heading")
    check("...and on a heading", page.evaluate(WHERE) == "on the block",
          page.evaluate(WHERE))
    page.click("[data-add-block='image']")
    settle(page)
    check("...but not on a picture, which has no words",
          page.evaluate(WHERE) == "parked", page.evaluate(WHERE))

    #  Looking at it is a thing you do to the whole newsletter, like
    #  saving it -- so it stands with those, in the tool's header, as an
    #  icon. The system messages screen already puts its preview there.
    check("preview is an icon in the tool's header", page.evaluate(
        """() => { const b = document.querySelector("[formaction*='preview']");
             if (!b) return 'missing';
             return b.classList.contains('icon-btn')
                 && !!b.closest('.cms-issue-toolbar'); }"""))
    check("...and it still says what it does",
          page.evaluate("""() => { const b = document.querySelector(
              "[formaction*='preview']"); return !!b && !!(b.title || '').trim(); }"""))


    print()
    print("The tools look like tools")
    print("-" * 68)
    #  Four things an owner reported as "messy", each measured rather
    #  than eyeballed, because every one of them is a number.

    #  1. Where a button points was a CARD under the message holding one
    #     field. It is a property of the selected block, exactly as its
    #     alignment is, so it stands with the block's other controls --
    #     which are now on the block itself, in its tool panel, rather
    #     than in the ribbon at the top of the screen. What matters has
    #     not changed: it is WITH the controls it belongs to, and it is
    #     not a form of its own underneath the message.
    page.click("[data-add-block='button']")
    settle(page)
    pick(page, "button")
    where = page.evaluate(
        """() => { const f = document.getElementById('block-url');
             if (!f) return 'missing';
             const tools = document.querySelector('[data-block-tools]');
             const align = document.querySelector('[data-block-style=\"align\"]');
             const r = f.getBoundingClientRect();
             return { withItsBlock: !!tools && tools.contains(f),
                      besideAlign: !!align && align.closest('[data-block-tools]')
                                   === f.closest('[data-block-tools]'),
                      width: Math.round(r.width),
                      card: !!f.closest('.card') }; }""")
    check("a block's link stands with that block's other controls",
          where != "missing" and where["withItsBlock"], str(where))
    check("...in the same panel as its alignment",
          where != "missing" and where["besideAlign"], str(where))
    check("...not a card under the message",
          where != "missing" and not where["card"], str(where))
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
    #  Per ROW, not as a total. The header holds a third line now -- what
    #  happens to the message afterwards -- and a total cap would have
    #  read that addition as the regression it was written to catch. The
    #  claim was never "two rows"; it is that each of these is a line,
    #  not a form field.
    header = page.evaluate(
        """() => {
             const h = document.querySelector('.cms-compose-header');
             return { tall: Math.round(h.getBoundingClientRect().height),
                      rows: h.querySelectorAll('.cms-compose-row').length }; }""")
    check("...so the header is a strip of lines, not a stack of fields",
          header["rows"] and header["tall"] / header["rows"] <= 50, str(header))

    #  3. WHEN it goes is one control, labelled, with the date box as
    #     the exception rather than the rule -- naming the schedules is
    #     what stopped a date being typed every month.
    #
    #     There was a Schedule button attached to it, and this used to
    #     measure the gap between the two. The button is gone: Save does
    #     the work, because choosing a schedule and pressing Save set a
    #     control and threw it away. So what is measured now is that the
    #     picker is labelled, defaults to "Not scheduled", and reads as
    #     one control with the date beside it.
    sched = page.evaluate(
        """() => { const wrap = document.querySelector('.cms-compose-schedule');
             const pick = wrap.querySelector('[data-schedule-pick]');
             const label = wrap.querySelector('label');
             const p = pick.getBoundingClientRect();
             const l = label ? label.getBoundingClientRect() : null;
             return { hasSchedules: pick.options.length > 2,
                      labelled: !!label,
                      joined: l ? Math.round(p.left - l.right) : 999,
                      bordered: getComputedStyle(wrap).borderStyle !== 'none',
                      notScheduled: pick.value === 'none',
                      dateHidden: wrap.querySelector('[data-send-at]').hidden,
                      width: Math.round(wrap.getBoundingClientRect().width) }; }""")
    check("when it goes reads as one control", sched["labelled"]
          and sched["bordered"] and sched["joined"] <= 12, str(sched))
    check("...and nothing is on the clock until somebody says so",
          sched["notScheduled"], str(sched))
    check("...and a date is only asked for a one-off",
          sched["hasSchedules"] == sched["dateHidden"] or not sched["hasSchedules"],
          str(sched))

    #  4. Everything that happens TO the newsletter is in one row under
    #     it, Delete included -- it used to sit alone in a card under
    #     everything else.
    acts = page.evaluate(
        """() => { const bar = document.querySelector('.cms-compose-actions');
             const canvas = document.querySelector('.cms-issue-canvas-ground');
             return { below: bar.getBoundingClientRect().top
                              > canvas.getBoundingClientRect().top,
                      has: ['[data-send]', '[data-delete-issue]']
                             .every(sel => !!bar.querySelector(sel)),
                      strayCards: document.querySelectorAll(
                        '.card form[action*="/delete"]').length }; }""")
    check("send, save and delete are under the message",
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
    pick(page, "text")
    busy = ribbon()
    check("the ribbon is the same height whether or not a block is chosen",
          idle["h"] == busy["h"], "idle %s, selected %s" % (idle, busy))
    #  Four, not three. The bound moved once and the reason is recorded
    #  rather than the number quietly raised: the selected-block group
    #  carries eleven controls now -- name, alignment, font, two colours
    #  with their resets, a link, a blog and a count -- and eleven
    #  controls do not share a row with anything at 852px.
    #
    #  What the bound is FOR is that the next control is not free. When
    #  this last failed it read five rows and 258px; the toolbar was
    #  reset to toolbar size rather than form size (12px in a 150px box,
    #  not 13px in a 190px one) and it came back to four and 200px.
    check("...and no taller than four rows, densely set",
          busy["rows"] <= 4 and busy["h"] <= 210, str(busy))

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
              for k in ("letter", "story", "two-up", "announcement", "from-the-blog")), str(after))

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
              for k in ("letter", "story", "two-up", "announcement", "from-the-blog")), str(left))
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
