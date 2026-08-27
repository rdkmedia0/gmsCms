// Writing a newsletter by writing the newsletter.
//
// The email is rendered with its blocks opened up (email_layouts.render
// with edit=True) and this keeps ONE hidden field in step with it: the
// whole arrangement, as JSON. The route that saves never has to know any
// of this happened.
//
// Two decisions shape everything below.
//
// **Structure is saved and re-rendered, never rebuilt here.** Adding,
// removing, moving or restyling a block submits the form and lets the
// server draw it again from `emails/blocks.html` -- the same template
// that renders the email that gets SENT. Rebuilding the canvas in
// JavaScript would mean two renderers, and a preview that has drifted
// from what is sent is worse than no preview at all. The cost is a round
// trip per structural change; the scroll position and which block was
// selected are carried across it, so it reads as the page updating
// rather than reloading.
//
// **Typing is live.** What somebody writes goes straight into the block
// it belongs to and into the hidden field, with no round trip, because a
// keystroke that waits for the network is not writing.
//
// The text serialiser is the exact inverse of email_layouts.rich(): that
// turns a written vocabulary into inline-styled email blocks, this reads
// those blocks back as the same vocabulary.
//
//     ## a heading        ### a smaller heading
//     **bold**            *italic*
//     [words](address)    - a bullet
//
// If one changes the other has to, or a newsletter stops reading back
// the way it was written. tools/newsletter_editor_check.py drives the
// real thing in a browser and compares the two.
(function () {
  "use strict";

  var form = document.querySelector(".cms-issue-form");
  if (!form) return;

  var store = form.querySelector("[data-blocks-store]");
  var canvas = form.querySelector(".cms-issue-canvas");
  var toolbar = form.querySelector("[data-newsletter-toolbar]");
  var blockTools = form.querySelector("[data-block-tools]");
  var aside = form.querySelector("[data-block-aside]");
  if (!store || !canvas) return;

  var blocks = readJSON(store.value) || [];
  var layoutStarts = readJSON(text("cms-layout-starts")) || {};
  var selected = null;

  function text(id) {
    var el = document.getElementById(id);
    return el ? el.textContent : "";
  }

  function readJSON(raw) {
    try { return JSON.parse(raw || "null"); } catch (e) { return null; }
  }

  function save() {
    store.value = JSON.stringify(blocks);
  }

  //  ---- reading a text block back as the written vocabulary ----

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
    //  Only a SPAN, never a block: a heading carries font-weight:700 as
    //  part of the email's own style, and reading that as emphasis wraps
    //  every heading in ** -- which it did.
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
    //  paragraph a <br> stays a single newline, which rich() reads back
    //  as a break rather than a new paragraph.
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
      var body = inline(block).split("\n").map(function (line) {
        return line.trim();
      }).filter(Boolean).join("\n");
      if (!body) return;
      //  A heading is one line by definition; a break pasted into one
      //  would otherwise become a second, unmarked heading.
      out.push(mark ? mark + body.replace(/\n+/g, " ") : body);
    });
    if (!out.length) {
      return inline(el).split("\n").map(function (l) { return l.trim(); })
        .filter(Boolean).join("\n");
    }
    return out.join("\n\n");
  }

  //  ---- keeping a text block looking like the email ----

  var KEEP = { P: "p", H2: "h2", H3: "h3", UL: "ul" };

  function stylesFor(el) {
    var cell = el.closest("[data-styles]");
    return (cell && readJSON(cell.dataset.styles)) || {};
  }

  function swap(block, tagName) {
    var made = document.createElement(tagName);
    made.innerHTML = block.innerHTML;
    block.parentNode.replaceChild(made, block);
    return made;
  }

  //  Writing a style onto a block does not disturb the caret, so this may
  //  run on every keystroke: it is what keeps the canvas looking like the
  //  email while it is being written into.
  function restyle(el) {
    var st = stylesFor(el);
    Array.prototype.forEach.call(el.children, function (block) {
      var name = KEEP[block.tagName];
      if (name && st[name]) block.setAttribute("style", st[name]);
      if (block.tagName === "UL" && st.li) {
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          li.setAttribute("style", st.li);
        });
      }
      Array.prototype.forEach.call(block.querySelectorAll("a"), function (a) {
        if (st.a) a.setAttribute("style", st.a);
      });
    });
  }

  //  A list made by the toolbar arrives INSIDE the paragraph it was made
  //  from -- <p><ul><li>..</li></ul></p>, which is not valid markup, is
  //  not what gets sent, and puts the caret in front of the words already
  //  there. It is lifted out and the caret put back into it.
  function liftLists(el) {
    var moved = null;
    Array.prototype.slice.call(el.children).forEach(function (block) {
      if (block.tagName === "UL" || block.tagName === "OL") return;
      Array.prototype.slice.call(block.querySelectorAll("ul, ol")).forEach(function (list) {
        el.insertBefore(list, block);
        moved = list;
      });
      if (!(block.textContent || "").trim() && !block.querySelector("img")) {
        block.parentNode.removeChild(block);
      }
    });
    if (!moved) return;
    var last = moved.querySelector("li:last-child");
    if (!last) return;
    var range = document.createRange();
    range.selectNodeContents(last);
    range.collapse(false);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  //  Replacing an element moves the caret to the start of whatever
  //  replaced it, so this runs only when nobody is typing into it: on
  //  blur, and before saving. Doing it on every keystroke -- which is
  //  what it did first -- scattered the words as they were typed.
  function normalise(el) {
    var st = stylesFor(el);
    liftLists(el);
    Array.prototype.slice.call(el.children).forEach(function (block) {
      var tag = block.tagName;
      //  H1 and H4 are what a browser reaches for at the edges of
      //  formatBlock; a text block has two heading sizes, so they become
      //  the nearer of the two rather than arriving unstyled.
      if (tag === "H1") { block = swap(block, "h2"); tag = "H2"; }
      else if (tag === "H4" || tag === "H5" || tag === "H6") {
        block = swap(block, "h3"); tag = "H3";
      } else if (tag === "DIV" || tag === "BLOCKQUOTE" || tag === "PRE") {
        block = swap(block, "p"); tag = "P";
      } else if (tag === "OL") { block = swap(block, "ul"); tag = "UL"; }
      if (!KEEP[tag]) return;
      if (st[KEEP[tag]]) block.setAttribute("style", st[KEEP[tag]]);
      if (tag === "UL" && st.li) {
        Array.prototype.forEach.call(block.querySelectorAll("li"), function (li) {
          li.setAttribute("style", st.li);
        });
      }
      //  execCommand writes bold and italic as a STYLED SPAN, because
      //  styleWithCSS is on for the sake of the controls the other
      //  callers of this toolbar have. The vocabulary can only write down
      //  a real tag, so the span becomes one -- converted, not stripped.
      //  Stripping was the first version and it silently threw away every
      //  bold word the toolbar had just made.
      Array.prototype.slice.call(block.querySelectorAll("span[style]"))
        .forEach(function (span) {
          var wraps = [];
          var weight = span.style.fontWeight;
          if (weight === "bold" || parseInt(weight, 10) >= 600) wraps.push("strong");
          if (span.style.fontStyle === "italic") wraps.push("em");
          if (!wraps.length) return;
          var made = document.createElement(wraps[0]);
          made.innerHTML = wraps.length > 1
            ? "<" + wraps[1] + ">" + span.innerHTML + "</" + wraps[1] + ">"
            : span.innerHTML;
          span.parentNode.replaceChild(made, span);
        });
      //  A font or a colour picked up from a paste means nothing here --
      //  a block's font and colour are the block's, set from the toolbar
      //  -- and the serialiser would drop it anyway.
      Array.prototype.forEach.call(block.querySelectorAll("[style]"), function (kid) {
        if (kid.tagName === "LI") return;
        kid.removeAttribute("style");
      });
      Array.prototype.forEach.call(block.querySelectorAll("a"), function (a) {
        if (st.a) a.setAttribute("style", st.a);
      });
    });
  }

  //  ---- the blocks on screen, and the ones in the field ----

  function cellOf(el) { return el.closest("[data-block]"); }

  function indexOf(el) {
    var cell = cellOf(el);
    return cell ? parseInt(cell.dataset.block, 10) : -1;
  }

  function readField(el) {
    var i = indexOf(el);
    if (i < 0 || !blocks[i]) return;
    var field = el.dataset.field;
    if (el.dataset.rich) {
      restyle(el);
      blocks[i][field] = textFromBlocks(el);
    } else {
      blocks[i][field] = (el.innerText || "").replace(/\u00a0/g, " ").trim();
    }
    placeholder(el);
    save();
  }

  //  An empty editable shows what belongs in it. A CSS :empty rule cannot
  //  be trusted here because a browser leaves a stray <br> behind.
  function placeholder(el) {
    el.classList.toggle("cms-slot-blank", !(el.innerText || "").trim());
  }

  canvas.querySelectorAll("[data-field]").forEach(function (el) {
    placeholder(el);
    el.addEventListener("input", function () { readField(el); });
    el.addEventListener("blur", function () {
      if (el.dataset.rich) normalise(el);
      readField(el);
    });
    //  Return inside a heading or a button would make a second line in
    //  something that is drawn as one.
    if (!el.dataset.rich) {
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); el.blur(); }
      });
    }
    //  Paste as words, not as somebody else's markup: a paragraph copied
    //  from a web page brings its fonts and colours with it, and an email
    //  that half matches the site looks like a mistake.
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      var plain = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, plain);
    });
  });

  //  ---- selecting a block ----

  function select(i) {
    selected = (i >= 0 && blocks[i]) ? i : null;
    canvas.querySelectorAll("[data-block]").forEach(function (cell) {
      cell.classList.toggle("cms-block-selected",
        selected !== null && parseInt(cell.dataset.block, 10) === selected);
    });
    showTools();
  }

  function showTools() {
    if (!blockTools) return;
    var block = selected === null ? null : blocks[selected];
    var name = blockTools.querySelector("[data-selected-name]");
    blockTools.classList.toggle("cms-tools-idle", !block);
    blockTools.querySelectorAll("select, input, button").forEach(function (c) {
      c.disabled = !block;
    });
    if (!block) {
      if (name) name.textContent = "Nothing selected";
      if (aside) aside.hidden = true;
      return;
    }
    if (name) {
      name.textContent = (BLOCK_NAMES[block.type] || "Block") + " " + (selected + 1);
    }
    var style = block.style || {};
    setControl("align", style.align || "left");
    setControl("font", style.font || "");
    setControl("color", style.color || "#333c47");
    setControl("bg", style.bg || "#f2f4f7");
    //  Where a button or a picture points cannot be typed INTO the
    //  email, so it sits under the canvas -- and only for the blocks
    //  that have one.
    if (aside) {
      var wants = block.type === "button" || block.type === "image";
      aside.hidden = !wants;
      if (wants) {
        var field = aside.querySelector("[data-block-field='url']");
        var label = aside.querySelector("[data-aside-label]");
        var hint = aside.querySelector("[data-aside-hint]");
        if (field) field.value = block.url || "";
        if (label) {
          label.textContent = block.type === "button"
            ? "Where this button goes" : "Where this picture links to";
        }
        if (hint) {
          hint.textContent = block.type === "button"
            ? "A button with no address is left out of the send, because a button that goes nowhere is worse than none."
            : "Optional. Leave it blank and the picture is not a link.";
        }
      }
    }
  }

  var BLOCK_NAMES = {};
  if (toolbar) {
    toolbar.querySelectorAll("[data-add-block]").forEach(function (btn) {
      //  The plain name, not the button's own text: that starts with the
      //  block's icon, so a selected picture announced itself as
      //  "(picture glyph) Picture 1".
      BLOCK_NAMES[btn.dataset.addBlock] = btn.dataset.blockName
        || (btn.textContent || "").trim();
    });
  }

  function setControl(key, value) {
    var control = blockTools.querySelector("[data-block-style='" + key + "']");
    if (control) control.value = value;
  }

  canvas.addEventListener("click", function (e) {
    var cell = cellOf(e.target);
    select(cell ? parseInt(cell.dataset.block, 10) : -1);
  });
  //  Clicking straight into some words selects that block too -- nobody
  //  clicks the margin first.
  canvas.addEventListener("focusin", function (e) {
    var cell = cellOf(e.target);
    if (cell) select(parseInt(cell.dataset.block, 10));
  });

  //  ---- structural changes: saved, then drawn again by the server ----

  var KEEP_SCROLL = "cmsNewsletterScroll";
  var KEEP_SELECTED = "cmsNewsletterSelected";

  //  True while a structural change is being submitted. The submit
  //  handler re-reads the canvas into `blocks` BY INDEX, which is right
  //  when somebody presses Save and catastrophic straight after a splice:
  //  the DOM still shows the old arrangement, so block 3's words would be
  //  written into whatever is at position 3 now. Every structural action
  //  therefore collects first, then moves, then submits with the re-read
  //  skipped.
  var structural = false;

  function collect() {
    canvas.querySelectorAll("[data-rich]").forEach(normalise);
    canvas.querySelectorAll("[data-field]").forEach(readField);
  }

  function reload(nextSelected) {
    structural = true;
    save();
    try {
      sessionStorage.setItem(KEEP_SCROLL, String(window.scrollY));
      sessionStorage.setItem(KEEP_SELECTED, String(nextSelected === undefined
        ? (selected === null ? "" : selected) : nextSelected));
    } catch (e) { /* a private window; the page still works, it just jumps */ }
    form.requestSubmit();
  }

  if (toolbar) {
    toolbar.querySelectorAll("[data-add-block]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        //  Below whatever is selected, because that is where somebody
        //  looking at a block wants the next one; at the end otherwise.
        collect();
        var at = selected === null ? blocks.length : selected + 1;
        blocks.splice(at, 0, { type: btn.dataset.addBlock, style: {} });
        reload(at);
      });
    });

    var layout = toolbar.querySelector("#layout-select");
    if (layout) {
      var chosen = layout.value;
      layout.addEventListener("change", function () {
        var next = layout.value;
        var starts = layoutStarts[next] || [];
        var written = blocks.some(function (b) {
          return (b.text || "").trim() || (b.label || "").trim() || (b.src || "").trim();
        });
        var go = function (ok) {
          if (!ok) { layout.value = chosen; return; }
          chosen = next;
          blocks = JSON.parse(JSON.stringify(starts));
          reload("");
        };
        //  Changing the template lays the blocks out afresh, which
        //  replaces what is there. Asked, never assumed -- and not asked
        //  at all when there is nothing to lose.
        if (!written) { go(true); return; }
        if (window.cmsModal) {
          window.cmsModal({
            message: "Lay this newsletter out as “" + layout.options[layout.selectedIndex].text
              + "”? What you have written in it is replaced.",
            confirmLabel: "Lay it out again",
          }).then(function (r) { go(r && r.confirmed); });
        } else {
          go(window.confirm("Replace what you have written?"));
        }
      });
    }
  }

  if (blockTools) {
    blockTools.querySelectorAll("[data-block-style]").forEach(function (control) {
      //  `change`, not `input`: a colour picker fires continuously while
      //  a finger is moving, and each one of those would be a save.
      control.addEventListener("change", function () {
        if (selected === null) return;
        collect();
        var key = control.dataset.blockStyle;
        blocks[selected].style = blocks[selected].style || {};
        if (control.value) blocks[selected].style[key] = control.value;
        else delete blocks[selected].style[key];
        reload();
      });
    });

    blockTools.querySelectorAll("[data-block-style-clear]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (selected === null) return;
        collect();
        delete (blocks[selected].style || {})[btn.dataset.blockStyleClear];
        reload();
      });
    });

    blockTools.querySelectorAll("[data-block-move]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (selected === null) return;
        collect();
        var to = selected + parseInt(btn.dataset.blockMove, 10);
        if (to < 0 || to >= blocks.length) return;
        var moving = blocks.splice(selected, 1)[0];
        blocks.splice(to, 0, moving);
        reload(to);
      });
    });

    var remove = blockTools.querySelector("[data-block-remove]");
    if (remove) {
      remove.addEventListener("click", function () {
        if (selected === null) return;
        collect();
        blocks.splice(selected, 1);
        reload("");
      });
    }
  }

  if (aside) {
    var url = aside.querySelector("[data-block-field='url']");
    if (url) {
      url.addEventListener("change", function () {
        if (selected === null) return;
        collect();
        blocks[selected].url = url.value.trim();
        reload();
      });
    }
  }

  //  An empty picture frame asks the Media Library for one -- the same
  //  picker the live page uses, extracted so there is only ever one.
  canvas.addEventListener("click", async function (e) {
    var frame = e.target.closest("[data-pick-image]");
    if (!frame || !window.cmsImagePicker) return;
    var i = indexOf(frame);
    if (i < 0) return;
    var chosen = await window.cmsImagePicker.open();
    if (!chosen) return;
    collect();
    blocks[i].src = chosen;
    reload(i);
  });

  //  ...and clicking a picture that is already there replaces it.
  canvas.addEventListener("dblclick", async function (e) {
    var img = e.target.closest("img");
    if (!img || !window.cmsImagePicker) return;
    var i = indexOf(img);
    if (i < 0 || !blocks[i] || blocks[i].type !== "image") return;
    var chosen = await window.cmsImagePicker.open();
    if (!chosen) return;
    blocks[i].src = chosen;
    reload(i);
  });

  //  ---- the writing toolbar ----
  //
  //  It acts on whichever text block was last written in, because it
  //  sits above the canvas rather than inside it. Remembered on focus,
  //  since pressing a button takes the focus away from the words it is
  //  about to act on.
  var lastBody = null;
  canvas.querySelectorAll("[data-rich]").forEach(function (el) {
    el.addEventListener("focus", function () { lastBody = el; });
  });

  var bar = form.querySelector(".cms-toolbar-writing .cms-wysiwyg-toolbar");
  if (bar && window.cmsWysiwyg) {
    window.cmsWysiwyg.bindToolbar(bar, {
      findBody: function () {
        return lastBody || canvas.querySelector("[data-rich]");
      },
      afterCommand: function (body) {
        if (!body) return;
        //  A list arrives malformed and cannot be left that way even for
        //  a keystroke, so it is lifted here; everything else that moves
        //  a node waits for blur.
        liftLists(body);
        restyle(body);
        readField(body);
      },
      askForLink: function (done) {
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
    //  See `structural`: after a splice the canvas and `blocks` no longer
    //  line up, and reading one into the other would scramble them.
    if (!structural) collect();
    save();
  });

  //  ---- coming back from a structural change ----
  //
  //  A round trip that jumped to the top of the page and forgot which
  //  block you were working on would read as the page reloading. Putting
  //  both back makes it read as the page updating, which is what it is.
  (function restore() {
    var where, which;
    try {
      where = sessionStorage.getItem(KEEP_SCROLL);
      which = sessionStorage.getItem(KEEP_SELECTED);
      sessionStorage.removeItem(KEEP_SCROLL);
      sessionStorage.removeItem(KEEP_SELECTED);
    } catch (e) { return; }
    if (where) window.scrollTo(0, parseInt(where, 10) || 0);
    if (which !== null && which !== "") select(parseInt(which, 10));
    else showTools();
  })();
})();
