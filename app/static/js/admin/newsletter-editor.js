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
    showBlockHandle();
    showTools();
  }

  //  Move and remove, ON the block, once it is selected.
  //
  //  They were only in the ribbon: a bare "×" at the far end of a fourth
  //  group, dimmed until something is selected. Adding is a labelled
  //  button that is always there; removing was invisible until you knew
  //  to wake it up by clicking a block first -- which is why it was
  //  reported as "I can add items but not remove them". It was there and
  //  it worked. Nobody could find it, which is the same thing.
  //
  //  On the block is where they belong anyway: you act on the thing
  //  where the thing is, which is how a section's own toolbar already
  //  works everywhere else in this editor.
  var handle = null;

  function blockHandle() {
    if (handle) return handle;
    handle = document.createElement("div");
    handle.className = "cms-block-handle";
    handle.innerHTML =
      '<button type="button" data-handle="-1" title="Move this block up one place.">↑</button>'
      + '<button type="button" data-handle="1" title="Move this block down one place.">↓</button>'
      + '<button type="button" data-handle="x" class="cms-block-handle-remove"'
      + ' title="Remove this block from the newsletter. Nothing else moves.">×</button>';
    handle.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-handle]");
      if (!btn || selected === null) return;
      e.preventDefault();
      collect();
      if (btn.dataset.handle === "x") {
        blocks.splice(selected, 1);
        reload("");
        return;
      }
      var to = selected + parseInt(btn.dataset.handle, 10);
      if (to < 0 || to >= blocks.length) return;
      blocks.splice(to, 0, blocks.splice(selected, 1)[0]);
      reload(to);
    });
    return handle;
  }

  function showBlockHandle() {
    var h = blockHandle();
    if (selected === null) {
      if (h.parentNode) h.parentNode.removeChild(h);
      return;
    }
    var cell = canvas.querySelector("[data-block='" + selected + "']");
    if (!cell) return;
    //  Parented to the CANVAS and positioned over the cell -- never put
    //  inside it. Two reasons, and the second was found by watching the
    //  events rather than reasoning about them:
    //
    //  Nothing that is not the email may live in that table, or the
    //  canvas stops being the thing that gets sent.
    //
    //  And appending into the cell moved the DOM mid-gesture. The real
    //  sequence was `mousedown:H2, focusin:H2, mouseup:P, click:TBODY`:
    //  focusin selected the block, the handle went in, the block
    //  shifted under the pointer, mouseup landed on a different element
    //  and the click resolved to the shared ancestor -- which carries no
    //  data-block, so it deselected. The handle was destroying the
    //  selection that created it, and NOTHING could be selected by
    //  clicking at all.
    if (h.parentNode !== canvas) canvas.appendChild(h);
    var box = cell.getBoundingClientRect();
    var frame = canvas.getBoundingClientRect();
    h.style.top = (box.top - frame.top - 12) + "px";
    h.style.left = (box.right - frame.left - 78) + "px";
    h.querySelector("[data-handle='-1']").disabled = selected === 0;
    h.querySelector("[data-handle='1']").disabled = selected === blocks.length - 1;
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
      if (name) name.textContent = "No block";
      if (postsControls) {
        postsControls.classList.add("cms-tools-idle");
        postsControls.querySelectorAll("[data-block-field]").forEach(function (f) {
          f.disabled = true;
        });
      }
      if (aside) {
        aside.classList.add("cms-tools-idle");
        var noneField = aside.querySelector("[data-block-field='url']");
        if (noneField) { noneField.disabled = true; noneField.value = ""; }
      }
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
    //  email. It stands with the block's other properties in the ribbon
    //  -- alignment, font, colour, and this -- rather than in a card of
    //  its own under the message, which is what it was: a label, a
    //  full-width input and a paragraph of hint, for one field. It wakes
    //  only for the blocks that have one.
    //
    //  The hint it used to carry moved onto the field's own tooltip.
    //  Every control here explains itself that way, and a sentence of
    //  running text in a row of controls was the thing that made this
    //  read as a section rather than as part of the toolbar.
    if (aside) {
      var wants = block.type === "button" || block.type === "image";
      //  Dimmed, never hidden. Hiding it changed the group's width by
      //  223px the moment a button was selected, which wrapped a row --
      //  the toolbar changing shape as it is used is the thing the other
      //  block controls are dimmed to prevent.
      aside.classList.toggle("cms-tools-idle", !wants);
      //  The posts controls wake for a posts block, and only then.
      if (postsControls) {
        var isPosts = block.type === "posts";
        postsControls.classList.toggle("cms-tools-idle", !isPosts);
        postsControls.querySelectorAll("[data-block-field]").forEach(function (f) {
          f.disabled = !isPosts;
          if (isPosts) {
            f.value = block[f.dataset.blockField] == null
              ? (f.type === "number" ? 3 : "")
              : block[f.dataset.blockField];
          }
        });
      }
      var urlField = aside.querySelector("[data-block-field='url']");
      if (urlField) urlField.disabled = !wants;
      if (!wants) {
        if (urlField) urlField.value = "";
        var idleLabel = aside.querySelector("[data-aside-label]");
        if (idleLabel) idleLabel.textContent = "Link";
      }
      if (wants) {
        var field = aside.querySelector("[data-block-field='url']");
        var label = aside.querySelector("[data-aside-label]");
        if (field) {
          field.value = block.url || "";
          field.title = block.type === "button"
            ? "Where this button goes. A button with no address is left out of the send, because a button that goes nowhere is worse than none."
            : "Where this picture links to. Optional — leave it blank and the picture is not a link.";
          field.placeholder = block.type === "button" ? "https://" : "https:// (optional)";
        }
        if (label) label.textContent = block.type === "button" ? "Goes to" : "Links to";
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

  //  mousedown, not click.
  //
  //  A `click` fires on the common ancestor of where the button went
  //  DOWN and where it came UP, and those differ here: pressing on a
  //  block focuses its contenteditable, the browser scrolls that into
  //  view, and by mouseup the pointer is over something else. Watched
  //  rather than reasoned about, the sequence was `mousedown:H2,
  //  focusin:H2, mouseup:P, click:TBODY` -- and TBODY carries no
  //  data-block, so the click DESELECTED whatever the focus had just
  //  selected. Nothing could be selected by clicking at all, which is
  //  why the block controls were reported as missing: they are only
  //  offered for a selected block, and there was never one.
  //
  //  mousedown lands on what was actually pressed, before any of that.
  canvas.addEventListener("mousedown", function (e) {
    //  The handle lives in the canvas but is not part of the email;
    //  pressing it must not clear the selection it acts on.
    if (e.target.closest(".cms-block-handle")) return;
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

      //  Has anybody actually written in this, or is it still exactly
      //  what the template laid out?
      //
      //  Asking "does any block contain words" is the obvious test and
      //  it is wrong: a template lays out "A heading" and "What you want
      //  to say", so a brand-new newsletter answered YES and changing
      //  the shape asked to replace work that did not exist. Every
      //  time. Which made the dropdown -- now the ONLY way to choose a
      //  shape -- feel like it was guarding something, on a newsletter
      //  with nothing in it.
      //
      //  The real question is whether it still MATCHES what it was laid
      //  out as. Compared field by field against this layout's own
      //  starting blocks, so the placeholder words a template ships
      //  count as untouched and one typed character counts as written.
      function hasBeenWrittenIn() {
        var was = layoutStarts[chosen] || [];
        if (blocks.length !== was.length) return true;
        return blocks.some(function (b, i) {
          var start = was[i] || {};
          if (b.type !== start.type) return true;
          return ["text", "label", "src", "url"].some(function (field) {
            return (b[field] || "").trim() !== (start[field] || "").trim();
          });
        });
      }
      layout.addEventListener("change", function () {
        var next = layout.value;
        var starts = layoutStarts[next] || [];
        var written = hasBeenWrittenIn();
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
  }

  //  Which blog a Blog-posts block shows, and how many. Same shape as
  //  the link field: a property of the selected block, dimmed rather
  //  than hidden so the ribbon does not change height as it is used.
  var postsControls = form.querySelector("[data-posts-controls]");
  if (postsControls) {
    postsControls.querySelectorAll("[data-block-field]").forEach(function (field) {
      field.addEventListener("change", function () {
        if (selected === null) return;
        collect();
        blocks[selected][field.dataset.blockField] =
          field.type === "number" ? parseInt(field.value, 10) || 3 : field.value;
        //  Reloaded through the SERVER, because the posts themselves are
        //  resolved there -- choosing a blog has to fetch its posts, and
        //  a second renderer in JavaScript would drift from the one that
        //  renders what is sent.
        reload(selected);
      });
    });
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

  //  Delete asks first, and says what survives it. It is a submit on
  //  the one form like every other action here -- a nested <form> would
  //  be invalid, and a GET link that deletes is worse than either.
  var deleteIssueBtn = form.querySelector("[data-delete-issue]");
  if (deleteIssueBtn) {
    deleteIssueBtn.addEventListener("click", async function (e) {
      if (deleteIssueBtn.dataset.confirmed === "1") return;
      e.preventDefault();
      var answer = window.cmsModal
        ? await window.cmsModal({
            message: "Delete this newsletter? What was already sent stays on the record.",
            confirmLabel: "Delete it",
          })
        : window.confirm("Delete this newsletter?");
      if (!answer || answer.confirmed === false) return;
      deleteIssueBtn.dataset.confirmed = "1";
      deleteIssueBtn.click();
    });
  }

  //  ---- keeping an arrangement you like -------------------------------
  //
  //  A layout is a starting arrangement, not a kind -- the shipped ones
  //  are a dictionary and a saved one is the same thing written down. So
  //  saving is: name it, post the blocks, and it is in the same dropdown.
  //
  //  What is posted is what is on the CANVAS, not what was last saved.
  //  Somebody who has just arranged something and likes it should not
  //  have to save the newsletter before they can keep its shape.
  var layoutSelect = form.querySelector("#layout-select");
  var subjectField = form.querySelector("#subject");
  var saveLayoutBtn = form.querySelector("[data-save-layout]");
  var deleteLayoutBtn = form.querySelector("[data-delete-layout]");

  //  Remove wakes only on one of your own. A shipped layout is in the
  //  code and would be back on the next boot, so a live button there
  //  would be a button that lies.
  function refreshLayoutButtons() {
    if (!deleteLayoutBtn || !layoutSelect) return;
    var mine = (layoutSelect.value || "").indexOf("saved:") === 0;
    deleteLayoutBtn.disabled = !mine;
    deleteLayoutBtn.title = mine
      ? "Remove “" + layoutSelect.options[layoutSelect.selectedIndex].text
        + "” from the Template list. Newsletters already laid out from it are untouched."
      : "Only templates you saved yourself can be removed. This one is built in.";
  }
  if (layoutSelect) layoutSelect.addEventListener("change", refreshLayoutButtons);
  refreshLayoutButtons();

  if (saveLayoutBtn) {
    saveLayoutBtn.addEventListener("click", async function () {
      collect();
      if (!blocks.length) {
        if (window.cmsModal) {
          await window.cmsModal({
            message: "There is nothing laid out to save yet.",
            confirmLabel: "OK", danger: false, showConfirm: true,
          });
        }
        return;
      }
      var answer = window.cmsModal
        ? await window.cmsModal({
            message: "Save this arrangement as a template you can start from again. "
              + "What should it be called?",
            showInput: true,
            defaultValue: (subjectField && subjectField.value.trim())
              || "My arrangement",
            confirmLabel: "Save it",
            danger: false,
          })
        : window.prompt("Name for this template");
      var name = answer && answer.value !== undefined ? answer.value : answer;
      if (!name || !String(name).trim()) return;
      var body = new FormData();
      body.append("name", String(name).trim());
      body.append("blocks_json", JSON.stringify(blocks));
      var res = await fetch(saveLayoutBtn.dataset.saveLayoutUrl, {
        method: "POST", headers: { "X-Inline-Edit": "1" }, body,
      });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok || data.error) {
        if (window.cmsModal) {
          await window.cmsModal({
            message: data.error || "That could not be saved.",
            confirmLabel: "OK", danger: false,
          });
        }
        return;
      }
      //  Reloaded rather than added to the dropdown here. The list comes
      //  from the server, and a second place building the same list is
      //  how the two come to disagree.
      window.location.reload();
    });
  }

  if (deleteLayoutBtn) {
    deleteLayoutBtn.addEventListener("click", async function () {
      if (deleteLayoutBtn.disabled || !layoutSelect) return;
      var label = layoutSelect.options[layoutSelect.selectedIndex].text;
      var answer = window.cmsModal
        ? await window.cmsModal({
            message: "Remove “" + label + "” from the Template list? "
              + "Newsletters already laid out from it are not affected.",
            confirmLabel: "Remove it",
          })
        : window.confirm("Remove " + label + "?");
      if (!answer || answer.confirmed === false) return;
      var body = new FormData();
      body.append("key", layoutSelect.value);
      await fetch(deleteLayoutBtn.dataset.deleteLayoutUrl, {
        method: "POST", headers: { "X-Inline-Edit": "1" }, body,
      });
      window.location.reload();
    });
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

  //  ---- the compose bar ----
  //
  //  Send, Schedule, Save and Preview are one form told apart by
  //  `formaction`, so all four read the same "who gets it" control. Three
  //  things have to happen in JavaScript, and only three.

  //  1 and 2, the clock and any stored time shown back on it, are
  //  admin/local-time.js -- the Newsletters list needs exactly the same
  //  two things, and two copies that must agree about daylight saving is
  //  a bug waiting to be written.

  //  3. Send asks first, because it cannot be taken back. Schedule does
  //     not: it CAN be taken back, right up until it goes.
  var sendBtn = form.querySelector("[data-send]");
  if (sendBtn) {
    sendBtn.addEventListener("click", function (e) {
      if (sendBtn.dataset.confirmed === "1") return;
      e.preventDefault();
      var who = form.querySelector("#audience");
      var count = who ? who.options[who.selectedIndex].text.trim() : "your list";
      var ask = window.cmsModal
        ? window.cmsModal({
            message: "Send this now to " + count + "? It cannot be unsent.",
            confirmLabel: "Send it",
          }).then(function (r) { return r && r.confirmed; })
        : Promise.resolve(window.confirm("Send this now? It cannot be unsent."));
      ask.then(function (yes) {
        if (!yes) return;
        sendBtn.dataset.confirmed = "1";
        collect();
        save();
        if (window.cmsLocalTime) window.cmsLocalTime.stampOffsets();
        //  Submitted THROUGH the button, so its formaction is the one
        //  used -- form.submit() would post to the editor instead and
        //  quietly save rather than send.
        structural = true;
        sendBtn.click();
      });
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
