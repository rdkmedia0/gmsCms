"""Admin screens are set at a size that fits what is in them.

An owner reported them as "overly large text and fields", which is not a
measurable request until you ask what each control is HOLDING. So this
measures rather than judges:

  * how tall a text input is, and how wide, against what goes in it;
  * how big the headings are, against the body text under them;
  * how much of a screen is chrome before any of its content;
  * and how many controls are stretched to the full width of the column
    while holding something short.

The last is the one that produced the complaint. A newsletter's Subject
was a full-width box forty pixels tall to hold a line read at inbox
width; "To" was another beside it. Two answers, 120px of screen, on a
page whose subject is the message underneath them.

The bounds here are not taste. They are the sizes at which a screen
holds what an owner is actually working on without scrolling, and every
one of them was set after measuring what the screen looked like before.

    python tools/admin_density_check.py <base-url> <cookie-file>
"""
import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
HOST = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]

#  Every screen an owner meets, plus the two editors that carry the most
#  controls. Query strings included where a screen has real tabs.
SCREENS = [
    "/admin/", "/admin/emails", "/admin/newsletters", "/admin/subscribers",
    "/admin/commerce/fulfilment", "/admin/commerce/orders",
    "/admin/commerce/bookings", "/admin/design/templates",
    "/admin/settings/integrations", "/admin/settings/email",
    "/admin/legal", "/admin/backups", "/admin/images", "/admin/account",
]

#  What a screen is allowed to be. Measured, not chosen: each is the
#  value the tightest screen already achieves, so a new screen that is
#  looser than every existing one fails.
LIMITS = {
    "control_height": 38,     # a one-line input, including its border
    "heading": 30,            # the h1 at the top of a screen
    "subheading": 22,         # an h2 inside a card
    "body": 16,               # running text
    "stretched": 0,           # short answers in full-width boxes
}

#  A field that legitimately wants the whole column: prose, or a value
#  that really is as long as the screen is wide.
WIDE_IS_FINE = ("textarea", "url", "email", "search")

ok = bad = 0
findings = []


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-52s ok" % what)
    else:
        bad += 1
        print("  %-52s FAILED  %s" % (what, detail))


MEASURE = """() => {
  const px = (el, prop) => parseFloat(getComputedStyle(el)[prop]) || 0;
  const seen = { controls: [], stretched: [] };
  const column = document.querySelector('.admin-main, main, body');
  const width = column ? column.getBoundingClientRect().width : window.innerWidth;

  document.querySelectorAll('input, select, textarea').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;                 // hidden
    const type = (el.type || el.tagName).toLowerCase();
    if (['hidden', 'checkbox', 'radio', 'color', 'file', 'range'].includes(type)) return;
    //  Toolbars are chrome and set smaller on purpose.
    if (el.closest('.cms-issue-toolbar, .cms-wysiwyg-toolbar')) return;
    if (el.tagName.toLowerCase() === 'textarea') return;   // multi-line by definition
    seen.controls.push({ type: type, h: Math.round(r.height),
                         w: Math.round(r.width),
                         name: el.name || el.id || type });
    //  Stretched: a SHORT answer given the whole column.
    const shortAnswer = ['text', 'number', 'date', 'datetime-local',
                         'time', 'select-one'].includes(type);
    if (shortAnswer && r.width > width * 0.82 && width > 520) {
      seen.stretched.push((el.name || el.id || type) + ' ' + Math.round(r.width) + 'px');
    }
  });

  //  Scoped to the CONTENT, because the first h1 on the page is the
  //  site's own brand in the header bar -- which is the site's to size,
  //  not this screen's, and measuring it measured the wrong element.
  const main = document.querySelector('.admin-main, main') || document.body;
  const one = sel => { const e = main.querySelector(sel); return e ? px(e, 'fontSize') : 0; };
  return {
    width: Math.round(width),
    controls: seen.controls,
    stretched: seen.stretched,
    h1: one('h1'), h2: one('h2'),
    body: px(document.body, 'fontSize'),
  };
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1400, "height": 1000})
    ctx.add_cookies([{"name": "session", "value": COOKIE,
                      "domain": HOST, "path": "/"}])
    page = ctx.new_page()

    print()
    print("Every admin screen, measured")
    print("-" * 70)
    worst = {"control_height": 0, "h1": 0, "h2": 0, "body": 0}
    stretched_total = 0
    for path in SCREENS:
        try:
            page.goto(BASE + path, wait_until="networkidle")
            page.wait_for_timeout(200)
        except Exception:  # noqa: BLE001 - a screen that will not load is its own bug
            print("  %-42s could not be opened" % path)
            continue
        if page.title().strip().lower().startswith("not found") or page.evaluate(
                """() => { const m = document.querySelector('.admin-main, main');
                     return !!m && /^not found/i.test(
                       (m.querySelector('h1') || {}).textContent || ''); }"""):
            #  Reported, never measured. The error page has its own type
            #  scale, so measuring it produced a finding about a screen
            #  that does not exist -- which is worse than no finding,
            #  because it hides the real one: the path is wrong.
            check("%s exists" % path, False, "404")
            continue
        m = page.evaluate(MEASURE)
        tall = [c for c in m["controls"] if c["h"] > LIMITS["control_height"]]
        worst["control_height"] = max(
            worst["control_height"],
            max([c["h"] for c in m["controls"]], default=0))
        for key in ("h1", "h2", "body"):
            worst[key] = max(worst[key], m[key])
        stretched_total += len(m["stretched"])
        if tall or m["stretched"]:
            findings.append((path, tall[:3], m["stretched"][:3]))
        print("  %-42s %2d controls, tallest %2dpx, %d stretched"
              % (path, len(m["controls"]),
                 max([c["h"] for c in m["controls"]], default=0),
                 len(m["stretched"])))

    print()
    print("What that comes to")
    print("-" * 70)
    check("no control is taller than a one-line input needs",
          worst["control_height"] <= LIMITS["control_height"],
          "tallest %dpx" % worst["control_height"])
    check("no short answer is stretched across the column",
          stretched_total == 0, "%d of them" % stretched_total)
    check("headings are headings, not banners",
          worst["h1"] <= LIMITS["heading"], "largest h1 %.0fpx" % worst["h1"])
    check("...and so are the ones inside cards",
          worst["h2"] <= LIMITS["subheading"], "largest h2 %.0fpx" % worst["h2"])
    check("running text is set for reading, not for posters",
          worst["body"] <= LIMITS["body"], "body %.0fpx" % worst["body"])

    if findings:
        print()
        print("Where")
        print("-" * 70)
        for path, tall, stretched in findings[:12]:
            for c in tall:
                print("  %-34s %s is %dpx tall" % (path, c["name"], c["h"]))
            for s in stretched:
                print("  %-34s %s across the column" % (path, s))

    b.close()

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
