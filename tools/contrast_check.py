"""Every piece of text on a page, measured against what is behind it.

Reading the stylesheet cannot answer this. Three separate things decide
what a word finally looks like -- the colour it was given, the opacity
of every box it sits inside, and which ancestor actually paints the
background it lands on -- and only a browser knows all three. So this
walks the rendered page, composites the opacity chain onto the first
opaque ancestor, and reports the contrast.

It exists because a page can fail this while every rule in it looks
sensible: `opacity: .7` on a heading is a reasonable-looking line that
becomes invisible the moment the ink is pale, and no server-side check
can see it happen.

Run it on the HOST, against a URL -- it needs a real browser.

  python tools/contrast_check.py http://localhost:5000 [template-id ...]

Thresholds are WCAG AA: 4.5:1 for body text, 3:1 for large text (24px,
or 18.66px when bold), which is the same arithmetic services/palette.py
uses when it picks a colour in the first place.
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WALK = " ".join([
  "() => {",
  "  const out = [];",
  #  A colour as four numbers, whatever notation it arrived in.
  "  const rgba = (s) => {",
  "    const m = (s || '').match(/[-0-9.]+/g);",
  "    if (!m) return null;",
  "    return [ +m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1 ];",
  "  };",
  "  const over = (top, bottom) => {",
  "    const a = top[3];",
  "    return [ top[0]*a + bottom[0]*(1-a),",
  "             top[1]*a + bottom[1]*(1-a),",
  "             top[2]*a + bottom[2]*(1-a), 1 ];",
  "  };",
  "  const lum = (c) => {",
  "    const f = (v) => { v /= 255; return v <= 0.03928 ? v/12.92 :",
  "                       Math.pow((v+0.055)/1.055, 2.4); };",
  "    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]);",
  "  };",
  "  const ratio = (a, b) => {",
  "    const l1 = lum(a), l2 = lum(b);",
  "    return (Math.max(l1,l2) + 0.05) / (Math.min(l1,l2) + 0.05);",
  "  };",
  #  What is actually behind this element: the first ancestor that
  #  paints something, with every translucent layer above it composited
  #  back down onto it. A background-IMAGE stops the walk -- a
  #  photograph has no single colour and this check must not invent one.
  "  const behind = (el) => {",
  "    let e = el, layers = [];",
  "    while (e) {",
  "      const cs = getComputedStyle(e);",
  "      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;",
  "      const bg = rgba(cs.backgroundColor);",
  "      if (bg && bg[3] > 0) { layers.push(bg); if (bg[3] >= 1) break; }",
  "      e = e.parentElement;",
  "    }",
  "    if (!layers.length) return [255,255,255,1];",
  "    let base = layers[layers.length-1];",
  "    if (base[3] < 1) base = over(base, [255,255,255,1]);",
  "    for (let i = layers.length-2; i >= 0; i--) base = over(layers[i], base);",
  "    return base;",
  "  };",
  #  Opacity is inherited by compositing, not by cascade: a 0.7 box
  #  inside a 0.7 box shows its text at 0.49.
  "  const faded = (el) => {",
  "    let e = el, a = 1;",
  "    while (e) { a *= parseFloat(getComputedStyle(e).opacity || '1');",
  "                e = e.parentElement; }",
  "    return a;",
  "  };",
  "  const seen = new Set();",
  "  document.querySelectorAll('body *').forEach((el) => {",
  "    if (el.closest('.cms-admin-bar, .cms-toolbar, .cms-dock, .cms-tool-panel')) return;",
  "    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());",
  "    if (!own) return;",
  "    const r = el.getBoundingClientRect();",
  "    if (r.width <= 2 || r.height <= 2) return;",
  "    const cs = getComputedStyle(el);",
  "    if (cs.visibility === 'hidden' || cs.display === 'none') return;",
  "    const bg = behind(el);",
  "    if (!bg) return;",
  "    let fg = rgba(cs.color);",
  "    if (!fg) return;",
  "    const a = faded(el) * (fg[3] === undefined ? 1 : fg[3]);",
  "    fg = over([fg[0], fg[1], fg[2], a], bg);",
  "    const px = parseFloat(cs.fontSize);",
  "    const w = parseInt(cs.fontWeight, 10) || 400;",
  "    const large = px >= 24 || (px >= 18.66 && w >= 700);",
  "    const need = large ? 3.0 : 4.5;",
  "    const got = ratio(fg, bg);",
  "    if (got >= need) return;",
  r"    const words = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 44);",
  "    const key = el.className + '|' + words;",
  "    if (seen.has(key)) return;",
  "    seen.add(key);",
  "    out.push({ sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'",
  r"                 ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''),",
  "               words: words, got: Math.round(got*100)/100, need: need,",
  "               px: Math.round(px), alpha: Math.round(a*100)/100 });",
  "  });",
  "  return out;",
  "}"])


def main():
    from playwright.sync_api import sync_playwright
    site = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    wanted = sys.argv[2:]
    session = io.open(".local-session").read().strip()

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        admin = b.new_context(viewport={"width": 1440, "height": 1000})
        admin.set_default_timeout(120000)
        admin.add_cookies([{"name": "session", "value": session,
                            "domain": site.split("//")[-1].split(":")[0], "path": "/"}])
        ap = admin.new_page()
        ap.goto(site + "/admin/design/templates", wait_until="load")
        rows = ap.evaluate("""() => [...document.querySelectorAll('[data-activate-url]')]
            .map(b => ({url: b.dataset.activateUrl,
                        name: (b.closest('[data-template-name]')||{}).dataset
                              ? (b.closest('[data-template-name]').dataset.templateName) : ''}))""")
        guest = b.new_context(viewport={"width": 1440, "height": 1000})
        gp = guest.new_page()

        total = 0
        matched = []
        for row in rows:
            #  The activate URL is /admin/templates/<id>/activate, so the
            #  second-from-last part is the ID, not the slug. Filtering by
            #  slug therefore matched NOTHING and the run reported "0
            #  failing" having checked nothing at all -- the same silent
            #  no-op this tool exists to catch, in the tool itself.
            #
            #  So a name that matches nothing is an ERROR, not an empty
            #  pass. A checker that can quietly check zero things is
            #  worse than no checker.
            #  The activate URL is /admin/templates/<id>/activate, so the
            #  second-from-last part is the template's ID. That is what
            #  this filters on -- the screen carries no name attribute,
            #  and guessing one from the surrounding markup is how the
            #  filter came to match NOTHING while reporting "0 failing".
            #  A checker that can quietly check zero things is worse than
            #  no checker, so an empty match is an error below.
            ident = row["url"].rstrip("/").split("/")[-2]
            label = ident
            if wanted and ident not in wanted:
                continue
            matched.append(label)
            ap.evaluate("""async (u) => fetch(u, {method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'force=1'})""", row["url"])
            ap.wait_for_timeout(900)
            #  EVERY page, not just the front one. A hero with no
            #  picture only appears on the pages that have no picture --
            #  which is the subpages -- so checking the home page alone
            #  said a template was fine while three of its pages carried
            #  white words on a cream band.
            gp.goto(site + "/", wait_until="load")
            gp.wait_for_timeout(900)
            bad = gp.evaluate(WALK)
            for href in gp.evaluate(
                    "() => [...document.querySelectorAll('.cms-menu a')]"
                    ".map(a => a.getAttribute('href'))"):
                if not href or not href.startswith("/") or href == "/":
                    continue
                gp.goto(site + href, wait_until="load")
                gp.wait_for_timeout(600)
                for one in gp.evaluate(WALK):
                    one["words"] = href + "  " + one["words"]
                    bad.append(one)

            if not bad:
                print("  %-26s ok" % label)
                continue
            total += len(bad)
            print("  %-26s %d unreadable" % (label, len(bad)))
            for f in bad[:12]:
                print("      %5.2f:1 (needs %.1f)  %-30s a=%.2f  %s"
                      % (f["got"], f["need"], f["sel"][:30], f["alpha"], f["words"]))
        b.close()
    print()
    missed = [w for w in wanted if w not in matched]
    if missed:
        #  The ACTIVE template has no Activate button, so it never
        #  appears in this list -- and asking for it produced a clean
        #  run that had silently skipped it. Anything asked for and not
        #  reached is a failure: a checker that can quietly check fewer
        #  things than it was told to is worse than no checker.
        print("  NOT CHECKED: %s" % ", ".join(missed))
        print("  (the active template has no Activate control -- activate")
        print("   something else first, then run this again)")
        return 1
    print("  %d failing" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
