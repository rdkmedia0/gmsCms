// Turns a <textarea data-richtext> into the same rich-text editor the
// live page uses.
//
// A blog post's content is HTML, and it was being typed AS HTML in a
// plain textarea -- the thing this project removed from the page editor
// once already: "never a raw HTML textarea as the way to accomplish
// ordinary styling or layout".
//
// The first version of this grew its own small toolbar, which was a
// second implementation of something already built. It now renders the
// shared toolbar markup (partials/wysiwyg_toolbar.html) and binds the
// shared behaviour (js/wysiwyg-commands.js), so the blog editor has the
// live tool's features and a button added in one place appears in both.
//
// The textarea stays in the form, keeps its name and stays what the
// server reads -- hidden, and kept in step -- so the route, the model and
// blog.post_html() see exactly what they always saw.
(function () {
  "use strict";

  //  Plain text with blank lines between paragraphs is how older posts
  //  were written, and post_html() still renders them that way. Same
  //  conversion here, so an old post opens as paragraphs rather than one
  //  run-on block.
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
    //  The toolbar for this field is rendered by the template, right
    //  before the textarea, so the markup stays in the template layer.
    var wrap = document.querySelector('.cms-richtext[data-for="' + textarea.id + '"]');
    if (!wrap) return;
    var bar = wrap.querySelector(".cms-wysiwyg-toolbar");

    var editable = document.createElement("div");
    //  cms-wysiwyg-body is what the shared toolbar looks for, and what
    //  the site's own body styles key off, so the words look here much
    //  as they will once published.
    editable.className = "cms-wysiwyg-body cms-richtext-surface";
    editable.contentEditable = "true";
    editable.setAttribute("role", "textbox");
    editable.setAttribute("aria-multiline", "true");
    editable.setAttribute("aria-label", "Post content");
    editable.title = textarea.title || "Write your post here. Use the buttons above for headings, lists and links.";
    editable.innerHTML = asHtml(textarea.value);
    wrap.appendChild(editable);

    function sync() { textarea.value = editable.innerHTML; }
    editable.addEventListener("input", sync);
    editable.addEventListener("blur", sync);

    textarea.hidden = true;
    //  So the icon inserter writes into the surface somebody is looking
    //  at rather than a hidden textarea's caret.
    textarea.richtextSurface = editable;

    //  The post's own picture, if this field has a slot for one. The
    //  toolbar's Image button then sets THAT rather than dropping a
    //  picture into the middle of the words -- one place to add a
    //  picture, and it appears where it will appear in the post.
    var slot = wrap.querySelector("[data-featured-slot]");
    var slotStore = wrap.querySelector("[data-featured-store]");

    function showFeatured(url) {
      if (!slot || !slotStore) return;
      slotStore.value = url || "";
      slot.querySelector("img").src = url || "";
      slot.hidden = !url;
    }

    if (slot) {
      var remove = slot.querySelector(".cms-featured-remove");
      if (remove) remove.addEventListener("click", function () { showFeatured(""); });
    }

    if (bar && window.cmsWysiwyg) {
      window.cmsWysiwyg.bindToolbar(bar, {
        findBody: function () { return editable; },
        afterCommand: function () { sync(); },
        onImage: slot ? showFeatured : null,
      });
    }

    var form = textarea.closest("form");
    if (form) form.addEventListener("submit", sync);
  });
})();
