"""A floating basket leaves nothing behind, for a VISITOR as well.

Worth its own net because this bug has now shipped twice, the same shape
both times. The basket's Position control can lift it out of the page and
pin it to a corner. The section it came from is then empty, and an empty
section that still paints is a placeholder sitting in the middle of
somebody's header.

It was found the first time while editing, fixed where it was found --
`.cms-editing .cms-section:has(...) > .block-html { display: contents }`
-- and the visitor kept the box, because the rule that fixed it was
written under `.cms-editing`. Measured on a live page: a 30x18 pill with
the site's card background, a 1px border and a 999px radius, under the
menu, containing nothing.

Neither round was visible from the server. The markup is identical either
way; what differs is which boxes have a size, and only a browser knows
that. So this runs in one, against a real instance, and it puts a real
basket on a real header rather than asserting about a stylesheet.

Two things it will not let regress:

  * `display: contents`, never `display: none`, on anything that CONTAINS
    the floating link. A fixed child of a display:none parent is not
    rendered at all -- that mistake has also been made twice on this same
    element, and it makes the basket vanish rather than linger.
  * the editing strip stays the tool panel and nothing more. Re-showing
    the whole section to keep the panel reachable is what produced the
    95px empty band an owner reported as a placeholder.

    python tools/basket_check.py <base-url> <cookie-file>

It adds a basket to the active template's header, measures, and removes
it again -- so it leaves the site as it found it.
"""
import io
import sys
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip()
HOST = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]

ok = bad = 0


def check(what, passed, detail=""):
    global ok, bad
    if passed:
        ok += 1
        print("  %-56s ok" % what)
    else:
        bad += 1
        print("  %-56s FAILED  %s" % (what, detail))


def post(path, fields):
    """One admin POST, with the Origin the CSRF middleware asks for."""
    req = urllib.request.Request(
        BASE + path,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Cookie": "session=" + COOKIE,
                 "Origin": BASE,
                 "Referer": BASE + "/",
                 "X-Inline-Edit": "1"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def get(path):
    req = urllib.request.Request(BASE + path,
                                 headers={"Cookie": "session=" + COOKIE,
                                          "X-Inline-Edit": "1"})
    with urllib.request.urlopen(req) as res:
        return res.read().decode("utf-8", "replace")


#  Both looked up off the page in edit mode, which is where the app
#  itself says them: the zone's own add-a-section URL carries the active
#  template's id, and the tool chips carry theirs. Reading them from
#  there rather than from a screen that only implies which is active is
#  what lets this run against any install.
import re                                                      # noqa: E402

editing = get("/?edit=1")

zone = re.search(r'/admin/templates/(\d+)/header/sections/new', editing)
tool = re.search(r'data-tool-id="(\d+)"[^>]*data-tool-name="Basket"', editing)

if not zone:
    print("This page has no header zone to put a basket in.")
    sys.exit(2)
if not tool:
    print("Could not find the Basket tool on this install.")
    sys.exit(2)
TEMPLATE, TOOL = zone.group(1), tool.group(1)

status, body = post("/admin/templates/%s/header/sections/new" % TEMPLATE,
                    {"tool_id": TOOL})
made = re.search(r'"id"\s*:\s*(\d+)', body)
if not made:
    print("Could not add a basket to the header: %s %s" % (status, body[:200]))
    sys.exit(2)
SECTION = made.group(1)

try:
    post("/admin/sections/%s/basket-update" % SECTION,
         {"basket_style": "icon", "basket_align": "float-top", "basket_icon": "bag"})

    with sync_playwright() as p:
        b = p.chromium.launch()

        print()
        print("A visitor sees the basket and nothing where it used to be")
        print("-" * 66)
        page = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.goto(BASE + "/", wait_until="networkidle")

        check("the basket is on screen", page.evaluate(
            """() => { const n = document.querySelector('.cms-basket-link');
                 if (!n) return false;
                 const r = n.getBoundingClientRect();
                 return r.width > 20 && r.height > 20; }"""))
        check("...pinned to the viewport rather than sitting in the row",
              page.evaluate("() => getComputedStyle("
                            "document.querySelector('.cms-basket-link')).position")
              == "fixed")

        #  The whole bug, in one number. Every box between the link and
        #  the header zone has to have no size: the section, the block
        #  around it, and anything a later change puts in between.
        left = page.evaluate(
            """() => { let el = document.querySelector('.cms-basket-link').parentElement;
                 const out = [];
                 while (el && !el.classList.contains('site-header-zone')) {
                   const r = el.getBoundingClientRect();
                   if (r.width > 0 || r.height > 0) {
                     out.push(String(el.className).split(' ')[0] + ' '
                       + Math.round(r.width) + 'x' + Math.round(r.height));
                   }
                   el = el.parentElement;
                 }
                 return out; }""")
        check("it leaves no box behind it at all", not left, "; ".join(left))

        print()
        print("...and it does not vanish while being edited")
        print("-" * 66)
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        ctx.add_cookies([{"name": "session", "value": COOKIE,
                          "domain": HOST, "path": "/"}])
        ed = ctx.new_page()
        ed.goto(BASE + "/?edit=1", wait_until="networkidle")

        #  `display: none` on any ancestor would fail exactly here, and
        #  nowhere else: the markup is unchanged and the server is happy.
        check("the basket is still on screen", ed.evaluate(
            """() => { const n = document.querySelector('.cms-basket-link');
                 if (!n) return false;
                 const r = n.getBoundingClientRect();
                 return r.width > 20 && r.height > 20; }"""))
        check("its tool panel is reachable", ed.evaluate(
            """() => { const s = document.querySelector(
                         '.cms-section:has(.cms-basket-align-float-top)');
                 const p = s && s.querySelector('.cms-tool-panel');
                 return !!p && p.getBoundingClientRect().height > 0; }"""))
        panel = ed.evaluate(
            """() => { const s = document.querySelector(
                         '.cms-section:has(.cms-basket-align-float-top)');
                 return getComputedStyle(s.querySelector('.cms-tool-panel'),
                                         '::before').content; }""")
        check("...and says where the basket went", "floats" in panel, panel)
        #  An em dash that has been through a bad encoding becomes a C1
        #  control character, which is invisible in every editor. One did.
        check("...in text with no mangled characters in it",
              all(not (ord(c) < 32 or 127 <= ord(c) <= 159) for c in panel),
              repr(panel))

        gap = ed.evaluate(
            """() => { const s = document.querySelector(
                         '.cms-section:has(.cms-basket-align-float-top)');
                 const p = s.querySelector('.cms-tool-panel');
                 return Math.round(s.getBoundingClientRect().height
                                   - p.getBoundingClientRect().height); }""")
        check("the strip it sits on is the panel and nothing else",
              gap <= 14, str(gap) + "px of box around the panel")

        b.close()
finally:
    #  Leave the site as it was found, whatever happened above.
    post("/admin/sections/%s/delete" % SECTION, {})

print()
print("  %d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
