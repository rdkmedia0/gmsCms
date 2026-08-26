// Resend a buyer's access link.
//
// Reports inline rather than by toast: the owner is usually doing this
// while someone waits on the phone, and "did that work?" needs to stay on
// screen.
(function () {
  "use strict";
  document.querySelectorAll(".cms-resend-order").forEach(function (btn) {
    var result = btn.closest(".integration-actions").nextElementSibling;
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
