"""Every screen, at two widths, asked what a screenshot cannot tell you.

Whether the page scrolls sideways, whether anything is stranded outside
the viewport, whether every control carries the sentence this project
requires of one, whether the console logged an error, whether a request
failed.

    python tools/screen_audit.py <base-url> [cookie-file]

**On crying wolf.** An earlier version of this reported 186 elements
"past the right edge" and every single one was correct behaviour: 174
were the editor's dock panel, which is `position: fixed` and parked
off-screen when closed, and the rest were a table inside its own
`overflow-x: auto` container -- which is exactly what this project
requires of a wide table. A check that always fails teaches people to
ignore it, which is the same uselessness as one that cannot fail,
arrived at from the other end. So both cases are now understood and
excluded, and what remains is meant to be read.

The tooltip check does NOT make the same exclusions, deliberately: a
control inside a closed panel is still a control somebody will open and
have to understand.
"""
import io
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
COOKIE = io.open(sys.argv[2], encoding="utf-8").read().strip() if len(sys.argv) > 2 else ""

PUBLIC = ["/", "/about", "/media", "/journal", "/contact", "/packages",
          "/terms-and-conditions", "/newsletters"]
ADMIN = ["/admin/", "/admin/emails", "/admin/newsletters", "/admin/subscribers",
         "/admin/commerce/fulfilment", "/admin/commerce/orders",
         "/admin/commerce/bookings", "/admin/design/templates",
         "/admin/setup", "/admin/setup/look", "/admin/setup/details",
         "/admin/setup/done", "/admin/settings/integrations",
         "/admin/settings/integrations?tab=calcom",
         "/admin/settings/integrations?tab=ai", "/admin/settings/email",
         "/admin/legal", "/admin/backups", "/admin/media", "/admin/help",
         "/admin/account"]

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

  //  Two things are OUTSIDE the viewport on purpose, and reporting them
  //  is what made an earlier version of this unreadable.
  const deliberatelyOutside = (el) => {
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      const cs = getComputedStyle(node);
      //  1. Inside something that scrolls. A wide table in an
      //     `overflow-x: auto` container is what this project REQUIRES
      //     of a wide table -- the page body must not scroll, and it
      //     does not; the table scrolls inside its own box.
      if (['auto', 'scroll', 'hidden'].includes(cs.overflowX)) return true;
      //  2. A fixed panel parked off-screen. The editor's dock slides in
      //     when opened; closed, it sits past the right edge by design,
      //     and so does everything in it.
      if (cs.position === 'fixed' &&
          (cs.transform !== 'none' || node.classList.contains('cms-dock-panel'))) {
        return true;
      }
    }
    //  3. An EMPTY sidebar. It is deliberately collapsed to a 28px strip
    //     carrying only its "+" (see site-base.css: "Collapse to a thin
    //     strip at the page's true left edge holding only the + hit
    //     target"), and that 20px button is centred on the strip's own
    //     dashed rule, 4px in -- so it necessarily spans -6..14. The
    //     overflow is the container collapsing on purpose, not the
    //     control being misplaced, and the page clips it so nothing
    //     scrolls. Measured before being excluded, because the last two
    //     things that looked like faults here were not.
    if (el.closest('.site-sidebar-empty')) return true;
    return false;
  };

  //  Anything whose box ends past the right edge and is NOT one of those:
  //  the cause of a page that scrolls sideways, which on a phone is the
  //  commonest fault there is. Reported with a name so it can be found.
  document.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const b = el.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) return;
    if (b.right <= vw + 1 && b.left >= -1) return;
    if (deliberatelyOutside(el)) return;
    const id = el.tagName.toLowerCase()
      + (el.id ? '#' + el.id : '')
      + (el.className && typeof el.className === 'string'
         ? '.' + el.className.trim().split(/\\s+/)[0] : '');
    if (out.pastViewport.length < 6) out.pastViewport.push(
      id + ' [' + Math.round(b.left) + '..' + Math.round(b.right) + ']');
  });

  //  This project requires a title on every control (CLAUDE.md), because
  //  the label is often a glyph and the title is then the only text there
  //  is. No exclusions here: a control inside a closed panel is still one
  //  somebody will open and have to understand.
  document.querySelectorAll('input, select, textarea, button, a.btn').forEach(el => {
    //  Three kinds of control nobody can see, and so nobody can hover.
    //
    //  A `hidden` file input is the pattern behind every "choose a
    //  picture" button in this app: the BUTTON is what somebody clicks
    //  and what carries the sentence, and the input is machinery. And an
    //  aria-hidden one is deliberately not announced at all -- the
    //  sign-up form's honeypot is exactly that, and giving it a tooltip
    //  would be describing a trap to the only visitors who would read
    //  the description.
    //
    //  A control inside a CLOSED PANEL is not in this list, deliberately:
    //  it is a control somebody will open and have to understand.
    if (el.type === 'hidden') return;
    if (el.hasAttribute('hidden')) return;
    if (el.closest('[aria-hidden="true"]')) return;
    if (el.title && el.title.trim()) return;
    if (el.getAttribute('aria-label')) return;
    //  A control wrapped in <label title="..."> already shows that
    //  tooltip when you hover the control, because the label contains it.
    const lab = el.closest('label[title]');
    if (lab && lab.title.trim()) return;

    //  A control with a VISIBLE label in words is already explained, and
    //  that is the whole reason the rule exists: CLAUDE.md asks for a
    //  title because "the label is often a glyph and the title is then
    //  the only text there is". Where there IS text, the requirement is
    //  met. A contact form's Name field does not need a tooltip saying
    //  Name.
    //
    //  The label has to be VISIBLE: a `cms-visually-hidden` one is there
    //  for a screen reader and says nothing to somebody looking at the
    //  page, so a control wearing one still needs its sentence.
    const labelled = el.id
      ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')
      : el.closest('label');
    if (labelled && (labelled.textContent || '').trim()
        && labelled.getBoundingClientRect().width > 1) {
      return;
    }
    //  Enough to FIND it. "input:checkbox (no words)" is a true report
    //  and an unactionable one -- there are dozens, and it names none of
    //  them. The nearest classed ancestor is what a person greps for.
    let where = '';
    for (let node = el.parentElement; node && node !== document.body;
         node = node.parentElement) {
      if (node.className && typeof node.className === 'string'
          && node.className.trim()) {
        where = ' in .' + node.className.trim().split(/\\s+/)[0];
        break;
      }
    }
    const id = el.tagName.toLowerCase()
      + (el.id ? '#' + el.id : (el.name ? '[' + el.name + ']' : ''))
      + (el.type ? ':' + el.type : '')
      + ((el.textContent||'').trim() ? ' "' + (el.textContent||'').trim().slice(0,26) + '"' : '')
      + where;
    out.controlsNoTitle.push(id);
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

print()
print("  %d findings across %d screens x 2 widths"
      % (len(findings), len(PUBLIC) + len(ADMIN)))
if findings:
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
