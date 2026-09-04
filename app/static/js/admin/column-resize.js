// Drag the centre line of a two-column section to resize it. The handle
// (.cms-col-resizer) is positioned on the boundary between the two
// columns; dragging updates the grid live and, on release, saves the
// ratio (the left column's fraction of the width) to the section. Only
// two-column sections carry a handle -- three or more stay equal.
(function () {
  "use strict";

  function columns(grid) {
    return Array.prototype.filter.call(
      grid.children, function (el) { return el.classList.contains("cms-column"); });
  }

  function setup(grid) {
    var resizer = grid.querySelector(":scope > .cms-col-resizer");
    if (!resizer || grid.__colResizeReady) return;
    grid.__colResizeReady = true;
    var url = grid.dataset.colResizeUrl;

    function place() {
      var cols = columns(grid);
      if (cols.length < 2) return;
      var gr = grid.getBoundingClientRect();
      var first = cols[0].getBoundingClientRect();
      var second = cols[1].getBoundingClientRect();
      // Sit on the MIDLINE of the gap between the two columns, not the
      // edge of the left one -- that read as offset to one side.
      resizer.style.left = ((first.right + second.left) / 2 - gr.left) + "px";
    }
    place();
    window.addEventListener("resize", place);

    var dragging = false;
    var frac = null;

    resizer.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      dragging = true;
      resizer.classList.add("dragging");
      try { resizer.setPointerCapture(e.pointerId); } catch (_) {}
    });

    resizer.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var gr = grid.getBoundingClientRect();
      frac = (e.clientX - gr.left) / gr.width;
      // Keep both columns usable -- never let one collapse.
      frac = Math.max(0.15, Math.min(0.85, frac));
      //  Set the RATIO VARIABLE (not grid-template-columns directly), so
      //  the mobile media query that stacks columns can still win.
      grid.style.setProperty("--cms-cols",
        frac.toFixed(3) + "fr " + (1 - frac).toFixed(3) + "fr");
      // The handle follows the cursor (clamped), so it stays under the
      // finger rather than snapping to the column edge.
      resizer.style.left = (Math.max(0.15, Math.min(0.85, frac)) * gr.width) + "px";
    });

    function end(e) {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove("dragging");
      try { resizer.releasePointerCapture(e.pointerId); } catch (_) {}
      if (frac == null || !url) return;
      var fd = new FormData();
      fd.append("left", frac.toFixed(3));
      if (grid.dataset.next) fd.append("next", grid.dataset.next);
      fetch(url, {
        method: "POST", body: fd,
        headers: { "X-Requested-With": "fetch", "Accept": "application/json" },
      }).then(place).catch(function () {});
    }
    resizer.addEventListener("pointerup", end);
    resizer.addEventListener("pointercancel", end);
  }

  function init() {
    document.querySelectorAll(".cms-columns-resizable").forEach(setup);
  }
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
