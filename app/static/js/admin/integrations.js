// Integrations panel: test a connection, and confirm a disconnect.
//
// One file per admin template — admin/base.html loads no
// scripts of its own, so each page brings what it needs.
(function () {
  "use strict";

  // The result IS the point of the button, so it lands inline beside it and
  // stays there. A toast would vanish before anyone finished reading which
  // account the key reached.
  document.querySelectorAll(".cms-test-integration").forEach(function (btn) {
    var result = btn.closest("form").querySelector(".integration-result");
    btn.addEventListener("click", async function () {
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Testing\u2026";
      result.hidden = true;
      try {
        var res = await fetch(btn.dataset.url, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
        });
        var data = await res.json();
        result.textContent = data.message;
        result.className = "integration-result " + (data.ok ? "ok" : "bad");
      } catch (e) {
        result.textContent = "Couldn't reach this site's own server to run the test.";
        result.className = "integration-result bad";
      }
      result.hidden = false;
      btn.textContent = original;
      btn.disabled = false;
    });
  });

  // Creating the webhook is the one action here that changes something in
  // the provider's account, so it reports back in the same inline place a
  // connection test does rather than silently succeeding.
  document.querySelectorAll(".cms-create-webhook").forEach(function (btn) {
    var card = btn.closest(".card");
    var result = card.querySelector(".integration-result[hidden]") || card.querySelector(".integration-result");
    btn.addEventListener("click", async function () {
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Creating…";
      var body = new FormData();
      body.append("webhook_url", card.querySelector("#webhook_url").value);
      try {
        var res = await fetch(btn.dataset.url, { method: "POST", body: body, headers: { "X-Inline-Edit": "1" } });
        var data = await res.json();
        result.textContent = data.message;
        result.className = "integration-result " + (data.ok ? "ok" : "bad");
        result.hidden = false;
      } catch (e) {
        result.textContent = "Couldn't reach this site's own server.";
        result.className = "integration-result bad";
        result.hidden = false;
      }
      btn.textContent = original;
      btn.disabled = false;
    });
  });

  // Sync is the pull counterpart to the webhook's push. Same inline
  // reporting: an admin needs to see how many orders it actually found.
  document.querySelectorAll(".cms-sync-orders").forEach(function (btn) {
    var result = btn.closest(".integration-actions").nextElementSibling;
    btn.addEventListener("click", async function () {
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Syncing…";
      try {
        var res = await fetch(btn.dataset.url, { method: "POST", headers: { "X-Inline-Edit": "1" } });
        var data = await res.json();
        result.textContent = data.message;
        result.className = "integration-result " + (data.ok ? "ok" : "bad");
        result.hidden = false;
      } catch (e) {
        result.textContent = "Couldn't reach this site's own server.";
        result.className = "integration-result bad";
        result.hidden = false;
      }
      btn.textContent = original;
      btn.disabled = false;
    });
  });

  //  Disconnecting drops a stored key that cannot be read back, so it
  //  asks first — but the asking is confirm.js's job now, from the
  //  form's own data-confirm. This file had its own copy of that loop.
})();
