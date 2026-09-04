// Filter the icon picker as you type. One delegated handler covers every
// picker on the page (the Menu tool, the WYSIWYG Insert Icon button, the
// Contact tool, the blog editor) -- each has its own .cms-icon-grid-view
// with a .cms-icon-search box; typing in one filters the buttons in that
// same view by their name (title) or key.
(function () {
  "use strict";
  document.addEventListener("input", function (e) {
    var box = e.target;
    if (!box.classList || !box.classList.contains("cms-icon-search")) return;
    var view = box.closest(".cms-icon-grid-view");
    if (!view) return;
    var q = box.value.trim().toLowerCase();
    view.querySelectorAll(".cms-icon-grid-btn").forEach(function (btn) {
      //  "No icon" is an action, not an icon -- hide it while searching so
      //  it does not sit oddly among the matches.
      if (btn.classList.contains("cms-icon-grid-none")) { btn.hidden = !!q; return; }
      var label = (btn.getAttribute("title") || "").toLowerCase();
      var key = (btn.getAttribute("data-icon-key") || "").toLowerCase();
      btn.hidden = !!q && label.indexOf(q) === -1 && key.indexOf(q) === -1;
    });
  });
})();
