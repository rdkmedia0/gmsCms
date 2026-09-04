// Drive the site translation from the Languages screen.
//
// The translation itself runs in a SERVER thread (see languages_screen /
// _spawn_translation_worker): a whole-site run is minutes of slow provider
// calls, so holding it in the request timed out and driving it from the
// browser meant a refresh killed it and the progress was a guess. Here the
// screen only ever STARTS a run and POLLS its progress -- and the progress
// is the true per-language count read from the cache, not anything the run
// says about itself. Because the run is server-side, a refresh loses
// nothing: on load we ask the server if one is going and pick reporting
// straight back up.
//
// The forms are real, so with no JavaScript "Translate the site" still
// starts the run (and the flash tells you to reload for progress).
(function () {
  "use strict";
  var table = document.getElementById("cms-translate-table");
  if (!table) return;
  var progress = document.querySelector(".cms-translate-progress");
  var cancelBtn = document.querySelector(".cms-translate-cancel");
  var cancelForm = document.querySelector(".cms-translate-cancel-form");
  var statusUrl = table.getAttribute("data-status-url");
  var startUrl = window.location.pathname;
  var polling = false;

  function say(msg) {
    if (!progress) return;
    progress.hidden = false;
    progress.textContent = msg;
  }
  function showCancel(on) { if (cancelBtn) cancelBtn.hidden = !on; }
  function setBusy(busy) {
    var btns = document.querySelectorAll(".cms-translate-one, .cms-translate-all");
    Array.prototype.forEach.call(btns, function (b) { b.disabled = busy; });
  }
  function applyStatus(data) {
    var langs = (data.status && data.status.languages) || [];
    var totalDone = 0, total = 0;
    langs.forEach(function (l) {
      totalDone += l.done; total += l.total;
      var row = table.querySelector('tr[data-lang="' + l.code + '"]');
      if (!row) return;
      var pct = l.total ? Math.round(100 * l.done / l.total) : 0;
      var fill = row.querySelector(".cms-lang-bar-fill");
      if (fill) fill.style.width = pct + "%";
      var count = row.querySelector(".cms-lang-count");
      if (count) count.textContent = l.done + " / " + l.total;
      var tick = row.querySelector(".cms-lang-tick");
      if (tick) tick.hidden = !l.complete;
      var btn = row.querySelector(".cms-translate-one");
      if (btn) btn.textContent = l.complete ? "Re-translate" : (l.done > 0 ? "Retry" : "Translate");
      row.classList.toggle("cms-lang-failed", !l.complete && l.total > 0 && l.done < l.total);
    });
    return { active: data.active, error: data.error, totalDone: totalDone, total: total };
  }
  function poll() {
    fetch(statusUrl, { headers: { "X-Requested-With": "cms-translate" }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var s = applyStatus(data);
        if (s.active) {
          setBusy(true);
          showCancel(true);
          say("Translating… " + s.totalDone + " / " + s.total
            + " — this runs on the server, so you can leave this page and come back.");
          setTimeout(poll, 3000);
        } else {
          setBusy(false);
          showCancel(false);
          polling = false;
          if (s.error) say("Stopped: " + s.error + " — press Translate to continue.");
          else if (s.total && s.totalDone >= s.total) say("All languages fully translated.");
          else if (s.total) say("Paused at " + s.totalDone + " / " + s.total
            + " — press Retry on any unfinished language, or Translate to continue.");
          else say("");
        }
      })
      .catch(function () { polling = false; setBusy(false); });
  }
  function startPolling() { if (!polling) { polling = true; poll(); } }

  function start(body) {
    setBusy(true);
    showCancel(true);
    say("Starting…");
    fetch(startUrl, {
      method: "POST",
      headers: { "X-Requested-With": "cms-translate", "Content-Type": "application/x-www-form-urlencoded" },
      body: body, credentials: "same-origin",
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.ok === false) { setBusy(false); say(data.error || "Couldn't start."); return; }
        startPolling();
      })
      .catch(function () { setBusy(false); say("Couldn't start — please try again."); });
  }

  var allForm = document.querySelector(".cms-translate-all-form");
  if (allForm) allForm.addEventListener("submit", function (e) {
    e.preventDefault();
    start("action=translate");
  });
  if (cancelForm) cancelForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (cancelBtn) cancelBtn.disabled = true;
    say("Cancelling — it stops after the current item…");
    fetch(startUrl, {
      method: "POST",
      headers: { "X-Requested-With": "cms-translate", "Content-Type": "application/x-www-form-urlencoded" },
      body: "action=cancel", credentials: "same-origin",
    }).then(function () {
      if (cancelBtn) cancelBtn.disabled = false;
      startPolling();  // the state flips to idle once the worker checks the flag
    }).catch(function () { if (cancelBtn) cancelBtn.disabled = false; });
  });
  table.addEventListener("submit", function (e) {
    var form = e.target.closest && e.target.closest(".cms-translate-one-form");
    if (!form) return;
    e.preventDefault();
    var lang = form.querySelector('input[name="lang"]').value;
    start("action=translate_one&lang=" + encodeURIComponent(lang));
  });

  //  On load, ask whether a run is already going (e.g. after a refresh) and
  //  resume reporting if so -- the run itself never stopped.
  fetch(statusUrl, { headers: { "X-Requested-With": "cms-translate" }, credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (data) { if (applyStatus(data).active) startPolling(); })
    .catch(function () {});
})();
