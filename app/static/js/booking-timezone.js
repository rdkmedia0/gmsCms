// Book in the visitor's own timezone, not the server's.
//
// Times arrive already formatted for whatever zone was asked for, so the
// page reloads once with the real zone if the guess was wrong. Without
// this, someone in another country is offered slots that look like their
// working day but are not.
(function () {
  "use strict";
  var tz;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch (e) {
    return;
  }
  if (!tz) return;

  // Every booking form carries it, so the slot that gets booked is the
  // one the visitor actually clicked.
  document.querySelectorAll(".cms-tz-field").forEach(function (field) {
    field.value = tz;
  });

  // The slot list itself was rendered for whatever zone the URL asked
  // for. If that is not this visitor's, reload once with the right one.
  var params = new URLSearchParams(location.search);
  if (params.get("tz") !== tz && document.querySelector(".cms-slot-grid")) {
    params.set("tz", tz);
    location.replace(location.pathname + "?" + params.toString());
  }
})();
