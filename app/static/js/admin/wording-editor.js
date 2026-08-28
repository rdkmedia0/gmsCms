// Writing into the message itself.
//
// The Message wording screen was two textareas and a collapsed preview.
// It is the message now, on the site's ground, in the card it arrives in
// -- the owner's greeting and sign-off written into directly, the code's
// own words greyed and inert beside them. Same shape as the newsletter
// editor, because they are the same kind of thing.
//
// Small on purpose. There are no blocks here and nothing to rearrange:
// two editable regions per message, a hidden input each, and the
// placeholder chips. Everything the newsletter editor does beyond that
// would be machinery for a problem this screen does not have.
(function () {
  "use strict";

  //  Which region the caret was last in, per message. A placeholder chip
  //  has to land where somebody was typing, and pressing it takes the
  //  focus away first -- so it is remembered rather than looked up.
  var lastUsed = {};

  document.querySelectorAll(".cms-wording-form").forEach(function (form) {
    var key = form.dataset.message;

    form.querySelectorAll("[data-wording]").forEach(function (region) {
      var store = document.getElementById(region.dataset.store);

      function sync() {
        //  innerText, not innerHTML: what is stored is TEXT. The message
        //  is rendered by the server from these words, and letting
        //  markup in here would put it in somebody's inbox unescaped.
        if (store) store.value = (region.innerText || "").replace(/\u00a0/g, " ").trim();
        region.classList.toggle("cms-wording-blank",
                                !(region.innerText || "").trim());
      }

      //  The greeting is the one people reach for first, so it is where
      //  a chip goes before anything has been focused.
      if (!lastUsed[key] && region.dataset.wording === "intro") {
        lastUsed[key] = region;
      }
      region.addEventListener("focus", function () { lastUsed[key] = region; });
      region.addEventListener("input", sync);
      region.addEventListener("blur", sync);

      //  Paste as words. A greeting copied from somewhere else brings
      //  its fonts and colours, and this text is rendered into an email
      //  where none of that survives anyway.
      region.addEventListener("paste", function (e) {
        e.preventDefault();
        var plain = (e.clipboardData || window.clipboardData).getData("text/plain");
        document.execCommand("insertText", false, plain);
      });

      //  Return would make a second line in something drawn as one, and
      //  the stored form is a single line of text.
      region.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); region.blur(); }
      });

      sync();
    });

    form.addEventListener("submit", function () {
      form.querySelectorAll("[data-wording]").forEach(function (region) {
        var store = document.getElementById(region.dataset.store);
        if (store) {
          store.value = (region.innerText || "").replace(/\u00a0/g, " ").trim();
        }
      });
    });
  });

  document.querySelectorAll("[data-insert]").forEach(function (btn) {
    //  mousedown, not click: pressing a button blurs the region and
    //  takes the caret position with it.
    btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
    btn.addEventListener("click", function () {
      var region = lastUsed[btn.dataset.into];
      if (!region) return;
      region.focus();
      document.execCommand("insertText", false, btn.dataset.insert);
      region.dispatchEvent(new Event("input"));
    });
  });
})();
