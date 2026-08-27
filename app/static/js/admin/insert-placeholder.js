// Putting a placeholder where the cursor was.
//
// A message's placeholders are listed on screen to be clicked rather
// than typed, for one reason: `{{site}}` typed as `{{ site }}` or
// `{{Site}}` does not substitute, and what arrives in somebody's inbox
// is the literal braces. Offering them removes the spelling from the
// problem entirely.
//
// It inserts at the caret in whichever of that message's two boxes was
// last used, because "greeting" and "sign-off" are both plausible homes
// for the same placeholder and guessing would be wrong half the time.
(function () {
  "use strict";

  var lastUsed = {};

  document.querySelectorAll("textarea[id$='_intro'], textarea[id$='_outro']")
    .forEach(function (box) {
      var group = box.id.replace(/_(intro|outro)$/, "");
      //  The greeting is the one people reach for first, so it is where
      //  a click goes before anything has been focused.
      if (!lastUsed[group] && box.id.endsWith("_intro")) lastUsed[group] = box;
      box.addEventListener("focus", function () { lastUsed[group] = box; });
    });

  document.querySelectorAll("[data-insert]").forEach(function (btn) {
    //  mousedown, not click: pressing a button blurs the textarea and
    //  takes the caret position with it.
    btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
    btn.addEventListener("click", function () {
      var box = lastUsed[btn.dataset.into];
      if (!box) return;
      var text = btn.dataset.insert;
      var at = box.selectionStart;
      var to = box.selectionEnd;
      box.value = box.value.slice(0, at) + text + box.value.slice(to);
      //  Caret after what was just inserted, so typing carries on where
      //  somebody would expect rather than at the start of the box.
      box.focus();
      box.selectionStart = box.selectionEnd = at + text.length;
    });
  });
})();
