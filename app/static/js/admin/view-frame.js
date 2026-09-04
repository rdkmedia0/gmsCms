// The page at another screen size, honestly.
//
// Narrowing a box lies -- a media query answers the VIEWPORT, not a box
// on it -- so while VIEWING a non-desktop size, the page is shown inside
// an iframe of that exact width (?preview=1 renders one request as a
// visitor sees it, without touching the session), where the queries fire
// as they will on the real device. While EDITING the canvas is narrowed
// in place instead (you cannot edit inside a frame); that path is
// container-query faithful and mirrors the one stacking media query.
//
// The chosen view lives in the session (data-preview-view on the body),
// so it is one selector for both jobs -- and switching Editing->Viewing
// shows the very size you were editing.
(function () {
  "use strict";
  //  Mirror the viewport widths in page.html and the cms-view-* canvas
  //  widths in site-base.css -- keep the three in step.
  var WIDTHS = { laptop: 1024, tablet: 768, mobile: 390 };
  var LABELS = { laptop: "Laptop", tablet: "Tablet", mobile: "Mobile" };
  var body = document.body;
  var frame = document.getElementById("cms-preview-frame");
  if (!frame) return;
  var viewport = frame.querySelector(".cms-preview-viewport");
  var label = frame.querySelector(".cms-preview-size");
  var close = document.getElementById("cms-preview-close");
  var view = body.getAttribute("data-preview-view") || "desktop";
  var editing = body.classList.contains("cms-editing");
  var resetUrl = body.getAttribute("data-view-reset-url") || "";

  //  Leave the admin bar uncovered so the View selector stays reachable
  //  with the frame open -- its height is dynamic (it wraps on a phone),
  //  so measure it rather than hard-code it.
  function seatBelowBar() {
    var bar = document.querySelector(".cms-admin-bar");
    frame.style.top = (bar ? Math.round(bar.getBoundingClientRect().height) : 0) + "px";
  }

  function show(name, width, code) {
    //  Pass the view code so the framed page FORCES that viewport width
    //  (public.py). Without it a phone reports its own width inside the
    //  iframe and every size collapses to mobile -- the bug this fixes.
    var url = window.location.pathname
      + (window.location.search ? window.location.search + "&" : "?")
      + "preview=1&view=" + encodeURIComponent(code || "");
    viewport.src = url;
    viewport.style.width = width + "px";
    label.textContent = name + " — " + width + "px wide, the page as a visitor sees it";
    seatBelowBar();
    frame.hidden = false;
    body.classList.add("cms-preview-open");
  }

  //  Only while VIEWING, and only for a non-desktop size.
  if (!editing && WIDTHS[view]) {
    show(LABELS[view], WIDTHS[view], view);
    window.addEventListener("resize", seatBelowBar);
  }

  function exit() {
    if (resetUrl) { window.location = resetUrl; return; }
    frame.hidden = true;
    viewport.src = "about:blank";
    body.classList.remove("cms-preview-open");
  }
  if (close) close.addEventListener("click", exit);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !frame.hidden) exit();
  });
})();
