// A plain <textarea> has no cursor/selection API like contenteditable
// does, so this inserts via selectionStart/End directly instead of the
// execCommand("insertHTML", ...) the live-page WYSIWYG editor uses (see
// inline-editor.js) — different mechanism, same shared icon grid markup.
(function () {
  var btn = document.querySelector(".cms-insert-icon-textarea-btn");
  var grid = document.querySelector(".cms-icon-grid-view");
  if (!btn || !grid) return;
  var textarea = document.getElementById(btn.dataset.target);
  var savedPos = null;

  btn.addEventListener("mousedown", function () {
    savedPos = { start: textarea.selectionStart, end: textarea.selectionEnd };
  });
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    if (!grid.hidden) { grid.hidden = true; return; }
    var rect = btn.getBoundingClientRect();
    grid.style.position = "fixed";
    grid.style.top = (rect.bottom + 2) + "px";
    grid.style.left = rect.left + "px";
    grid.hidden = false;
  });
  grid.querySelectorAll(".cms-icon-grid-btn").forEach(function (iconBtn) {
    iconBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      grid.hidden = true;
      var pos = savedPos || { start: textarea.value.length, end: textarea.value.length };
      var html = iconBtn.innerHTML.trim();
      textarea.setRangeText(html, pos.start, pos.end, "end");
      textarea.focus();
    });
  });
  document.addEventListener("click", function (e) {
    if (!grid.hidden && !e.target.closest(".cms-icon-grid-view, .cms-insert-icon-textarea-btn")) grid.hidden = true;
  });
})();
