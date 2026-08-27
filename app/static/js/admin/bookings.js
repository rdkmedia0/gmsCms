// Cancelling a booking from the Bookings page.
//
// Goes through Cal.com rather than any calendar the meeting was mirrored
// into, because that is the only cancellation that counts — see the
// route's own docstring.
(function () {
  "use strict";
  document.querySelectorAll(".cms-cancel-booking").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var { confirmed } = await window.cmsModal({
        message: "Cancel the booking on " + btn.dataset.when +
          "? Cal.com will email everyone, and the session goes back to whoever paid for it.",
        //  The dismiss button already says "Cancel", so a confirm also
        //  called "Cancel booking" put two opposite actions a word apart.
        confirmLabel: "Yes, cancel it",
      });
      if (!confirmed) return;
      var result = btn.closest(".card").querySelector(".integration-result");
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
        result.textContent = "Couldn't reach Cal.com just now.";
        result.hidden = false;
        btn.disabled = false;
      }
    });
  });
})();
