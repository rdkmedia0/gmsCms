// Writing a newsletter by writing the newsletter.
//
// The email is rendered with its slots opened up (email_layouts.render
// with edit=True) and this keeps a hidden input in step with each one, so
// the route that saves it never has to know any of this happened: it
// still reads `heading`, `body`, `button_url` and the rest, exactly as it
// did when they were text boxes.
//
// The serialiser here is the exact inverse of email_layouts.rich(): that
// turns a written vocabulary into inline-styled email blocks, this reads
// those blocks back as the same vocabulary. If one changes the other has
// to, or a newsletter will not read back the way it was written.
//
//     ## a heading        ### a smaller heading
//     **bold**            *italic*
//     [words](address)    - a bullet
//
// The toolbar is the shared one (wysiwyg-commands.js), so the buttons
// behave the way they do on a page and in a blog post. Two things make
// this the LIVE preview it is supposed to be rather than a box that
// happens to be styled: every block the toolbar creates is immediately
// given the style the SENT email writes onto that kind of block -- from
// the same dictionary the server used, handed over as JSON -- and
// anything the vocabulary cannot write down is normalised away as soon
// as it appears, so what is on screen is always something that can
// actually be sent.
(function () {
  "use strict";

  var form = document.querySelector(".cms-issue-form");
  if (!form) return;
  var asides = form.querySelector(".cms-issue-asides");

  function store(name) {
    return form.querySelector('[data-slot-store="' + name + '"]');
  }

  //  The styles the sent email writes onto each kind of block. Read from
  //  the page rather than repeated here, so the editor cannot drift from
  //  what is actually sent.
  var STYLES = (function () {
    var box = document.getElementById("cms-email-block-styles");
    try { return box ? JSON.parse(box.textContent) : {}; } catch (e) { return {}; }
  })();

  //  ---- reading the blocks back as the written vocabulary ----

  function inline(node) {
    if (node.nodeType === 3) {
      return (node.nodeValue || "").replace(/\u00a0/g, " ");
    }
    if (node.nodeType !== 1) return "";
    var inner = "";
    Array.prototype.forEach.call(node.childNodes, function (kid) {
      inner += inline(kid);
    });
    var tag = node.tagName.toLowerCase();
    if (tag === "br") return "\n";
    //  execCommand writes bold and italic as a STYLED SPAN, because
    //  styleWithCSS is on for the sake of the colour and font controls
    //  the other callers of this toolbar have. Both forms have to read
    //  the same, or what is stored depends on whether the DOM has been
    //  tidied yet -- and tidying cannot happen while somebody is typing
    //  into it (see normalise).
    //  Only a SPAN, never a block: a heading carries font-weight:700 as
    //  part of the email's own style, and reading that as emphasis wraps
    //  every heading in ** -- which is what it did.
    var styled = tag === "span" || tag === "font";
    var weight = styled && node.style ? node.style.fontWeight : "";
    var bold = tag === "strong" || tag === "b"
      || weight === "bold" || parseInt(weight, 10) >= 600;
    var italic = tag === "em" || tag === "i"
      || (styled && node.style && node.style.fontStyle === "italic");
    if (bold || italic) {
      if (!inner.trim()) return inner;
      if (bold) inner = "**" + inner + "**";
      if (italic) inner = "*" + inner + "*";
      return inner;
    }
    if (tag === "a") {
      var href = node.getAttribute("href") || "";
      return href ? "[" + inner + "](" + href + ")" : inner;
    }
    return inner;
  }

  function textFromBlocks(el) {
    //  One entry per BLOCK, joined by a blank line -- because a blank
    //  line is what rich() reads as the end of a block. Inside a
    //  paragraph, a <br> stays a single newline, which is what rich()
    //  reads back as a break rather than a new paragraph.
    var out = [];
    Array.prototype.forEach.call(el.children, function (block) {
      var tag = block.tagName.toLowerCase();
      if (tag === "ul" || tag === "ol") {
        var items = [];
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          var t = inline(li).replace(/\n+/g, " ").trim();
          if (t) items.push("- " + t);
        });
        if (items.length) out.push(items.join("\n"));
        return;
      }
      var mark = (tag === "h2" || tag === "h1") ? "## "
        : ((tag === "h3" || tag === "h4") ? "### " : "");
      var text = inline(block).split("\n").map(function (line) {
        return line.trim();
      }).filter(Boolean).join("\n");
      if (!text) return;
      if (mark) {
        //  A heading is one line by definition; a break pasted into one
        //  would otherwise become a second, unmarked heading.
        out.push(mark + text.replace(/\n+/g, " "));
      } else {
        out.push(text);
      }
    });
    if (!out.length) {
      //  Nothing block-level in there yet -- a browser sometimes leaves
      //  bare text in a fresh editable.
      var bare = inline(el).split("\n").map(function (l) { return l.trim(); })
        .filter(Boolean).join("\n");
      return bare;
    }
    return out.join("\n\n");
  }

  //  ---- keeping the canvas looking like the email ----

  //  Everything the vocabulary can write down, and nothing else. A block
  //  the toolbar made is bare -- execCommand emits <h2> with no style --
  //  so it is given the style the sent email would give it; and a block
  //  that could not be sent is turned into the nearest one that can,
  //  rather than being silently dropped on save.
  var KEEP = { P: "p", H2: "h2", H3: "h3", UL: "ul" };

  function swap(block, tagName) {
    var made = document.createElement(tagName);
    made.innerHTML = block.innerHTML;
    block.parentNode.replaceChild(made, block);
    return made;
  }

  //  Writing a style onto a block does not disturb the caret, so this
  //  may run on every keystroke: it is what keeps the canvas looking
  //  like the email while it is being written into.
  function restyle(el) {
    if (!el.dataset.rich) return;
    Array.prototype.forEach.call(el.children, function (block) {
      var name = KEEP[block.tagName];
      if (name && STYLES[name]) block.setAttribute("style", STYLES[name]);
      if (block.tagName === "UL" && STYLES.li) {
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          li.setAttribute("style", STYLES.li);
        });
      }
      Array.prototype.forEach.call(block.querySelectorAll("a"), function (a) {
        if (STYLES.a) a.setAttribute("style", STYLES.a);
      });
    });
  }

  //  A list made by the toolbar arrives INSIDE the paragraph it was made
  //  from -- <p><ul><li>...</li></ul></p>, which is not valid markup and
  //  is not what gets sent. It has to be lifted out to stand on its own,
  //  and the caret put back into it, or the next thing typed lands in
  //  front of the words already there. (It did: "moreFirst line".)
  function liftLists(el) {
    var moved = null;
    Array.prototype.slice.call(el.children).forEach(function (block) {
      if (block.tagName === "UL" || block.tagName === "OL") return;
      Array.prototype.slice.call(block.querySelectorAll("ul, ol")).forEach(function (list) {
        el.insertBefore(list, block);
        moved = list;
      });
      //  What is left of the paragraph once its list has gone is often
      //  nothing at all.
      if (!(block.textContent || "").trim() && !block.querySelector("img")) {
        block.parentNode.removeChild(block);
      }
    });
    if (moved) {
      var last = moved.querySelector("li:last-child");
      if (last) {
        var range = document.createRange();
        range.selectNodeContents(last);
        range.collapse(false);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
    }
  }

  //  Replacing an element moves the caret to the start of whatever
  //  replaced it, so this runs only when nobody is typing into it: on
  //  blur, and before saving. Doing it on every keystroke -- which is
  //  what it did first -- scattered the words as they were typed.
  function normalise(el) {
    if (!el.dataset.rich) return;
    liftLists(el);
    Array.prototype.slice.call(el.children).forEach(function (block) {
      var tag = block.tagName;
      //  H1 and H4 are what a browser reaches for at the edges of
      //  formatBlock; an email has two heading sizes, so they become the
      //  nearer of the two rather than arriving unstyled.
      if (tag === "H1") { block = swap(block, "h2"); tag = "H2"; }
      else if (tag === "H4" || tag === "H5" || tag === "H6") {
        block = swap(block, "h3"); tag = "H3";
      } else if (tag === "DIV" || tag === "BLOCKQUOTE" || tag === "PRE") {
        block = swap(block, "p"); tag = "P";
      } else if (tag === "OL") { block = swap(block, "ul"); tag = "UL"; }
      if (!KEEP[tag]) return;
      if (STYLES[KEEP[tag]]) block.setAttribute("style", STYLES[KEEP[tag]]);
      if (tag === "UL" && STYLES.li) {
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          li.setAttribute("style", STYLES.li);
        });
      }
      //  execCommand writes bold and italic as a STYLED SPAN, because
      //  styleWithCSS is on for the sake of the colour and font controls
      //  the other callers have. The vocabulary can only write down a
      //  real tag, so the span becomes one -- converted, not stripped.
      //  Stripping was the first version of this and it silently threw
      //  away every bold word the toolbar had just made.
      Array.prototype.slice.call(block.querySelectorAll("span[style]"))
        .forEach(function (span) {
          var cs = span.style;
          var weight = cs.fontWeight;
          var wraps = [];
          if (weight === "bold" || parseInt(weight, 10) >= 600) wraps.push("strong");
          if (cs.fontStyle === "italic") wraps.push("em");
          if (!wraps.length) return;
          var made = document.createElement(wraps[0]);
          made.innerHTML = wraps.length > 1
            ? "<" + wraps[1] + ">" + span.innerHTML + "</" + wraps[1] + ">"
            : span.innerHTML;
          span.parentNode.replaceChild(made, span);
        });
      //  A font or a colour means nothing in an inbox and the serialiser
      //  would throw it away anyway, so it goes now, while what is on
      //  screen can still be trusted to be what will be sent.
      Array.prototype.forEach.call(block.querySelectorAll("[style]"), function (kid) {
        if (kid.tagName === "LI") return;
        kid.removeAttribute("style");
      });
      Array.prototype.forEach.call(block.querySelectorAll("a"), function (a) {
        if (STYLES.a) a.setAttribute("style", STYLES.a);
      });
    });
  }

  function sync(el) {
    var name = el.dataset.slot;
    var box = store(name);
    if (!box) return;
    if (el.tagName === "INPUT") {
      box.value = el.value;
    } else if (el.dataset.multiline) {
      restyle(el);              //  safe while typing
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
    el.addEventListener("blur", function () {
      normalise(el);            //  the caret has gone; safe to rewrite
      sync(el);
      placeholders(el);
    });
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

  //  ---- the toolbar ----
  //
  //  It acts on whichever body slot was last written in, because it sits
  //  above the canvas rather than inside it: an email has no room for a
  //  toolbar, and this one is not being sent. Remembered on focus, since
  //  pressing a button takes the focus away from the words it is about
  //  to act on.
  var lastBody = null;
  form.querySelectorAll('[data-rich]').forEach(function (el) {
    el.addEventListener("focus", function () { lastBody = el; });
  });

  var bar = document.querySelector(".cms-issue-toolbar .cms-wysiwyg-toolbar");
  if (bar && window.cmsWysiwyg) {
    window.cmsWysiwyg.bindToolbar(bar, {
      //  One canvas, several body slots; the answer is the one being
      //  written in, not the one nearest the button.
      findBody: function () {
        return lastBody || form.querySelector('[data-rich]');
      },
      afterCommand: function (body) {
        if (!body) return;
        //  Only the safe half: the caret is still in there, ready for
        //  whatever is typed next. The one exception is a list, which
        //  arrives malformed and cannot be left that way even for a
        //  keystroke -- so it is lifted out here and the caret put back.
        liftLists(body);
        restyle(body);
        sync(body);
        placeholders(body);
      },
      askForLink: function (done) {
        //  The shared modal, the same one every other confirm in this
        //  app uses, rather than the browser's grey box.
        if (window.cmsModal) {
          window.cmsModal({
            message: "Link to which web address?",
            showInput: true,
            defaultValue: "https://",
            confirmLabel: "Add the link",
            danger: false,
          }).then(function (r) { done(r && r.confirmed ? r.value : null); });
        } else {
          done(window.prompt("Link to which web address?", "https://"));
        }
      },
      say: function (message) {
        if (window.cmsModal) {
          window.cmsModal({ message: message, confirmLabel: "OK", danger: false });
        } else {
          window.alert(message);
        }
      },
    });
  }

  form.addEventListener("submit", function () {
    form.querySelectorAll("[data-rich]").forEach(normalise);
    form.querySelectorAll("[data-slot]").forEach(sync);
  });
})();
