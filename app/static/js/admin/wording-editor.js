// Writing the messages that send themselves.
//
// The Message wording screen was two textareas and a collapsed preview.
// It is the message now, on the site's ground, in the card it arrives in
// -- the whole body written into directly, with what the code appends
// greyed and inert below it.
//
// Two jobs, and only two. Keep the hidden field in step with what is
// being typed, and show the same words with their placeholders filled
// in, beside it, as they are typed. Everything the newsletter editor
// does beyond that -- blocks, structure, a server round trip per change
// -- would be machinery for a problem this screen does not have.
(function () {
  "use strict";

  var sampleEl = document.getElementById("cms-wording-sample");
  var SAMPLE = {};
  try {
    SAMPLE = JSON.parse((sampleEl && sampleEl.textContent) || "{}");
  } catch (e) {
    SAMPLE = {};
  }

  //  Which region the caret was last in, per message. A placeholder chip
  //  has to land where somebody was typing, and pressing it takes the
  //  focus away first -- so it is remembered rather than looked up.
  var lastUsed = {};

  //  The same substitution the server does, in the same order, so what
  //  is shown while typing is what will be sent. Kept deliberately
  //  small: it fills what it knows and leaves what it does not, which is
  //  exactly the rule the server follows -- a visible {{discount}} is a
  //  mistake somebody can see and fix, and a gap is one nobody notices.
  function filled(text) {
    var out = text || "";
    Object.keys(SAMPLE).forEach(function (name) {
      var token = "{{" + name + "}}";
      var value = SAMPLE[name] == null ? "" : String(SAMPLE[name]);
      if (out.indexOf(token) < 0) return;
      if (!value.trim()) {
        //  Drop the whole line rather than strand a label. "Buyer: "
        //  with nothing after it reads as a fault in the site.
        out = out.split("\n").filter(function (line) {
          return line.indexOf(token) < 0 || line.trim() !== token;
        }).join("\n");
      }
      out = out.split(token).join(value);
    });
    //  Never two blank lines in a row: dropping a line above would
    //  otherwise leave a hole in the middle of the message.
    var kept = [];
    out.split("\n").forEach(function (line) {
      if (!line.trim() && kept.length && !kept[kept.length - 1].trim()) return;
      kept.push(line);
    });
    return kept.join("\n").trim();
  }

  function paragraphs(into, text) {
    into.textContent = "";
    (text || "").split(/\n{2,}/).forEach(function (para) {
      var p = document.createElement("p");
      //  A single newline is a line break inside one paragraph, which is
      //  what a list of items in an invoice is.
      para.split("\n").forEach(function (line, i) {
        if (i) p.appendChild(document.createElement("br"));
        p.appendChild(document.createTextNode(line));
      });
      into.appendChild(p);
    });
  }

  document.querySelectorAll(".cms-wording-form").forEach(function (form) {
    var key = form.dataset.message;
    var preview = form.querySelector("[data-preview]");

    form.querySelectorAll("[data-wording]").forEach(function (region) {
      var store = document.getElementById(region.dataset.store);

      function sync() {
        //  innerText, not innerHTML: what is stored is TEXT. The message
        //  is rendered by the server from these words, and letting
        //  markup in here would put it in somebody's inbox unescaped.
        var text = (region.innerText || "").replace(/\u00a0/g, " ");
        if (store) store.value = text.trim();
        region.classList.toggle("cms-wording-blank", !text.trim());
        if (preview) paragraphs(preview, filled(text));
      }

      if (!lastUsed[key]) lastUsed[key] = region;
      region.addEventListener("focus", function () { lastUsed[key] = region; });
      region.addEventListener("input", sync);
      region.addEventListener("blur", sync);

      //  Paste as words. A message copied from somewhere else brings its
      //  fonts and colours, and this text is rendered into an email
      //  where none of that survives anyway.
      region.addEventListener("paste", function (e) {
        e.preventDefault();
        var plain = (e.clipboardData || window.clipboardData).getData("text/plain");
        document.execCommand("insertText", false, plain);
      });

      //  Return makes a new line. It used to blur, which was right when
      //  this held a one-line greeting and is wrong now that it holds
      //  the whole message: an owner cannot write a paragraph in a box
      //  that closes when they press Enter.
      region.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          document.execCommand("insertLineBreak");
        }
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
