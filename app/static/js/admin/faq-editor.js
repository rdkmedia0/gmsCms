(function () {
  "use strict";
  // The FAQ's editor.
  //
  // What is STORED is unchanged: a Q./A. document, exactly as before. This
  // only changes how it is written — a page you format with buttons rather
  // than by typing ** around things — and what happens when a FAQ is
  // pasted in from a document, where the formatting should survive instead
  // of arriving as a wall of plain text or a mess of Word markup.
  //
  // So there are two conversions here and they are inverses:
  //   read  — the document is rendered into the editable area (server side)
  //   write — the editable area is serialised back to a document (below)
  // Keeping the document as the stored form is what lets the plain-text
  // box, the checker, the mirroring and the views all carry on working
  // without knowing this editor exists.

  var ALLOWED = {
    H1: "h", H2: "h", H3: "h", H4: "h", H5: "h", H6: "h",
    P: "p", DIV: "p", UL: "list", OL: "list", LI: "li",
    STRONG: "b", B: "b", EM: "i", I: "i", A: "a", BR: "br",
  };

  function inlineText(node) {
    // A run of text with its emphasis written back into the document's own
    // small vocabulary. Anything not in that vocabulary contributes its
    // words and nothing else, which is what keeps a paste from a word
    // processor from dragging its markup in behind it.
    var out = "";
    node.childNodes.forEach(function (child) {
      if (child.nodeType === 3) {
        out += child.nodeValue.replace(/\s+/g, " ");
        return;
      }
      if (child.nodeType !== 1) return;
      var kind = ALLOWED[child.tagName];
      var inner = inlineText(child);
      if (kind === "b") out += inner.trim() ? "**" + inner.trim() + "**" : "";
      else if (kind === "i") out += inner.trim() ? "*" + inner.trim() + "*" : "";
      else if (kind === "a") {
        var href = (child.getAttribute("href") || "").trim();
        out += href ? "[" + inner.trim() + "](" + href + ")" : inner;
      } else if (kind === "br") out += "\n";
      else out += inner;
    });
    return out;
  }

  function serialise(root) {
    var lines = [];
    var seenQuestion = false;

    // No "A." — the answer is simply what follows the question, and
    // saying so twice is noise once Q. has marked where each one starts.
    // A. is still READ, for FAQs pasted in from documents that use it.
    function pushBlock(text) {
      var trimmed = text.trim();
      if (!trimmed) return;
      lines.push(trimmed, "");
    }

    Array.prototype.forEach.call(root.children, function (el) {
      var kind = ALLOWED[el.tagName] || "p";
      if (kind === "h") {
        var q = inlineText(el).trim();
        if (!q) return;
        lines.push("Q. " + q, "");
        seenQuestion = true;
      } else if (kind === "list") {
        Array.prototype.forEach.call(el.children, function (li) {
          var item = inlineText(li).trim();
          if (item) lines.push("- " + item);
        });
        lines.push("");
      } else {
        pushBlock(inlineText(el));
      }
    });
    return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function clean(html) {
    // Paste, reduced to what this tool can show. Everything else keeps its
    // words and loses its markup — a heading stays a heading, bold stays
    // bold, and a table's forty spans do not come along.
    var holder = document.createElement("div");
    holder.innerHTML = html;
    holder.querySelectorAll("script, style, meta, link, table, img").forEach(function (el) {
      el.remove();
    });
    var out = document.createElement("div");
    Array.prototype.forEach.call(holder.querySelectorAll("h1,h2,h3,h4,h5,h6,p,ul,ol,li,div"), function (el) {
      if (el.closest("li") && el.tagName !== "LI") return;   // already carried by its item
      if (el.tagName === "LI") return;                        // handled with its list
      var kind = ALLOWED[el.tagName] || "p";
      if (kind === "list") {
        var list = document.createElement("ul");
        Array.prototype.forEach.call(el.children, function (li) {
          var item = document.createElement("li");
          item.textContent = inlineText(li).trim();
          if (item.textContent) list.appendChild(item);
        });
        if (list.children.length) out.appendChild(list);
        return;
      }
      var text = inlineText(el).trim();
      if (!text) return;
      var block = document.createElement(kind === "h" ? "h3" : "p");
      block.textContent = text;
      out.appendChild(block);
    });
    if (!out.children.length) {
      var fallback = document.createElement("p");
      fallback.textContent = holder.textContent.trim();
      out.appendChild(fallback);
    }
    return out.innerHTML;
  }

  //  Run again when the page's markup is replaced without a load (see
  //  admin/live-refresh.js). An editor that survived keeps the one wiring
  //  it already has; only the ones that have just arrived are set up.
  var wired = new WeakSet();
  document.addEventListener("cms:site-refreshed", wireEditors);
  wireEditors();

  function wireEditors() {
  document.querySelectorAll("[data-faq-editor]").forEach(function (editor) {
    if (wired.has(editor)) return;
    wired.add(editor);
    var form = editor.closest("form");
    var field = form && form.querySelector('input[name="faq_md"], textarea[name="faq_md"]');
    if (!field) return;

    // Pasting from a document is the case this exists for: the formatting
    // is kept, and everything the tool cannot show is dropped rather than
    // smuggled in as markup nobody can see or edit.
    editor.addEventListener("paste", function (e) {
      var data = e.clipboardData;
      if (!data) return;
      var html = data.getData("text/html");
      e.preventDefault();
      if (html) {
        document.execCommand("insertHTML", false, clean(html));
      } else {
        // Plain text: blank-line-separated blocks become paragraphs, so a
        // pasted FAQ keeps its shape instead of collapsing into one line.
        var text = data.getData("text/plain") || "";
        var blocks = text.split(/\n\s*\n/).map(function (b) {
          var p = document.createElement("p");
          p.textContent = b.trim();
          return p.outerHTML;
        });
        document.execCommand("insertHTML", false, blocks.join(""));
      }
    });

    // Marking a line as a question is the one structural act here, so it
    // gets a button rather than asking anyone to remember that "Q." at the
    // start of a line is what makes one.
    var mark = form.querySelector("[data-faq-mark-question]");
    if (mark) {
      mark.addEventListener("click", function () {
        editor.focus();
        var block = document.queryCommandValue("formatBlock").toLowerCase();
        document.execCommand("formatBlock", false, block === "h3" ? "p" : "h3");
      });
    }

    // Formatting buttons. Bound here rather than by the page's own
    // toolbar handler, because this bar is not one of those toolbars — it
    // belongs to this editor and should not act on whatever else happens
    // to have focus.
    form.querySelectorAll(".cms-faq-editor-bar button[data-cmd]").forEach(function (btn) {
      btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
      btn.addEventListener("click", function () {
        editor.focus();
        var cmd = btn.dataset.cmd;
        if (cmd === "createLink") {
          var href = window.prompt("Link to (a page like /contact, or a full web address)");
          if (!href) return;
          document.execCommand("createLink", false, href.trim());
          return;
        }
        document.execCommand(cmd, false, null);
      });
    });

    // The document is written into the field the form actually posts, at
    // the moment it posts — so the editor never has to be kept in step
    // with it while somebody is typing.
    form.addEventListener("submit", function () {
      field.value = serialise(editor);
    });
  });
  }
})();
