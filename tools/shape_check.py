"""A shape has to survive the things standing inside it.

Two faults, both invisible to anything but a browser, and both of a kind
this project has now been bitten by twice: a CSS declaration that is
WRONG produces silence, not an error.

  1. Percentage padding resolves against WIDTH on every side, including
     top and bottom. Right for a box roughly as tall as it is wide,
     absurd for a row: a 420x80 file card given `min(24%, 88px)`
     vertically became 420x352, four times its own height, to clear a
     curve that never reached it.

  2. `clamp(0px, var(--site-radius), 28px)` cannot cap a lens or a blob.
     A lens is `50% / 30%`, so after substitution the declaration is
     invalid -- and an invalid value arriving through var() does not fall
     back to the previous declaration, it becomes unset. So on exactly
     the sites that needed the cap, the cap silently did nothing.

Both are now separate variables that are always the right KIND of value.
This drives a real browser at every shape and measures the result.

    python tools/shape_check.py <base-url> [cookie-file]
"""
import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = (io.open(sys.argv[2], encoding="utf-8").read().strip()
          if len(sys.argv) > 2 else "")

#  Every shape the app offers, and what each one is.
GENTLE = ("sharp", "soft", "rounded", "cut-corner")
DRAMATIC = ("pill", "lens", "organic", "organic-alt")

ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-58s ok" % what)
    else:
        bad += 1
        print("  %-58s FAILED  %s" % (what, detail))


#  A page of its own rather than whatever the site happens to hold: what
#  is being measured is the CSS, and a check that depends on somebody's
#  content is a check that breaks when they edit it.
PAGE = """
() => {
  document.body.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.id = 'probe-wrap';
  wrap.style.cssText = 'width:420px;';
  wrap.innerHTML = `
    <div class="cms-file-card" id="probe-row">
      <span class="cms-file-icon">F</span>
      <span class="cms-file-info"><span class="cms-file-name">A file</span></span>
    </div>
    <video id="probe-video" style="width:320px;height:180px;"></video>
    <textarea id="probe-textarea" rows="4"></textarea>
    <div class="cms-account-flash ok" id="probe-flash">A message</div>`;
  document.body.appendChild(wrap);
  return true;
}
"""

