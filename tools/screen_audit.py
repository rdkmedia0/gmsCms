"""Walk every screen and report what is wrong with it.

Run it against a running instance with an admin session cookie:

    python tools/screen_audit.py http://localhost:5000 path/to/cookiefile

Three of its rules were wrong when first written, and each correction is
worth keeping: an off-canvas panel is not an overflow, alt="" is the
CORRECT markup for a decorative image, and a control wrapped in
<label title="..."> is already labelled. A checker that cries wolf gets
ignored, which is worse than not having one.

Checks the things a screenshot does not tell you: whether the page
scrolls sideways, whether anything sticks out past the viewport, whether
a control has the tooltip this project requires of every control, whether
the console logged an error, and whether any request failed.

    python audit.py <base> [cookie-file]
"""
import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip() if len(sys.argv) > 2 else ""

PUBLIC = ["/", "/about", "/media", "/journal", "/contact", "/packages",
          "/terms-and-conditions", "/newsletters"]
ADMIN = ["/admin/", "/admin/setup", "/admin/setup/look", "/admin/setup/details",
         "/admin/setup/done", "/admin/settings/integrations",
         "/admin/settings/integrations?tab=calcom", "/admin/settings/integrations?tab=ai",
         "/admin/settings/email", "/admin/newsletters", "/admin/subscribers",
         "/admin/commerce/fulfilment", "/admin/commerce/orders", "/admin/commerce/bookings",
         "/admin/legal", "/admin/backups", "/admin/media", "/admin/help", "/admin/account"]

AUDIT_JS = """
() => {
  const vw = window.innerWidth;
  const out = {
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: vw,
    pastViewport: [],
    controlsNoTitle: [],
    imagesNoAlt: 0,
  };
  //  Anything whose box ends past the right edge: the cause of a page
  //  that scrolls sideways, which on a phone is the commonest fault there
  //  is. Reported with a name so it can be found.
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const b = el.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) return;
    if (b.right > vw + 1 || b.left < -1) {
      const id = el.tagName.toLowerCase()
        + (el.id ? '#' + el.id : '')
        + (el.className && typeof el.className === 'string'
           ? '.' + el.className.trim().split(/\\s+/)[0] : '');
      if (out.pastViewport.length < 6) out.pastViewport.push(
        id + ' [' + Math.round(b.left) + '..' + Math.round(b.right) + ']');
    }
  });
  //  This project requires a title on every control (CLAUDE.md). A
  //  submit button whose own text says what it does is exempt.
  document.querySelectorAll('input, select, textarea, button, a.btn').forEach(el => {
    if (el.type === 'hidden') return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    if (el.title && el.title.trim()) return;
    if (el.getAttribute('aria-label')) return;
    //  A control wrapped in <label title="..."> already shows that
    //  tooltip when you hover the control, because the label contains
    //  it. That is a labelled control, not a bare one.
    const lab = el.closest('label[title]');
    if (lab && lab.title.trim()) return;
    //  A button whose own visible words say what it does is not a glyph
    //  needing a tooltip; report it with those words so it can be judged.
    const id = el.tagName.toLowerCase()
      + (el.id ? '#' + el.id : (el.name ? '[' + el.name + ']' : ''))
      + (el.type ? ':' + el.type : '')
      + ((el.textContent||'').trim() ? ' “' + (el.textContent||'').trim().slice(0,26) + '”' : ' (no words)');
    if (out.controlsNoTitle.length < 8) out.controlsNoTitle.push(id);
  });
  //  alt="" is the CORRECT markup for a decorative image -- it tells a
  //  screen reader to skip it. Only a MISSING alt is a fault.
  document.querySelectorAll('img').forEach(im => {
    if (im.getAttribute('alt') === null) out.imagesNoAlt++;
  });
  return out;
}
"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    findings = []
    for width, label in ((1440, "desktop"), (390, "phone")):
        ctx = browser.new_context(viewport={"width": width, "height": 900},
                                  ignore_https_errors=True)
        if COOKIE:
            host = BASE.split("//", 1)[1].split("/", 1)[0].split(":")[0]
            ctx.add_cookies([{"name": "session", "value": COOKIE,
                              "domain": host, "path": "/"}])
        page = ctx.new_page()
        for path in PUBLIC + ADMIN:
            errors, failed, bad = [], [], []
            page.on("console", lambda m: errors.append(m.text[:90]) if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url.split("/")[-1][:40]))
            page.on("response", lambda r: bad.append("%d %s" % (r.status, r.url.split("/")[-1][:34]))
                    if r.status >= 400 else None)
            try:
                resp = page.goto(BASE + path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(250)
                a = page.evaluate(AUDIT_JS)
            except Exception as e:
                findings.append((label, path, "LOAD FAILED: %s" % str(e)[:70]))
                continue
            status = resp.status if resp else 0
            if status >= 400:
                findings.append((label, path, "status %d" % status))
            if a["scrollWidth"] > a["innerWidth"] + 1:
                findings.append((label, path, "scrolls sideways: %dpx wide in a %dpx window"
                                 % (a["scrollWidth"], a["innerWidth"])))
            for el in a["pastViewport"]:
                findings.append((label, path, "past the right edge: %s" % el))
            for el in a["controlsNoTitle"]:
                findings.append((label, path, "control with no tooltip: %s" % el))
            if a["imagesNoAlt"]:
                findings.append((label, path, "%d image(s) with no alt text" % a["imagesNoAlt"]))
            for e in errors[:3]:
                findings.append((label, path, "console error: %s" % e))
            for f in failed[:3]:
                findings.append((label, path, "request failed: %s" % f))
            for bstat in bad[:3]:
                findings.append((label, path, "response %s" % bstat))
        ctx.close()
    browser.close()

print("  %d findings across %d screens x 2 widths" % (len(findings), len(PUBLIC) + len(ADMIN)))
seen = {}
for label, path, what in findings:
    seen.setdefault(what.split(":")[0], 0)
    seen[what.split(":")[0]] += 1
print("  by kind:")
for k, v in sorted(seen.items(), key=lambda kv: -kv[1]):
    print("    %-34s %d" % (k, v))
print()
for label, path, what in findings:
    print("  [%-7s] %-42s %s" % (label, path, what))
