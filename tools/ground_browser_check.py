"""Is the body REALLY the ground colour, on every template, in a browser?

The server-side half (ground_check.py) proves the token is emitted. This
proves the cascade: each template's real theme.css is loaded over
site-base.css with a distinctive ground, ink, tint and hairline set, and
the computed colours of the body, the header, the footer and a
paragraph are read back. A theme that paints the body itself, or hands a
paragraph a literal colour, shows up here and nowhere else.

Run on the HOST against a running site (the theme files are served from
it; the site's own pages are never opened):

    python tools/ground_browser_check.py http://127.0.0.1:5000
"""
import glob
import os
import re
import sys

from playwright.sync_api import sync_playwright

base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
slugs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, "app", "data", "templates", "*"))
               if os.path.isdir(p))

GROUND, INK, TINT, LINE = "#123456", "#fedcba", "#234567", "#345678"
#  The one surface everything on the page sits on -- what the app emits
#  as --site-card-bg for this ground (a lifted step of it, since it is
#  dark). A theme pinning a card to --accent-50 stays cream and hands the
#  pale ink a cream box to vanish on.
CARD = "#1e3a5f"
#  What the app would emit for a brand heading on this ground: a pale
#  step that reads. A theme reading --site-primary-text or
#  --site-secondary-text passes; a theme pinning its headings to a ramp
#  step (--primary-600, ground-blind) does not, which is the fault this
#  is here to catch.
PRIMARY_TEXT = "#ffd8a8"
#  Zones that are the page (a strip of the ground, or the alternate band)
#  rather than a brand-coloured bar. A brand-coloured header is a design
#  choice and follows the palette, not the ground.
FOLLOWS = {
    "bakery": ("header",), "business": ("header",), "clinic": ("header", "footer"),
    "coaching": ("header", "footer"), "cv": ("header",), "hair-salon": ("header",),
    "restaurant": ("header",), "self-help": ("header", "footer"), "shop": ("header",),
    "venue": ("header",),
}


def rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def parse(css_colour):
    """(r, g, b), alpha -- from rgb()/rgba(), or the color(srgb r g b / a)
    form a browser reports for anything that went through color-mix()."""
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)", css_colour or "")
    if m:
        return tuple(int(m.group(i)) for i in (1, 2, 3)), float(m.group(4) or 1)
    m = re.match(r"color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: / ([\d.]+))?\)", css_colour or "")
    if m:
        return tuple(round(float(m.group(i)) * 255) for i in (1, 2, 3)), float(m.group(4) or 1)
    return None, 0.0


def same(css_colour, expected_hex, min_alpha=0.85):
    got, alpha = parse(css_colour)
    return got == rgb(expected_hex) and alpha >= min_alpha


