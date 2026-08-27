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
