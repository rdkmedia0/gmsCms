// Copy what a button says to copy.
//
// Any `[data-copy]` puts its value on the clipboard and says so. Written
// once because more than one screen wants it -- the WhatsApp link on the
// Legal screen today, and anything else that offers a value to paste
// somewhere else in the app.
//
// The fallback matters more than it looks: navigator.clipboard needs a
// secure context, and this app is explicitly supported running on plain
// http behind somebody's own proxy (see the README). Without it, Copy
// would do nothing at all on exactly those installs, silently.
(function () {
  "use strict";

  function tell(btn, words) {
    var was = btn.textContent;
    btn.textContent = words;
    window.setTimeout(function () { btn.textContent = was; }, 1400);
  }

  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var text = btn.dataset.copy || "";
      try {
        await navigator.clipboard.writeText(text);
        tell(btn, "Copied");
        return;
      } catch (e) {
        //  No clipboard API, or not a secure context.
      }
      var box = document.createElement("textarea");
      box.value = text;
      box.setAttribute("readonly", "");
      box.style.cssText = "position:absolute;left:-9999px;top:0;";
      document.body.appendChild(box);
      box.select();
      var done = false;
      try { done = document.execCommand("copy"); } catch (e) { done = false; }
      document.body.removeChild(box);
      //  If even that failed, say so rather than looking like it worked.
      tell(btn, done ? "Copied" : "Press Ctrl+C");
      if (!done) {
        box = document.querySelector("code");
        if (window.getSelection && btn.previousElementSibling) {
          var range = document.createRange();
          range.selectNodeContents(btn.previousElementSibling);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        }
      }
    });
  });
})();
