// Times, on the clock of the person reading them.
//
// The database stores UTC, because a time written in a zone that changes
// twice a year is a time that moves. The screen has to show the owner's
// own clock, because that is the clock they set it by -- and the browser
// is the only thing that knows which one that is.
//
// Two jobs, both tiny, both needed on more than one screen (the compose
// bar and the Newsletters list), which is why they are here rather than
// in either one:
//
//   [data-tz-offset]  a hidden field that tells the server which clock a
//                     typed time was typed on
//   [data-local-time] an element holding a UTC stamp, shown as local
//
// The offset is re-read on every submit rather than once at load: a page
// left open across a daylight-saving change would otherwise schedule an
// hour out.
(function () {
  "use strict";

  function stampOffsets(root) {
    var minutes = String(new Date().getTimezoneOffset());
    (root || document).querySelectorAll("[data-tz-offset]").forEach(function (field) {
      field.value = minutes;
    });
  }

  function showLocalTimes(root) {
    (root || document).querySelectorAll("[data-local-time]").forEach(function (el) {
      //  "2026-08-27 20:44:09" is UTC; make that explicit before parsing,
      //  or a browser reads it as local and shows the wrong hour.
      var raw = (el.dataset.localTime || "").trim().replace(" ", "T");
      if (raw && !/[Zz]$|[+-]\d\d:?\d\d$/.test(raw)) raw += "Z";
      var when = new Date(raw);
      if (!isNaN(when)) {
        el.textContent = when.toLocaleString();
        //  The exact stamp stays reachable, since "in your time" and
        //  "what is actually stored" are both worth being able to see.
        if (!el.title) el.title = el.dataset.localTime + " UTC";
      }
    });
  }

  //  A `datetime-local` field pre-filled from a stored UTC stamp.
  function fillLocalField(field, utc) {
    if (!utc) return;
    var when = new Date(utc.trim().replace(" ", "T") + "Z");
    if (isNaN(when)) return;
    var pad = function (n) { return String(n).padStart(2, "0"); };
    field.value = when.getFullYear() + "-" + pad(when.getMonth() + 1) + "-"
      + pad(when.getDate()) + "T" + pad(when.getHours()) + ":" + pad(when.getMinutes());
  }

  function init() {
    stampOffsets();
    showLocalTimes();
    document.querySelectorAll("[data-scheduled-utc]").forEach(function (field) {
      fillLocalField(field, field.dataset.scheduledUtc);
    });
    //  Every form, not just the one being submitted: which one it will be
    //  is not known until it happens.
    document.addEventListener("submit", function () { stampOffsets(); }, true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.cmsLocalTime = { stampOffsets: stampOffsets, showLocalTimes: showLocalTimes,
                          fillLocalField: fillLocalField };
})();
