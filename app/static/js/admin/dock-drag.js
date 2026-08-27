/*  Slide the stack of dock tabs along the edge it lives on.
 *
 *  The five tabs sit at fixed offsets down the right-hand edge (or across
 *  the bottom, when the dock is docked there), which puts them wherever
 *  the CSS happened to say -- squarely over the thing being edited often
 *  enough to be a nuisance, and with nothing an admin could do about it.
 *
 *  So the whole strip moves as one, along its own line and no further:
 *  up and down on the side, left and right along the bottom. Together,
 *  because they are one control with five faces -- moving them
 *  individually would let an admin scatter them and then have to hunt for
 *  the one they wanted.
 *
 *  The offset is remembered per orientation, since a distance down the
 *  right edge means nothing when the strip is lying across the bottom.
 */
(function () {
  var KEY_SIDE = "cmsDockTabSlideSide";
  var KEY_BOTTOM = "cmsDockTabSlideBottom";
  var MARGIN = 8;      //  never let the strip touch the corner
  var THRESHOLD = 4;   //  below this a pointer movement is still a click

  document.addEventListener("DOMContentLoaded", function () {
    var tabs = Array.prototype.slice.call(
      document.querySelectorAll(".cms-dock-tab-btn"));
    if (!tabs.length) return;

    var root = document.documentElement;
    var dragged = false;   //  suppress the click that ends a drag

    function bottom() { return tabs[0].classList.contains("cms-dock-bottom"); }
    function key() { return bottom() ? KEY_BOTTOM : KEY_SIDE; }

    function stored() {
      var v = parseFloat(localStorage.getItem(key()));
      return isFinite(v) ? v : 0;
    }

    /*  How far the strip may travel before its leading or trailing tab
     *  would leave the screen. Measured from where the tabs actually are
     *  rather than from the numbers in the stylesheet, so it stays right
     *  when a tab is added, removed or restyled.
     */
    function limits(slide) {
      var lo = Infinity, hi = -Infinity;
      tabs.forEach(function (t) {
        var r = t.getBoundingClientRect();
        if (!r.width && !r.height) return;      //  a hidden tab has no say
        lo = Math.min(lo, bottom() ? r.left : r.top);
        hi = Math.max(hi, bottom() ? r.right : r.bottom);
      });
      if (!isFinite(lo)) return { min: 0, max: 0 };
      //  Un-slide the measurement: rects already include the offset.
      lo -= slide; hi -= slide;
      var edge = bottom() ? window.innerWidth : window.innerHeight;
      return { min: MARGIN - lo, max: edge - MARGIN - hi };
    }

    function apply(slide) {
      var l = limits(0);
      slide = Math.max(l.min, Math.min(l.max, slide));
      //  One variable; which axis it moves along is the stylesheet's
      //  business, because that is what knows which edge we are on.
      root.style.setProperty("--cms-dock-tab-slide", slide + "px");
      return slide;
    }

    function restore() { apply(stored()); }
    restore();
    window.addEventListener("resize", restore);

    //  The orientation toggle rewrites the tabs' classes; the saved
    //  offset for the edge they have just moved to has to come with them.
    var watch = new MutationObserver(restore);
    tabs.forEach(function (t) {
      watch.observe(t, { attributes: true, attributeFilter: ["class"] });
    });

    //  A control nobody knows is draggable is a control nobody drags.
    //  Said in the tooltip each tab already has, rather than in five
    //  templates, so adding a sixth panel gets it for free.
    tabs.forEach(function (t) {
      if (t.title.indexOf("Drag") === -1) {
        t.title = t.title + " — drag to slide these along the edge";
      }
    });

    tabs.forEach(function (tab) {
      tab.addEventListener("pointerdown", function (e) {
        if (e.button !== undefined && e.button !== 0) return;
        var startAt = bottom() ? e.clientX : e.clientY;
        var startSlide = stored();
        var moving = false;

        function onMove(ev) {
          var delta = (bottom() ? ev.clientX : ev.clientY) - startAt;
          if (!moving && Math.abs(delta) < THRESHOLD) return;
          if (!moving) {
            moving = true;
            //  Only capture once it IS a drag, so a plain click still
            //  reaches the tab and opens its panel.
            try { tab.setPointerCapture(e.pointerId); } catch (err) { /* older */ }
            root.classList.add("cms-dock-tab-dragging");
          }
          ev.preventDefault();
          apply(startSlide + delta);
        }

        function onUp(ev) {
          document.removeEventListener("pointermove", onMove);
          document.removeEventListener("pointerup", onUp);
          document.removeEventListener("pointercancel", onUp);
          root.classList.remove("cms-dock-tab-dragging");
          if (!moving) return;
          dragged = true;
          var delta = (bottom() ? ev.clientX : ev.clientY) - startAt;
          localStorage.setItem(key(), String(apply(startSlide + delta)));
        }

        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp);
        document.addEventListener("pointercancel", onUp);
      });
    });

    //  A drag that finishes over a tab would otherwise also open it.
    //  Capture phase, because the tab's own click handler is on the tab.
    document.addEventListener("click", function (e) {
      if (!dragged) return;
      dragged = false;
      if (!e.target.closest(".cms-dock-tab-btn")) return;
      e.preventDefault();
      e.stopPropagation();
    }, true);
  });
})();