def _lum(rgb_tuple):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb_tuple)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(css_colour, against_hex):
    """WCAG contrast of a computed colour against a hex ground. A heading
    may be the ink or a brand colour -- what matters is that it reads."""
    got, _ = parse(css_colour)
    if not got:
        return 0.0
    a, b = _lum(got), _lum(rgb(against_hex))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def contrast_css(text_css, bg_css):
    """The same, between two computed colours. A translucent surface is
    read as its own colour: at 90% over the ground that is what it is."""
    t, _ = parse(text_css)
    b, alpha = parse(bg_css)
    if not t or not b:
        return 0.0
    if alpha < 0.85:
        b = rgb(GROUND)
    lt, lb = _lum(t), _lum(b)
    return (max(lt, lb) + 0.05) / (min(lt, lb) + 0.05)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{base}/static/css/site-base.css">
{theme}
<style>:root{{--site-ground:{g};--site-ink:{i};--site-tint:{t};--site-line:{l};--site-card-bg:{c};--site-primary-text:{pt};--site-secondary-text:{pt};--site-accent-text:{pt};}}</style>
</head><body>
<header class="site-header"><nav class="site-nav"><a href="#">Menu</a></nav></header>
<main><section class="cms-section"><h2>A heading</h2><p>Some words on the page.</p>
<div class="cms-card-shape"><p>Card words.</p></div>
<div class="cms-blog-card"><p>Blog card words.</p></div>
<div class="cms-price-tier"><p>Price words.</p></div>
<div class="cms-quote-card"><p>Quote words.</p></div>
<div class="cms-stat"><span class="cms-stat-value">42</span><p>Stat words.</p></div>
<div class="block-html"><p>Embed words.</p></div>
</section></main>
<footer class="site-footer"><p>Footer words.</p></footer>
</body></html>"""

passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    print("%-62s %s%s" % (what, "ok" if ok else "FAILED",
                          ("  " + str(detail)) if detail and not ok else ""))
    passed += bool(ok)
    failed += not ok


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    for slug in slugs:
        theme_url = f"{base}/static/themes/{slug}/theme.css"
        has_css = page.request.get(theme_url).status == 200
        link = f'<link rel="stylesheet" href="{theme_url}">' if has_css else ""
        page.set_content(PAGE.format(base=base, theme=link, g=GROUND, i=INK, t=TINT, l=LINE,
                                     c=CARD, pt=PRIMARY_TEXT))
        page.wait_for_timeout(150)
        got = page.evaluate("""() => {
            const c = (sel, prop) => { const el = document.querySelector(sel);
                return el ? getComputedStyle(el)[prop] : null; };
            return { body: c('body', 'backgroundColor'), header: c('.site-header', 'backgroundColor'),
                     footer: c('.site-footer', 'backgroundColor'), p: c('main p', 'color'),
                     h: c('main h2', 'color'), nav: c('.site-nav a', 'color'),
                     on: (() => {
                        //  Text reads on whatever it SITS on: the nearest painted
                        //  ancestor, which is the body if nothing nearer paints.
                        const bgOf = el => { for (let e = el; e; e = e.parentElement) {
                            const b = getComputedStyle(e).backgroundColor;
                            if (b && b !== 'rgba(0, 0, 0, 0)' && b !== 'transparent') return b; }
                            return null; };
                        const out = {};
                        //  The header's menu is an html tool inside .block-html,
                        //  so the "pill" behind it is that block's surface.
                        for (const sel of ['.cms-card-shape p', '.cms-blog-card p', '.cms-price-tier p',
                                           '.cms-quote-card p', '.cms-stat p', '.cms-stat .cms-stat-value',
                                           '.block-html p']) {
                            const el = document.querySelector(sel);
                            if (el) out[sel] = { text: getComputedStyle(el).color, bg: bgOf(el) };
                        }
                        return out;
                     })() };
        }""")
        label = f"{slug:<15}"
        check(f"{label} body is the ground", same(got["body"], GROUND), got["body"])
        check(f"{label} words take the ink", same(got["p"], INK), got["p"])
        #  A heading may keep a brand colour; it has to READ on the ground.
        #  Large text, so WCAG's 3:1 -- and the harness hands the page a
        #  --site-primary-text worked out for THIS ground, as the app does.
        check(f"{label} a heading reads on it", contrast(got["h"], GROUND) >= 3.0,
              "%s at %.1f:1" % (got["h"], contrast(got["h"], GROUND)))
        #  Every surface a tool puts words on: the words have to read on
        #  THAT surface, whatever colour the theme gave it.
        bad = []
        for sel, pair in got["on"].items():
            ratio = contrast_css(pair["text"], pair["bg"])
            if ratio < 4.5:
                bad.append("%s %.1f:1 (%s on %s)" % (sel, ratio, pair["text"], pair["bg"]))
        check(f"{label} words read on every surface", not bad, "; ".join(bad))
        for zone in FOLLOWS.get(slug, ()):
            ok = same(got[zone], GROUND) or same(got[zone], TINT)
            check(f"{label} {zone} follows the page", ok, got[zone])
    browser.close()

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