MEASURE = """
(shape) => {
  //  On the WRAPPER, not on <html>. `data-corner-style` is a section's
  //  own override, and it works by inheritance: custom properties cascade
  //  to descendants, so the nearest ancestor that sets one wins for
  //  everything inside it. Put on <html> it would be arguing with the
  //  page's own theme block at equal specificity -- a fight the theme
  //  wins on source order, and a fight the real app never has, because
  //  the site-wide shape has only one source.
  document.getElementById('probe-wrap').setAttribute('data-corner-style', shape);
  const read = id => {
    const el = document.getElementById(id);
    const cs = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return { h: Math.round(box.height), w: Math.round(box.width),
             padTop: cs.paddingTop, padLeft: cs.paddingLeft,
             radius: cs.borderTopLeftRadius, radiusFull: cs.borderRadius };
  };
  return { row: read('probe-row'), video: read('probe-video'),
           textarea: read('probe-textarea'), flash: read('probe-flash') };
}
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1200, "height": 900})
    if COOKIE:
        host = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]
        ctx.add_cookies([{"name": "session", "value": COOKIE,
                          "domain": host, "path": "/"}])
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="networkidle")
    page.evaluate(PAGE)

    print()
    print("A short wide box is not made four times taller to clear a curve")
    print("-" * 70)
    for shape in GENTLE + DRAMATIC:
        got = page.evaluate(MEASURE, shape)
        row = got["row"]
        #  The box is 420 wide and holds one line. Anything past ~140px
        #  is the percentage-of-width fault, which produced 352.
        check("%s: the file card stays a row" % shape, row["h"] <= 140,
              "%dpx tall, padding-top %s" % (row["h"], row["padTop"]))
        check("%s: a message bar too" % shape, got["flash"]["h"] <= 140,
              "%dpx tall" % got["flash"]["h"])

    print()
    print("...and a dramatic shape still insets it horizontally")
    print("-" * 70)
    for shape in DRAMATIC:
        got = page.evaluate(MEASURE, shape)
        left = float(got["row"]["padLeft"].replace("px", "") or 0)
        #  The curve really does eat the ends, so there has to be more
        #  than a gentle shape's 20px -- the fix is not "turn it off".
        check("%s: the ends of the row are cleared" % shape, left >= 30,
              "padding-left %s" % got["row"]["padLeft"])

    print()
    print("A video keeps its controls, whatever shape the site is")
    print("-" * 70)
    for shape in GENTLE + DRAMATIC:
        got = page.evaluate(MEASURE, shape)
        radius = got["video"]["radius"]
        #  A length, and a modest one. A percentage here means the cap
        #  was not applied -- which is exactly what clamp() did on a lens.
        check("%s: the video's corner is a length" % shape,
              "%" not in got["video"]["radiusFull"], got["video"]["radiusFull"])
        value = float(radius.replace("px", "") or 0)
        check("%s: ...and small enough to keep the play bar" % shape,
              value <= 30, radius)

    print()
    print("A textarea does not become a stadium standing on end")
    print("-" * 70)
    for shape in DRAMATIC:
        got = page.evaluate(MEASURE, shape)
        value = float(got["textarea"]["radius"].replace("px", "") or 0)
        check("%s: the textarea is capped" % shape,
              "%" not in got["textarea"]["radiusFull"] and value <= 20,
              got["textarea"]["radiusFull"])

    print()
    print("A gentle shape is left alone")
    print("-" * 70)
    for shape in GENTLE:
        got = page.evaluate(MEASURE, shape)
        #  No inset at all: a gentle corner needs none, and adding one
        #  would be styling around a problem that is not there.
        check("%s: the row keeps its own padding" % shape,
              got["row"]["padLeft"] in ("20px", "16px"), got["row"]["padLeft"])

    print()
    print("...and these rules can actually fail")
    print("-" * 70)
    #  A check that cannot fail passes everything, and this file has two
    #  that are one typo away from being that. So the old, broken values
    #  are applied on purpose and the same measurements taken: if they do
    #  not come back wrong, the check above was measuring nothing.
    broken = page.evaluate("""
      () => {
        const wrap = document.getElementById('probe-wrap');
        wrap.setAttribute('data-corner-style', 'pill');
        //  What it used to be: a percentage of WIDTH on every side.
        wrap.style.setProperty('--site-radius-pad-row', 'min(24%, 88px) min(22%, 104px)');
        //  ...and a cap that cannot cap a lens. It has to go through
        //  var() to reproduce: written literally, the CSSOM simply
        //  rejects it and keeps whatever was there. Through var() the
        //  browser accepts the declaration, substitutes, and only THEN
        //  finds it invalid -- which is "invalid at computed-value
        //  time", and means unset rather than the previous value. That
        //  distinction is the entire bug.
        const sheet = document.createElement('style');
        sheet.textContent =
          '#probe-video { --lens: 50% / 30%;' +
          ' border-radius: clamp(0px, var(--lens), 28px) !important; }';
        document.head.appendChild(sheet);
        const v = document.getElementById('probe-video');
        return { rowH: Math.round(document.getElementById('probe-row').getBoundingClientRect().height),
                 videoRadius: getComputedStyle(v).borderRadius };
      }""")
    check("the old padding really did make a row four times too tall",
          broken["rowH"] > 140, "%dpx" % broken["rowH"])
    #  Unset, i.e. 0 -- not the 28px cap it was written to apply, and not
    #  the shape either. The rule was doing nothing at all.
    check("the old cap really did fail to cap",
          broken["videoRadius"] in ("0px", "", "0px 0px 0px 0px"),
          broken["videoRadius"])

    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
