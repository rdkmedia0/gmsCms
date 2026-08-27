// The email, beside the words, while they are being written.
//
// Writing a newsletter into a column of text boxes and pressing Preview
// afterwards is guessing with an extra step: the whole question is what
// it will look like. This posts the FORM (not what was last saved) to the
// preview route on every change and puts the answer in the frame, so the
// right-hand side is always what would go out if you sent it now.
//
// Nothing is stored by any of this — the route renders what it is given
// and saves nothing, so a half-written sentence never becomes the saved
// copy.
(function () {
  "use strict";
  var form = document.querySelector(".cms-issue-fields");
  var frame = document.querySelector(".cms-issue-preview-frame");
  var state = document.querySelector(".cms-issue-preview-state");
  if (!form || !frame) return;
  var url = form.dataset.previewUrl;
  var timer = null;
  var inFlight = false;

  function say(text) { if (state) state.textContent = text; }

  function refresh() {
    if (inFlight) return;
    inFlight = true;
    say("Updating…");
    fetch(url, { method: "POST", body: new FormData(form), credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        //  srcdoc rather than a src: the answer is already here, and a
        //  second request would show a version one keystroke behind.
        frame.srcdoc = html;
        say(state ? state.dataset.idle : "");
      })
      .catch(function () { say("Couldn't refresh the preview"); })
      .then(function () { inFlight = false; });
  }

  //  Debounced: a preview that re-renders on every keystroke is a preview
  //  nobody can read while typing into it.
  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(refresh, 400);
  }

  form.addEventListener("input", schedule);
  form.addEventListener("change", schedule);
  refresh();
})();
