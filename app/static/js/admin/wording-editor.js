// Writing the messages that send themselves.
//
// One editor, and a dropdown saying which of the four it is writing.
// It was four cards stacked down the page -- the same canvas, the same
// chips and the same buttons four times, differing only in which
// message they wrote. Choosing which one you are editing is a control,
// not a reason to render the screen again.
//
// Every message's canvas is in the page and one is shown, so switching
// is instant and nothing is lost by looking at another one.
(function () {
  "use strict";

  var form = document.querySelector("[data-message-form]");
  if (!form) return;

  var pick = form.querySelector("[data-message-pick]");
  var previewBtn = form.querySelector("[data-preview-toggle]");
  var saveUrl = form.dataset.saveUrl || "";

  var SAMPLE = {};
  try {
    var el = document.getElementById("cms-wording-sample");
    SAMPLE = JSON.parse((el && el.textContent) || "{}");
  } catch (e) {
    SAMPLE = {};
  }

  var current = pick ? pick.value : null;
  var previewing = false;

  function panel(key) { return form.querySelector('[data-message-panel="' + key + '"]'); }
  function region(key) { return panel(key) && panel(key).querySelector("[data-wording]"); }

  //  The same substitution the server does, so what is shown while
  //  typing is what will be sent. It fills what it knows and leaves what
  //  it does not, which is the rule the server follows -- a visible
  //  {{discount}} is a mistake somebody can see and fix, and a gap is
  //  one nobody notices until a customer asks.
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

  function sync(key) {
    var r = region(key);
    if (!r) return;
    var store = document.getElementById(key + "_body");
    //  innerText, not innerHTML: what is stored is TEXT. The message is
    //  rendered by the server from these words, and letting markup in
    //  here would put it in somebody's inbox unescaped.
    var text = (r.innerText || "").replace(/\u00a0/g, " ");
    if (store) store.value = text.trim();
    r.classList.toggle("cms-wording-blank", !text.trim());
    var into = panel(key).querySelector("[data-preview]");
    if (into) paragraphs(into, filled(text));
  }

  function show(key) {
    current = key;
    form.querySelectorAll("[data-message-panel]").forEach(function (p) {
      p.hidden = p.dataset.messagePanel !== key;
    });
    form.querySelectorAll("[data-chips]").forEach(function (c) {
      c.hidden = c.dataset.chips !== key;
    });
    //  The action follows the choice. One form, four possible targets --
    //  which is what stops this being four forms again.
    form.action = saveUrl.replace("MESSAGE", key);
    if (previewing) setPreview(true);
  }

  //  Preview is a VIEW of the same canvas rather than a column beside
  //  it. The side-by-side pane answered a real question -- a sentence
  //  with a placeholder in it cannot be judged until the placeholder
  //  says a real amount -- and it does not have to cost half the width
  //  all the time to answer it.
  function setPreview(on) {
    previewing = on;
    form.querySelectorAll("[data-message-panel]").forEach(function (p) {
      var write = p.querySelector("[data-wording]");
      var read = p.querySelector("[data-preview]");
      if (write) write.hidden = on;
      if (read) read.hidden = !on;
    });
    if (previewBtn) {
      previewBtn.textContent = on ? "Back to writing" : "Preview";
      previewBtn.classList.toggle("btn-primary", on);
      previewBtn.title = on
        ? "Go back to writing this message."
        : "Show this message with everything filled in, as it will arrive.";
    }
    var note = form.querySelector("[data-preview-source]");
    if (note) note.hidden = !on;
  }

  form.querySelectorAll("[data-wording]").forEach(function (r) {
    var key = r.closest("[data-message-panel]").dataset.messagePanel;

    r.addEventListener("input", function () { sync(key); });
    r.addEventListener("blur", function () { sync(key); });

    //  Paste as words. A message copied from somewhere else brings its
    //  fonts and colours, and this text is rendered into an email where
    //  none of that survives anyway.
    r.addEventListener("paste", function (e) {
      e.preventDefault();
      var plain = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, plain);
    });

    //  Return makes a new line. It used to blur, which was right when
    //  this held a one-line greeting and is wrong now that it holds the
    //  whole message: nobody can write a paragraph in a box that closes
    //  when they press Enter.
    r.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        document.execCommand("insertLineBreak");
      }
    });

    sync(key);
  });

  if (pick) {
    pick.addEventListener("change", function () { show(pick.value); });
    show(pick.value);
  }

  if (previewBtn) {
    previewBtn.addEventListener("click", function () { setPreview(!previewing); });
    setPreview(false);
  }

  form.querySelectorAll("[data-insert]").forEach(function (btn) {
    //  mousedown, not click: pressing a button blurs the region and
    //  takes the caret position with it.
    btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
    btn.addEventListener("click", function () {
      var r = region(current);
      if (!r || previewing) return;
      r.focus();
      document.execCommand("insertText", false, btn.dataset.insert);
      sync(current);
    });
  });

  form.addEventListener("submit", function () {
    //  Only the message being edited is saved -- the others are in the
    //  page so switching is instant, and posting all four would mean one
    //  form quietly rewriting three messages nobody opened.
    form.querySelectorAll("[data-body-for]").forEach(function (input) {
      input.disabled = input.dataset.bodyFor !== current;
    });
    sync(current);
    var mine = document.getElementById(current + "_body");
    if (mine) mine.disabled = false;
  });
})();
