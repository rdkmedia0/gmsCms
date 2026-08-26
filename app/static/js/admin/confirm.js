// Every action in the admin says what it is about to do, and waits.
//
// An icon is quicker to read than a word once you know it, and says
// nothing at all until you do. A tooltip only helps somebody who thinks
// to hover, and on a phone there is no hover. So the sentence the icon
// replaced is not lost -- it is asked, at the moment it matters, with an
// OK and a Cancel.
//
// This is the ONE implementation. There were three: a native confirm()
// spelled out in an onsubmit attribute (which some embedded and preview
// contexts silently refuse, so the action just looks dead), this file's
// [data-confirm] on a button, and integrations.js's own .cms-confirm-form
// on a form. They had drifted in wording, in what they did on Cancel, and
// in whether they worked at all. Put "data-confirm" on the thing that
// acts -- a button, a link, or a form -- and it is handled here.
//
// admin/base.html loads this on every admin screen, so a new action never
// has to remember to bring its own dialog.
(function () {
  "use strict";
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    var isForm = el.tagName === "FORM";
    el.addEventListener(isForm ? "submit" : "click", async function (e) {
      //  The second pass, after the answer was yes: let it through, and
      //  arm the question again for next time.
      if (el.dataset.confirmed === "1") { el.dataset.confirmed = ""; return; }
      e.preventDefault();
      var answer = await window.cmsModal({
        message: el.dataset.confirm,
        confirmLabel: el.dataset.confirmLabel || "OK",
        //  Red is for what cannot be taken back. Most of these can.
        danger: el.dataset.confirmDanger === "1",
      });
      if (!answer || !answer.confirmed) return;
      el.dataset.confirmed = "1";
      if (isForm) {
        if (el.requestSubmit) el.requestSubmit(); else el.submit();
      } else if (el.closest("form") && el.tagName === "BUTTON") {
        //  requestSubmit(button) and not submit(): the button's own name
        //  and value are part of what the form says, and submit() drops
        //  them.
        var form = el.closest("form");
        if (form.requestSubmit) form.requestSubmit(el); else form.submit();
      } else if (el.tagName === "A" && el.href) {
        if (el.target === "_blank") window.open(el.href, el.target);
        else window.location.href = el.href;
      } else {
        //  Anything else -- a button another script is listening to --
        //  gets its click back now that the answer is in.
        el.click();
      }
    });
  });
})();
