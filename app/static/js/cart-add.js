// Adding to the basket without leaving the shop.
//
// The form posts and the server answers either way -- this only upgrades
// it so the page does not navigate: the item goes in, the header count
// changes, and the button says so for a moment. Without a script running,
// the same form posts normally and the server sends the shopper back to
// where they were, so nothing here is load-bearing.
(function () {
  "use strict";

  function setCount(n) {
    document.querySelectorAll(".cms-basket-count").forEach(function (el) {
      el.textContent = n;
      if (n > 0) { el.removeAttribute("data-empty"); } else { el.setAttribute("data-empty", "1"); }
    });
    //  A basket set to hide itself while empty has to appear the moment
    //  it is not.
    document.querySelectorAll(".cms-basket[data-hide-empty='1']").forEach(function (el) {
      el.hidden = n === 0;
    });
  }

  function flash(btn, text, ok) {
    if (btn.dataset.busy === "1") return;
    var original = btn.textContent;
    btn.dataset.busy = "1";
    btn.textContent = text;
    btn.classList.add(ok ? "is-added" : "is-refused");
    window.setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("is-added", "is-refused");
      btn.dataset.busy = "0";
    }, 1600);
  }

  document.querySelectorAll('form[action$="/cart/add"]').forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var btn = form.querySelector("button[type=submit], button:not([type])");
      if (!btn) return;                       // nothing to give feedback on; let it post
      e.preventDefault();
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            setCount(data.count);
            flash(btn, "Added \u2713", true);
          } else {
            flash(btn, data.message || "Couldn't add that", false);
          }
        })
        .catch(function () {
          //  If the request itself failed, fall back to the plain form
          //  rather than swallowing the click.
          form.submit();
        });
    });
  });
})();
