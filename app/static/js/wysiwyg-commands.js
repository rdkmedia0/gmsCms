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

  function bindToolbar(root, options) {
    var findBody = options.findBody;
    var afterCommand = options.afterCommand || function () {};
    var askForLink = options.askForLink || function (done) {
      var url = window.prompt("Link to which web address?", "https://");
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
        if (cmd === "createLink") {
          askForLink(function (url) {
            if (url) {
              if (!(onLinkImage && onLinkImage(body, url))) {
                document.execCommand("createLink", false, url);
              }
            }
            afterCommand(body);
          }, body);
          return;
        }
        run(cmd, value);
        afterCommand(body);
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
