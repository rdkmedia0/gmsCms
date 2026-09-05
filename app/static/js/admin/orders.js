// Resend a buyer's access link.
//
// Reports inline rather than by toast: the owner is usually doing this
// while someone waits on the phone, and "did that work?" needs to stay on
// screen.
(function () {
  "use strict";
  document.querySelectorAll(".cms-resend-order").forEach(function (btn) {
    var result = btn.closest("[data-order-row]").querySelector(".integration-result");
    btn.addEventListener("click", async function () {
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Sending\u2026";
      try {
        var res = await fetch(btn.dataset.url, { method: "POST", headers: { "X-Inline-Edit": "1" } });
        var data = await res.json();
        result.textContent = data.message;
        result.className = "integration-result " + (data.ok ? "ok" : "bad");
      } catch (e) {
        result.textContent = "Couldn't reach this site's own server.";
        result.className = "integration-result bad";
      }
      result.hidden = false;
      btn.textContent = original;
      btn.disabled = false;
    });
  });
})();

//  Taking a buyer's own password off their purchases page, when they have
//  forgotten it. Confirmed first: it is their lock, not the owner's.
document.querySelectorAll(".cms-clear-page-password").forEach(function (btn) {
  btn.addEventListener("click", async function () {
    var { confirmed } = await window.cmsModal({
      message: "Remove this buyer's password from their purchases page? " +
        "Their link will open it again on its own, and nothing they bought changes.",
      confirmLabel: "Remove it",
    });
    if (!confirmed) return;
    var result = btn.closest("[data-order-row]").querySelector(".integration-result");
    btn.disabled = true;
    try {
      var resp = await fetch(btn.dataset.url, {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      var data = await resp.json();
      result.textContent = data.ok ? data.message : data.error;
      result.hidden = false;
      if (data.ok) btn.remove();
    } catch (e) {
      result.textContent = "Couldn't do that just now.";
      result.hidden = false;
      btn.disabled = false;
    }
  });
});

//  Sync + keep-from. A blank date just pulls (nothing dropped); a date set
//  means the sync will prune this site's copy before it, so confirm THAT
//  case -- pruning loses the local fulfilment note, though Stripe keeps the
//  payment. See commerce_orders_sync.
document.querySelectorAll(".orders-sync-form").forEach(function (form) {
  var btn = form.querySelector(".orders-sync-btn");
  var date = form.querySelector("#sync_from");
  if (!btn || !date) return;
  form.addEventListener("submit", async function (e) {
    if (!date.value) return;  // no window, no prune -- just sync
    if (!window.cmsModal) return;
    e.preventDefault();
    var res = await window.cmsModal({
      message: btn.dataset.pruneWarning,
      confirmLabel: "Sync and drop older",
    });
    if (res.confirmed) form.submit();
  });
});
