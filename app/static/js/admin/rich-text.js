// Turns a <textarea data-richtext> into a small WYSIWYG.
//
// A blog post's content is HTML, and it was being typed AS HTML in a
// plain textarea -- the exact thing this project removed from the page
// editor once already: "never a raw HTML textarea as the way to
// accomplish ordinary styling or layout". Somebody writing a post should
// not have to know what a <p> is.
//
// The textarea stays in the form and keeps its name, so the server, the
// route and everything downstream see exactly what they saw before. It
// is only hidden, and kept in step with what the person is actually
// editing.
//
// The command set is the live editor's core vocabulary (see the
// wysiwyg_toolbar macro in public/page.html) minus the page-layout ones:
// alignment, fonts and colours belong to a section on a page, not to the
// words of a post.
(function () {
  "use strict";

  var COMMANDS = [
    { cmd: "bold", label: "<b>B</b>", title: "Bold" },
    { cmd: "italic", label: "<i>I</i>", title: "Italic" },
    { cmd: "formatBlock", value: "h2", label: "H2", title: "Heading" },
    { cmd: "formatBlock", value: "p", label: "\u00b6", title: "Normal paragraph" },
    { cmd: "insertUnorderedList", label: "\u2022 List", title: "Bullet list" },
    { cmd: "insertOrderedList", label: "1. List", title: "Numbered list" },
    { cmd: "createLink", label: "\uD83D\uDD17", title: "Link" },
    { cmd: "removeFormat", label: "\u2715", title: "Clear formatting" }
  ];

  //  Plain text with blank lines between paragraphs is how older posts
  //  were written, and post_html() still renders them that way. Same
  //  conversion here, so opening an old post shows paragraphs rather
  //  than one run-on block.
  function asHtml(value) {
    var text = (value || "").trim();
    if (!text) return "";
    if (text.indexOf("<") !== -1) return text;
    return text.split(/\n\s*\n/).map(function (para) {
      var safe = para.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return "<p>" + safe.replace(/\n/g, "<br>") + "</p>";
    }).join("");
  }

  document.querySelectorAll("textarea[data-richtext]").forEach(function (textarea) {
    var wrap = document.createElement("div");
    wrap.className = "cms-richtext";

    var bar = document.createElement("div");
    bar.className = "cms-richtext-toolbar";
    COMMANDS.forEach(function (item) {
      var b = document.createElement("button");
      b.type = "button";
      b.innerHTML = item.label;
      b.title = item.title;
      //  mousedown, not click: clicking a button blurs the editable and
      //  the selection goes with it, so the command lands on nothing.
      b.addEventListener("mousedown", function (e) {
        e.preventDefault();
        editable.focus();
        if (item.cmd === "createLink") {
          var url = window.prompt("Link to which web address?", "https://");
          if (url) document.execCommand("createLink", false, url);
        } else {
          document.execCommand(item.cmd, false, item.value || null);
        }
        sync();
      });
      bar.appendChild(b);
    });

    var editable = document.createElement("div");
    editable.className = "cms-richtext-surface";
    editable.contentEditable = "true";
    editable.setAttribute("role", "textbox");
    editable.setAttribute("aria-multiline", "true");
    editable.setAttribute("aria-label", textarea.getAttribute("aria-label") || "Post content");
    editable.title = textarea.title || "Write your post here. Use the buttons above for headings, lists and links.";
    editable.innerHTML = asHtml(textarea.value);

    function sync() { textarea.value = editable.innerHTML; }
    editable.addEventListener("input", sync);
    editable.addEventListener("blur", sync);

    textarea.parentNode.insertBefore(wrap, textarea);
    wrap.appendChild(bar);
    wrap.appendChild(editable);
    textarea.hidden = true;
    //  So the icon inserter can find the surface it should write into
    //  rather than a textarea nobody is looking at.
    textarea.richtextSurface = editable;

    var form = textarea.closest("form");
    if (form) form.addEventListener("submit", sync);
  });
})();
