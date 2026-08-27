// Seeing a page at another screen size, honestly.
//
// The obvious implementation -- squeeze the page into a narrow column --
// is a lie: a media query answers the VIEWPORT, not the width of some box
// on it, so a page pushed into 390px on a wide screen still lays itself
// out as a wide one. This loads the page as a VISITOR sees it (?preview=1
// renders one request without editing chrome, and without touching the
// session) inside a frame of the chosen width, where the queries fire
// exactly as they will on somebody's phone.
(function () {
  "use strict";
  var select = document.querySelector(".cms-preview-width");
  var frame = document.getElementById("cms-preview-frame");
  if (!select || !frame) return;
  var viewport = frame.querySelector(".cms-preview-viewport");
  var label = frame.querySelector(".cms-preview-size");
  var close = document.getElementById("cms-preview-close");

  function show(width) {
    var url = window.location.pathname
      + (window.location.search ? window.location.search + "&" : "?") + "preview=1";
    viewport.src = url;
    viewport.style.width = width + "px";
    label.textContent = width + "px wide — the page as a visitor sees it";
    frame.hidden = false;
    document.body.classList.add("cms-preview-open");
  }

  function hide() {
    frame.hidden = true;
    viewport.src = "about:blank";
    select.value = "";
    document.body.classList.remove("cms-preview-open");
  }

  select.addEventListener("change", function () {
    if (select.value) show(parseInt(select.value, 10));
  });
  close.addEventListener("click", hide);
  //  Escape closes it, the way every other overlay in this editor does.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !frame.hidden) hide();
  });
})();
