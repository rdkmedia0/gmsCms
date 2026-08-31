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

  var NEWLINE = String.fromCharCode(10);
  var current = pick ? pick.value : null;
  var previewing = false;

  function panel(key) { return form.querySelector('[data-message-panel="' + key + '"]'); }
  function region(key) { return panel(key) && panel(key).querySelector("[data-wording]"); }

  //  The preview is the SAME canvas with the placeholders filled in --
  //  a clone of it, walked for text. Not a second renderer: the words
  //  have already been turned into headings and paragraphs by the
  //  server, and re-doing that in JavaScript is how a preview comes to
  //  disagree with what is sent. The only difference between the two
  //  views is what `{{total}}` says.
  function drawPreview(key) {
    var from = region(key);
    var into = panel(key) && panel(key).querySelector("[data-preview]");
    if (!from || !into) return;
    var copy = from.cloneNode(true);
    copy.removeAttribute("contenteditable");

    var walker = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT, null);
    var found = [];
    var node;
    while ((node = walker.nextNode())) found.push(node);
    found.forEach(function (text) {
      var filled = substitute(text.nodeValue || "");
      if (filled === text.nodeValue) return;
      //  A value can be several lines -- an order's items are one per
      //  line -- and they have to stay several. Dropped into one text
      //  node they become "1 x Coaching pack 24.00 CHF 2 x Session notes
      //  18.00 CHF", which is not what arrives and is not a price list.
      //  NEWLINE is built rather than typed: an escape inside a
      //  string in this file has been eaten once already, and what
      //  came out was a real line break in the middle of a literal.
      if (filled.indexOf(NEWLINE) < 0) {
        text.nodeValue = filled;
        return;
      }
      var made = document.createDocumentFragment();
      filled.split(NEWLINE).forEach(function (line, i) {
        if (i) made.appendChild(document.createElement("br"));
        made.appendChild(document.createTextNode(line));
      });
      text.parentNode.replaceChild(made, text);
    });
    //  A value that is itself empty takes its whole block with it, the
    //  same rule `site_emails.fill` follows: a message must never end in
    //  "Buyer:" with nothing after it.
    Array.prototype.slice.call(copy.children).forEach(function (block) {
      if (!(block.textContent || "").trim()) block.parentNode.removeChild(block);
    });

    into.textContent = "";
    while (copy.firstChild) into.appendChild(copy.firstChild);
  }

  //  What it fills, it fills; what it does not know it leaves visible --
  //  the rule the server follows too. A `{{discount}}` still on screen
  //  is a mistake somebody can see and fix, and a gap is one nobody
  //  notices until a customer asks.
  function substitute(text) {
    var out = text;
    Object.keys(SAMPLE).forEach(function (name) {
      var token = "{{" + name + "}}";
      if (out.indexOf(token) < 0) return;
      var value = SAMPLE[name] == null ? "" : String(SAMPLE[name]);
      out = out.split(token).join(value);
    });
    return out;
  }


  function sync(key) {
    var r = region(key);
    if (!r) return;
    var store = document.getElementById(key + "_body");
    //  The canvas holds the message RENDERED -- headings, bold, lists --
    //  and what is stored is the vocabulary it was written in. Read back
    //  by the shared serialiser, which is the exact inverse of the
    //  `rich()` that rendered it. It was `innerText`, which was right
    //  while the canvas was raw text and silently threw away every
    //  heading and every bold word the moment it was not.
    var text = window.cmsRichText
      ? window.cmsRichText.fromHtml(r)
      : (r.innerText || "");
    if (store) store.value = text.trim();
    r.classList.toggle("cms-wording-blank", !text.trim());
    if (previewing) drawPreview(key);
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
    //  ...and so does the "open it as it arrives" link, or it would show
    //  whichever message happened to be first.
    var live = document.querySelector("[data-live-preview]");
    if (live) {
      live.href = live.href.replace(/\/emails\/[^/]+\/preview/,
                                    "/emails/" + key + "/preview");
    }
    if (previewing) setPreview(true);
  }

  //  Preview is a VIEW of the same canvas rather than a column beside
  //  it. The side-by-side pane answered a real question -- a sentence
  //  with a placeholder in it cannot be judged until the placeholder
  //  says a real amount -- and it does not have to cost half the width
  //  all the time to answer it.
  function setPreview(on) {
    previewing = on;
    //  Built at the moment it is shown, from what is on the canvas --
    //  not kept in step behind the scenes while somebody types. The
    //  server rendered one at page load; every one after that is this.
    if (on && current) drawPreview(current);
    form.querySelectorAll("[data-message-panel]").forEach(function (p) {
      var write = p.querySelector("[data-wording]");
      var read = p.querySelector("[data-preview]");
      if (write) write.hidden = on;
      if (read) read.hidden = !on;
    });
    if (previewBtn) {
      //  A glyph, and the same glyph vocabulary the rest of the admin
      //  uses: an eye SHOWS, a pencil WRITES. It was set to the words
      //  "Preview" / "Back to writing" here, which overwrote the icon
      //  the markup renders -- so a toolbar of icons had one text button
      //  in the middle of it, from JavaScript, invisibly.
      previewBtn.innerHTML = on ? "&#9998;" : "&#128065;";
      previewBtn.classList.toggle("is-on", on);
      previewBtn.title = on
        ? "Back to writing this message."
        : "Show this message with everything filled in, as it will arrive.";
    }
    //  One note per message, beside that message's own preview. It used
    //  to be a single one in the ribbon, which is what made the toolbar
    //  reflow when it appeared.
    form.querySelectorAll("[data-preview-source]").forEach(function (note) {
      note.hidden = !on;
    });
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
