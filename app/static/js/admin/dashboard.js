// Dashboard-only widgets: the favicon upload button (opens a hidden file
// input, auto-submits its form once a file is chosen) and the default
// section width select (shows/hides the companion % input for "Custom").
(function () {
  var trigger = document.querySelector(".favicon-upload-trigger");
  var input = document.querySelector(".favicon-upload-input");
  if (trigger && input) {
    trigger.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      if (input.files.length) input.closest("form").submit();
    });
  }

  //  Importing a template that is already installed is a question, not a
  //  silent second copy. The server answers 409 with what it found; the
  //  file is still in the input, so the same upload is simply sent again
  //  with the answer attached — nothing is stashed on the server waiting
  //  for a reply that may never come.
  var importForm = document.querySelector(".cms-import-package-form");
  if (importForm && window.cmsModal) {
    importForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var send = async function (choice) {
        var data = new FormData(importForm);
        if (choice) data.set("on_conflict", choice);
        return fetch(importForm.action, {
          method: "POST", body: data, credentials: "same-origin",
          headers: { "X-Inline-Edit": "1" },
        });
      };
      var res = await send("");
      if (res.status === 409) {
        var info = await res.json();
        var message = '"' + info.name + '" is already installed. Overwrite keeps one template, '
          + 'putting these files in place of the ones with the same name. Keep both leaves the '
          + 'original alone and installs this one beside it, under its own name.';
        if (!info.can_replace) {
          message = '"' + info.name + '" is built in and is reinstalled every time the site '
            + 'restarts, so it cannot be overwritten — an overwrite would last until the next '
            + 'restart and then be gone. You can keep both: this one installs beside it, under '
            + 'its own name.';
        }
        var choice = await window.cmsModal({
          message: message,
          confirmLabel: "Overwrite",
          showConfirm: info.can_replace,
          altLabel: "Keep both",
          danger: true,
        });
        if (!choice.confirmed && !choice.alt) return;
        res = await send(choice.confirmed ? "replace" : "keep-both");
      }
      window.location = res.redirected ? res.url : "/admin/";
    });
  }

  var widthSelect = document.getElementById("default-width-select");
  var widthPctInput = document.getElementById("default-width-pct-input");
  if (widthSelect && widthPctInput) {
    widthSelect.addEventListener("change", function () {
      widthPctInput.hidden = widthSelect.value !== "custom";
    });
  }
})();
