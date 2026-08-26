// The shared confirm/prompt modal (replaces native confirm()/prompt()) —
// a real DOM element, not a native browser dialog, which some embedded/
// preview contexts silently block or auto-dismiss with no visible dialog
// at all (confirm() then just always returns false, making every action
// look like it does nothing). Exposed as window.cmsModal so any other
// script on a page that includes partials/cms_modal.html can reuse it —
// currently inline-editor.js (the live-page editor) and
// static/js/admin/template-panel.js (Dashboard + the Theme & Layout dock
// panel).
(function () {
  "use strict";
  const backdrop = document.getElementById("cms-modal-backdrop");
  if (!backdrop) return; // this page didn't include partials/cms_modal.html

  const modalMessage = document.getElementById("cms-modal-message");
  const modalInput = document.getElementById("cms-modal-input");
  const modalCancel = document.getElementById("cms-modal-cancel");
  const modalConfirm = document.getElementById("cms-modal-confirm");
  const modalAlt = document.getElementById("cms-modal-alt");
  const modalCountLabel = document.getElementById("cms-modal-count-label");
  const modalCount = document.getElementById("cms-modal-count");
  const modalSnapshotLabel = document.getElementById("cms-modal-snapshot-label");
  const modalSnapshot = document.getElementById("cms-modal-snapshot");

  function cmsModal({ message, showInput = false, defaultValue = "", confirmLabel = "Confirm", danger = true, showCount = false, showSnapshotOption = false, altLabel = "", showConfirm = true }) {
    return new Promise((resolve) => {
      modalMessage.textContent = message;
      modalInput.hidden = !showInput;
      modalInput.value = defaultValue;
      if (modalCountLabel) {
        modalCountLabel.hidden = !showCount;
        if (showCount) modalCount.value = "1";
      }
      if (modalSnapshotLabel) {
        modalSnapshotLabel.hidden = !showSnapshotOption;
        if (showSnapshotOption) modalSnapshot.checked = false;
      }
      modalConfirm.textContent = confirmLabel;
      modalConfirm.classList.toggle("cms-danger", danger);
      //  A choice that cannot be taken is not offered. Showing it greyed
      //  out, or labelled with its own impossibility, just makes the
      //  reader work out why.
      modalConfirm.hidden = !showConfirm;
      if (modalAlt) {
        modalAlt.hidden = !altLabel;
        modalAlt.textContent = altLabel || "";
      }
      backdrop.hidden = false;
      if (showInput) setTimeout(() => modalInput.focus(), 0);

      function cleanup(result) {
        backdrop.hidden = true;
        modalConfirm.removeEventListener("click", onConfirm);
        modalCancel.removeEventListener("click", onCancel);
        if (modalAlt) modalAlt.removeEventListener("click", onAlt);
        backdrop.removeEventListener("click", onBackdrop);
        resolve(result);
      }
      function onConfirm() {
        cleanup({
          confirmed: true, value: modalInput.value, count: showCount ? parseInt(modalCount.value, 10) : 1,
          saveSnapshot: showSnapshotOption ? modalSnapshot.checked : false,
        });
      }
      function onCancel() { cleanup({ confirmed: false, alt: false, value: null, count: 1, saveSnapshot: false }); }
      function onAlt() { cleanup({ confirmed: false, alt: true, value: null, count: 1, saveSnapshot: false }); }
      function onBackdrop(e) { if (e.target === backdrop) onCancel(); }

      modalConfirm.addEventListener("click", onConfirm);
      modalCancel.addEventListener("click", onCancel);
      if (modalAlt) modalAlt.addEventListener("click", onAlt);
      backdrop.addEventListener("click", onBackdrop);
    });
  }

  window.cmsModal = cmsModal;
})();
