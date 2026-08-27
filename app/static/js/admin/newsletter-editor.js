// Writing a newsletter by writing the newsletter.
//
// The email is rendered with its slots opened up (email_layouts.render
// with edit=True) and this keeps a hidden input in step with each one, so
// the route that saves it never has to know any of this happened: it
// still reads `heading`, `body`, `button_url` and the rest, exactly as it
// did when they were text boxes.
//
// The serialiser here is the exact inverse of email_layouts.paragraphs():
// that turns blank-line-separated text into <p> blocks, this turns <p>
// blocks back into blank-line-separated text. If one changes the other
// has to, or a newsletter will not read back the way it was written.
(function () {
  "use strict";

  var form = document.querySelector(".cms-issue-form");
  if (!form) return;
  var asides = form.querySelector(".cms-issue-asides");

  function store(name) {
    return form.querySelector('[data-slot-store="' + name + '"]');
  }

  //  <p>one</p><p>two</p>  ->  "one" + blank line + "two"
  function textFromBlocks(el) {
    var paras = el.querySelectorAll("p");
    var out = [];
    if (!paras.length) {
      var lone = (el.innerText || "").trim();
      return lone;
    }
    Array.prototype.forEach.call(paras, function (p) {
      var t = (p.innerText || "").replace(/\u00a0/g, " ").trim();
      if (t) out.push(t);
    });
    return out.join("\n\n");
  }

  function sync(el) {
    var name = el.dataset.slot;
    var box = store(name);
    if (!box) return;
    if (el.tagName === "INPUT") {
      box.value = el.value;
    } else if (el.dataset.multiline) {
      box.value = textFromBlocks(el);
    } else {
      box.value = (el.innerText || "").replace(/\u00a0/g, " ").trim();
    }
  }

  //  An empty editable shows what belongs in it. A CSS :empty rule cannot
  //  be trusted here because a browser leaves a stray <br> behind.
  function placeholders(el) {
    var empty = !(el.innerText || "").trim();
    el.classList.toggle("cms-slot-blank", empty);
  }

  form.querySelectorAll("[data-slot]").forEach(function (el) {
    sync(el);
    placeholders(el);
    var ev = el.tagName === "INPUT" ? "input" : "input";
    el.addEventListener(ev, function () { sync(el); placeholders(el); });
    el.addEventListener("blur", function () { sync(el); placeholders(el); });
    //  Return inside a single-line slot would make a second line in
    //  something that is drawn as one.
    if (el.tagName !== "INPUT" && !el.dataset.multiline) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); el.blur(); }
      });
    }
  });

  //  The things an email cannot hold -- where a button points, where a
  //  picture lives -- are moved out of the canvas and under it, so the
  //  canvas stays the email and nothing floats on top of it.
  if (asides) {
    form.querySelectorAll(".cms-slot-aside").forEach(function (aside) {
      asides.appendChild(aside);
    });
    if (!asides.children.length) asides.hidden = true;
  }

  //  An empty picture frame opens the field that fills it.
  form.querySelectorAll("[data-slot-image]").forEach(function (frame) {
    frame.addEventListener("click", function () {
      var field = form.querySelector('input[data-slot="' + frame.dataset.slotImage + '"]');
      if (field) { field.scrollIntoView({ block: "center" }); field.focus(); }
    });
  });

  //  Paste as words, not as somebody else's markup: a paragraph copied
  //  from a web page brings its fonts and colours with it, and an email
  //  that half matches the site looks like a mistake.
  form.querySelectorAll('[contenteditable="true"]').forEach(function (el) {
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text);
    });
  });

  form.addEventListener("submit", function () {
    form.querySelectorAll("[data-slot]").forEach(sync);
  });
})();
