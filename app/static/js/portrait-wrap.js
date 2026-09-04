// Text wrapping around a side banner portrait.
//
// A banner portrait is position:absolute inside the banner and overhangs the
// banner's bottom-outer corner into the SECTION beneath it. Whether the text
// there should wrap around it -- and by exactly how much -- is pure geometry:
// how far the picture reaches below the banner (a function of the banner's
// height, the portrait's size and the gap between the two sections) and where
// its round edge sits relative to the centred, narrower text column (a
// function of the viewport width). None of that can be read in static CSS
// across a section boundary, which is why this is measured here.
//
// What it does per side-portrait banner that is followed by a section:
//   * projects how far the portrait would overhang once the banner drops its
//     reserve (arithmetic, so no layout thrash from toggling to measure),
//   * if the picture actually reaches into the text column on a wide-enough
//     screen, drops the banner's reserve and reserves a float of exactly the
//     overhang's footprint, shaped with an ellipse so the text hugs the
//     ACTUAL curve and comes back to full width the moment it clears the
//     bottom of the picture -- nothing below it is held off,
//   * otherwise clears everything, so the CSS full reserve keeps the text
//     safely below the picture (also the no-JS fallback).
//
// Re-runs on the site refresh event (the editor swaps regions in place) and,
// debounced, on resize. Phones (< 641px) stack: the column is too narrow to
// set text beside a picture.
(function () {
  "use strict";

  var MIN_WIDTH = 641;   // below this the column is too narrow -- stack instead
  var GAP = 14;          // the small reserve the banner keeps so the picture overhangs
  var SHAPE_MARGIN = 8;  // the circle sits slightly larger than the picture
  var MIN_OVERHANG = 6;  // less than this and the picture does not really reach the text

  function clearFloat(section) {
    if (!section) return;
    section.classList.remove("cms-portrait-wrapping", "cms-portrait-wrapping-left", "cms-portrait-wrapping-right");
    ["--cms-pw-w", "--cms-pw-h", "--cms-pw-mt", "--cms-pw-ml", "--cms-pw-mr", "--cms-pw-shape", "--cms-pw-margin"]
      .forEach(function (p) { section.style.removeProperty(p); });
  }

  function clear(banner, section) {
    if (banner) banner.style.removeProperty("margin-bottom");
    clearFloat(section);
  }

  function applyOne(banner) {
    var section = banner.closest(".cms-section");
    // The next SECTION -- skipping the drop-zone dividers the editor inserts
    // between sections, which are the real next sibling while editing.
    var next = section && section.nextElementSibling;
    while (next && !next.classList.contains("cms-section")) next = next.nextElementSibling;
    if (!next) { clear(banner, null); return; }
    if (window.innerWidth < MIN_WIDTH) { clear(banner, next); return; }

    var portrait = banner.querySelector(".cms-banner-portrait");
    var pr = portrait && portrait.getBoundingClientRect();
    if (!pr || pr.width < 2 || pr.height < 2) { clear(banner, next); return; }  // hidden / none

    // The next section's padding box is the text column (measured, not assumed).
    var cs = getComputedStyle(next);
    var sr = next.getBoundingClientRect();
    var contentLeft = sr.left + (parseFloat(cs.paddingLeft) || 0);
    var contentRight = sr.right - (parseFloat(cs.paddingRight) || 0);
    var contentTop = sr.top + (parseFloat(cs.paddingTop) || 0);
    var colW = contentRight - contentLeft;
    if (colW < 40) { clear(banner, next); return; }

    var D = pr.width, H = pr.height;   // the picture's box (square for round, taller for oval)
    var rx = D / 2, ry = H / 2;
    var cx = pr.left + rx;

    // Which side is the portrait on? Read it from where the picture sits within
    // the BANNER (that is where left/centre/right is decided), MEASURED rather
    // than taken from the class -- so left, right and every per-view position
    // (centred on a phone, left on a laptop) are one path, at whatever the
    // current width renders. Judging it against the text column instead is
    // wrong: a narrow, offset column can put a hard-left picture's centre at
    // the column's middle. A picture over the middle of the BANNER can't be
    // wrapped (text would split around it), so it keeps the full reserve below.
    var br = banner.getBoundingClientRect();
    var placeFrac = (cx - br.left) / br.width;   // 0 = banner's left edge, 1 = its right
    if (placeFrac > 0.38 && placeFrac < 0.62) {
      // Centred: text can't wrap around both sides of it (a float pushes text
      // one way only), so it simply flows below. How far below is the OWNER's
      // call -- set by dragging the banner's height, exactly like a side
      // portrait -- so nothing is forced here; the reserve falls to the normal
      // rules the drag controls.
      clear(banner, next);
      return;
    }
    var side = placeFrac <= 0.5 ? "left" : "right";

    // Dropping the banner's reserve to GAP lifts the next section up by
    // (currentReserve - GAP); the portrait is anchored to the banner, so the
    // overhang grows by that much. Project it rather than toggling to measure.
    var currentMB = parseFloat(getComputedStyle(banner).marginBottom) || 0;
    var lift = Math.max(0, currentMB - GAP);
    var projectedTop = contentTop - lift;
    var overhang = pr.bottom - projectedTop;
    if (overhang < MIN_OVERHANG) { clear(banner, next); return; }  // sits above the text -- nothing to do

    // Does the picture actually reach into the column at all?
    if (side === "left"  && cx + rx <= contentLeft + 2)  { clear(banner, next); return; }
    if (side === "right" && cx - rx >= contentRight - 2)  { clear(banner, next); return; }

    // The reservation IS the whole picture: a box the portrait's size, pulled
    // up so it overlays the picture exactly (its top half lands back up in the
    // banner, harmlessly), then given the picture's own outline as its
    // shape-outside. The text wraps the real curve where it dips into the
    // column and returns to full width the instant it clears the bottom.
    banner.style.setProperty("margin-bottom", GAP + "px");
    next.classList.remove("cms-portrait-wrapping-left", "cms-portrait-wrapping-right");
    next.classList.add("cms-portrait-wrapping", "cms-portrait-wrapping-" + side);
    next.style.setProperty("--cms-pw-w", Math.round(D) + "px");
    next.style.setProperty("--cms-pw-h", Math.round(H) + "px");
    next.style.setProperty("--cms-pw-mt", Math.round(pr.top - projectedTop) + "px");
    next.style.setProperty("--cms-pw-margin", SHAPE_MARGIN + "px");
    if (side === "left") { next.style.setProperty("--cms-pw-ml", Math.round(pr.left - contentLeft) + "px"); next.style.removeProperty("--cms-pw-mr"); }
    else                 { next.style.setProperty("--cms-pw-mr", Math.round(contentRight - pr.right) + "px"); next.style.removeProperty("--cms-pw-ml"); }
    // Square has no curve to hug; anything else wears its ellipse (a circle
    // when round). shape-margin adds the breathing gap around it.
    next.style.setProperty("--cms-pw-shape",
      banner.classList.contains("cms-portrait-shape-square") ? "inset(0)" : "ellipse(50% 50%)");
  }

  function apply() {
    document.querySelectorAll(".cms-banner.cms-has-portrait").forEach(applyOne);
  }

  // Load + every in-place region swap (see site.js's cmsSiteSetup).
  if (window.cmsSiteSetup) { window.cmsSiteSetup(apply); }
  else if (document.readyState !== "loading") { apply(); }
  else { document.addEventListener("DOMContentLoaded", apply); }

  // Geometry depends on width, so recompute on resize -- once bound, debounced.
  var t;
  window.addEventListener("resize", function () {
    clearTimeout(t);
    t = setTimeout(apply, 120);
  });
  // A late-loading web font can reflow the text column; re-measure once.
  window.addEventListener("load", apply);
})();
