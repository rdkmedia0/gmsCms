// The rich-text toolbar's behaviour, written once.
//
// It lived in inline-editor.js, bound to the live page's own idea of
// which editable a button belongs to and how to save it. The blog editor
// needed the same buttons and got a second, smaller implementation
// instead -- two toolbars for one job.
//
// The generic half is here: read data-cmd off a control, run it, tell the
// caller something changed. The two things that differ between callers
// are passed in, because they are genuinely different questions:
//
//   findBody(el)  which editable does this control act on? The live page
//                 walks up to a section; a form has exactly one.
//   afterCommand  what now? The live page autosaves; a form copies the
//                 markup into the hidden field the server reads.
//   askForLink    how to ask for a URL. The live page has its own modal;
//                 a plain form has the browser's prompt.
(function () {
  "use strict";

  function run(cmd, value) {
    //  styleWithCSS so a colour or a font comes out as an inline style
    //  rather than a <font> tag, which nothing downstream understands.
    document.execCommand("styleWithCSS", false, true);
    document.execCommand(cmd, false, value || null);
  }

  var ALIGN = {
    justifyLeft: "left", justifyCenter: "center",
    justifyRight: "right", justifyFull: "justify",
  };

  //  The editable a command should act on, found from the current
  //  selection when the caller could not supply it -- the floating
  //  toolbar is not inside the section, so `findBody(button)` comes back
  //  empty, which is exactly why aligning did nothing and did not save.
  function bodyFromSelection() {
    var sel = document.getSelection();
    if (!sel || !sel.rangeCount) return null;
    var node = sel.getRangeAt(0).startContainer;
    var el = node.nodeType === 3 ? node.parentElement : node;
    return (el && el.closest)
      ? el.closest('.cms-wysiwyg-body,[contenteditable=""],[contenteditable="true"]')
      : null;
  }

  //  Align every top-level block in the editable. The style has to sit on
  //  a CHILD, not the editable itself -- the save stores the editable's
  //  innerHTML, so a text-align on the editable would be thrown away.
  //  Bare text with no block gets wrapped in one so it has somewhere to
  //  carry the alignment. Returns the editable it acted on, so the caller
  //  can save that one.
  function applyAlign(body, align) {
    body = body || bodyFromSelection();
    if (!body) return null;
    var blocks = Array.prototype.filter.call(body.children, function (c) {
      return c.nodeType === 1;
    });
    if (!blocks.length) {
      var wrap = document.createElement("div");
      while (body.firstChild) wrap.appendChild(body.firstChild);
      body.appendChild(wrap);
      blocks = [wrap];
    }
    blocks.forEach(function (b) { b.style.textAlign = align; });
    return body;
  }

  //  The anchor the caret is in or around -- used to hang a tooltip on the
  //  link createLink just made.
  function _linkFromSelection() {
    var s = window.getSelection();
    if (!s || !s.rangeCount) return null;
    var c = s.getRangeAt(0).commonAncestorContainer;
    var el = c.nodeType === 1 ? c : c.parentElement;
    if (!el) return null;
    if (el.closest) {
      var a = el.closest("a[href]");
      if (a) return a;
    }
    return el.querySelector ? el.querySelector("a[href]") : null;
  }

  function bindToolbar(root, options) {
    var findBody = options.findBody;
    var afterCommand = options.afterCommand || function () {};
    var askForLink = options.askForLink || function (done, body, current) {
      var url = window.prompt("Link to which web address?", (current && current.url) || "https://");
      done(url || null);
    };
    var onLinkImage = options.onLinkImage || null;
    //  How a caller tells somebody something. The live page has a toast;
    //  a form has nothing, so it falls back to the browser.
    var say = options.say || function (message) { window.alert(message); };
    //  What an uploaded picture is for. Absent: it goes in at the caret.
    var onImage = options.onImage || null;

    root.querySelectorAll("button[data-cmd]").forEach(function (btn) {
      //  mousedown, not click: pressing a button blurs the editable and
      //  takes the selection with it, so the command lands on nothing.
      btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
      btn.addEventListener("click", function () {
        var cmd = btn.dataset.cmd;
        var value = btn.dataset.value || null;
        var body = findBody(btn);
        //  Alignment set DIRECTLY on the block, not via execCommand.
        //  execCommand("justifyCenter") is unreliable on an editable that
        //  is a single block (it may style the wrong node, or nothing),
        //  which is exactly what a Text tool holding one paragraph is --
        //  so "centre this" appeared to do nothing. Writing text-align on
        //  the block the caret sits in always lands, and saves like any
        //  other edit.
        if (ALIGN[cmd]) {
          //  Save whichever editable it actually aligned -- which may be
          //  the one found from the selection when `body` came back empty.
          afterCommand(applyAlign(body, ALIGN[cmd]) || body);
          setTimeout(function () { root.__cmsRefreshState && root.__cmsRefreshState(); }, 0);
          return;
        }
        if (cmd === "createLink") {
          //  Asking for the URL means a prompt/modal with its own input,
          //  and giving that focus COLLAPSES the text selection this link
          //  is meant to wrap -- so by the time createLink runs there is
          //  nothing selected and it silently does nothing. Capture the
          //  range now (the button's mousedown-preventDefault kept it
          //  alive to here) and put it back, in the editable, right before
          //  wrapping it.
          var linkSel = window.getSelection();
          var savedLinkRange = (linkSel && linkSel.rangeCount)
            ? linkSel.getRangeAt(0).cloneRange() : null;
          //  If the caret is already in a link, this EDITS it: the prompt
          //  opens pre-filled with its address and tooltip, and the same
          //  anchor is updated rather than a second one being made inside it.
          var existing = _linkFromSelection();
          var current = existing
            ? { url: existing.getAttribute("href") || "", title: existing.getAttribute("title") || "" }
            : null;
          askForLink(function (url, title) {
            if (url) {
              if (existing) {
                existing.setAttribute("href", url);
                if ((title || "").trim()) existing.setAttribute("title", (title + "").trim());
                else existing.removeAttribute("title");
              } else if (!(onLinkImage && onLinkImage(body, url, title))) {
                if (body && body.focus) body.focus();
                if (savedLinkRange) {
                  var s2 = window.getSelection();
                  s2.removeAllRanges();
                  s2.addRange(savedLinkRange);
                }
                document.execCommand("createLink", false, url);
                //  The optional hover tooltip goes on the anchor createLink
                //  just made -- found from the selection, which now sits
                //  inside it.
                var made = _linkFromSelection();
                if (made) {
                  if (title) made.setAttribute("title", (title + "").trim());
                  else made.removeAttribute("title");
                }
              }
            }
            afterCommand(body);
          }, body, current);
          return;
        }
        run(cmd, value);
        afterCommand(body);
        setTimeout(function () { root.__cmsRefreshState && root.__cmsRefreshState(); }, 0);
      });
    });

    root.querySelectorAll("select[data-cmd], input[data-cmd]").forEach(function (ctrl) {
      var eventName = ctrl.tagName === "SELECT" ? "change" : "input";
      ctrl.addEventListener(eventName, function () {
        if (!ctrl.value) return;
        run(ctrl.dataset.cmd, ctrl.value);
        if (ctrl.tagName === "SELECT") ctrl.value = "";   // reset the "Font…" picker
        afterCommand(findBody(ctrl));
      });
    });

    //  Show what is ALREADY applied where the caret is: the B/I/U buttons
    //  light up on bold/italic/underlined text, the H2/H3/¶ button for the
    //  block the caret sits in lights up, and so does the current alignment.
    //  A toolbar that never reflects the state makes you guess whether text
    //  is already bold, and toggle it off by accident.
    var STATE_CMDS = { bold: 1, italic: 1, underline: 1, strikeThrough: 1,
                       insertUnorderedList: 1, insertOrderedList: 1 };
    var ALIGN_STATE = { justifyLeft: "left", justifyCenter: "center",
                        justifyRight: "right", justifyFull: "justify" };
    var BLOCK_TAGS = /^(P|H1|H2|H3|H4|H5|H6|LI|DIV|BLOCKQUOTE|PRE)$/;

    function caretBlock(body) {
      var sel = window.getSelection();
      if (!sel || !sel.rangeCount) return body.firstElementChild || body;
      var node = sel.getRangeAt(0).startContainer;
      var el = node.nodeType === 1 ? node : node.parentElement;
      while (el && el !== body && !BLOCK_TAGS.test(el.tagName)) el = el.parentElement;
      return (el && el !== body) ? el : (body.firstElementChild || body);
    }

    function refreshState() {
      var body = findBody(root);
      if (!body) return;
      var sel = window.getSelection();
      //  Only when the caret is actually inside the body THIS toolbar drives.
      if (!sel || !sel.anchorNode || !body.contains(sel.anchorNode)) return;
      var blockTag = "";
      try { blockTag = (document.queryCommandValue("formatBlock") || "").toLowerCase(); } catch (e) {}
      var block = caretBlock(body);
      var align = block ? getComputedStyle(block).textAlign : "";
      root.querySelectorAll("button[data-cmd]").forEach(function (btn) {
        var cmd = btn.dataset.cmd;
        var active = false;
        if (STATE_CMDS[cmd]) {
          try { active = document.queryCommandState(cmd); } catch (e) {}
        } else if (cmd === "formatBlock") {
          active = blockTag === (btn.dataset.value || "").toLowerCase();
        } else if (cmd === "createLink") {
          //  Lit when the caret is inside a link -- the cue that clicking
          //  will EDIT it, not make a new one.
          active = !!_linkFromSelection();
        } else if (ALIGN_STATE[cmd]) {
          var want = ALIGN_STATE[cmd];
          active = align === want || (want === "left" && (align === "start" || align === "" || align === "-moz-left"));
        }
        btn.classList.toggle("is-active", !!active);
      });
    }
    root.__cmsRefreshState = refreshState;
    document.addEventListener("selectionchange", refreshState);
    root.addEventListener("mouseup", refreshState);
    root.addEventListener("keyup", refreshState);

    //  A picture inside the words. Shared for the same reason the
    //  commands are: the live page and an admin form upload to the same
    //  route and insert at the same caret; only "what now" differs.
    root.querySelectorAll(".cms-insert-image-btn").forEach(function (btn) {
      var input = root.querySelector(".cms-insert-image-input");
      if (!input) return;
      var savedRange = null;
      btn.addEventListener("mousedown", function () {
        var sel = window.getSelection();
        if (sel.rangeCount) savedRange = sel.getRangeAt(0).cloneRange();
      });
      btn.addEventListener("click", async function () {
        //  The Media Library first, with Upload inside it -- not a file
        //  dialog. This button went straight to `input.click()`, so the
        //  only way to put a picture in a post or a page was to find the
        //  file again on disk: no way to reuse one already uploaded, and
        //  no sight of what the site already has. The picker offers both
        //  routes and finishes the same way whichever is used.
        if (window.cmsImagePicker) {
          var chosen = await window.cmsImagePicker.open();
          if (!chosen) return;
          if (onImage) {
            onImage(chosen);
          } else {
            if (savedRange) {
              var sel = window.getSelection();
              sel.removeAllRanges();
              sel.addRange(savedRange);
            }
            document.execCommand("insertImage", false, chosen);
          }
          afterCommand(findBody(btn));
          return;
        }
        //  No picker loaded on this page: the file dialog still works.
        input.click();
      });
      input.addEventListener("change", function () {
        var file = input.files[0];
        if (!file) return;
        var data = new FormData();
        data.set("image", file);
        fetch("/admin/upload-image", { method: "POST", body: data, credentials: "same-origin" })
          .then(function (res) { return res.json().then(function (j) { return { ok: res.ok, j: j }; }); })
          .then(function (r) {
            if (r.ok && r.j.url) {
              //  A caller can say what a picture is FOR. The blog editor
              //  makes it the post's own picture rather than one inside
              //  the words; without a hook it goes in at the caret, which
              //  is what a page needs.
              if (onImage) {
                onImage(r.j.url);
                return;
              }
              //  The click moved focus off the words, so the caret has to
              //  be put back before anything can be inserted at it.
              var sel = window.getSelection();
              sel.removeAllRanges();
              if (savedRange) sel.addRange(savedRange);
              document.execCommand("insertImage", false, r.j.url);
              afterCommand(findBody(btn));
              say("Image inserted");
            } else {
              say((r.j && r.j.error) || "Upload failed");
            }
          })
          .catch(function () { say("Upload failed — check your connection"); })
          .then(function () { input.value = ""; });
      });
    });

    //  Back to whatever the theme would apply, rather than being stuck
    //  with a colour somebody picked once.
    root.querySelectorAll(".cms-color-reset").forEach(function (btn) {
      btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
      btn.addEventListener("click", function () {
        var cmd = btn.dataset.resetCmd;
        run(cmd, cmd === "hiliteColor" ? "transparent" : "inherit");
        afterCommand(findBody(btn));
      });
    });
  }

  window.cmsWysiwyg = { bindToolbar: bindToolbar, run: run };
})();
