/*  Choosing WHEN, from the schedules that have been named.

    One file, used by the newsletter editor and by the blog post editor.
    It was written inside newsletter-editor.js, which was right while a
    schedule was a thing only a newsletter had -- a post can be put on
    one now, and the second copy would have been the place the two came
    to disagree about which dates a schedule produces.

    What it does is small and the reasons are not:

      * the dates are OFFERED, not decided. Booking a schedule's next
        occurrence silently was the app choosing the date -- "the first
        Monday" might be tomorrow, and the thing being scheduled might
        not be ready by tomorrow.

      * a list rather than a calendar, because only certain dates are
        valid. A date picker cannot express "the first Monday of the
        month", so it would either allow dates the schedule does not
        produce or quietly move the one that was picked.

      * drawn in the reader's own clock, which is the clock the owner
        typed the schedule in. A UTC timestamp in a list of dates
        somebody is choosing between is a sum they should not have to do.

      * the date box is shown, never REQUIRED. These are forms with
        several buttons on them, so a required field refuses all of them
        until a date is typed -- for actions that have nothing to do with
        scheduling. The server already refuses a schedule with no time,
        and says which of the two is missing; the rule belongs to the
        action, not to the form.
*/
window.cmsSchedulePicker = function (form, datesElementId) {
  var pick = form.querySelector("[data-schedule-pick]");
  var when = form.querySelector("[data-send-at]");
  var date = form.querySelector("[data-schedule-date]");
  if (!pick || !when) return;

  var DATES = {};
  try {
    var block = document.getElementById(datesElementId || "cms-schedule-dates");
    (JSON.parse((block && block.textContent) || "[]") || []).forEach(function (s) {
      DATES[s.name] = s.dates || [];
    });
  } catch (e) {
    DATES = {};
  }

  function readable(utc) {
    var at = new Date(utc.replace(" ", "T") + "Z");
    if (isNaN(at.getTime())) return utc;
    return at.toLocaleString(undefined, {
      weekday: "short", day: "numeric", month: "short",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function fill(name) {
    if (!date) return;
    var list = DATES[name] || [];
    date.innerHTML = "";
    list.forEach(function (d) {
      var option = document.createElement("option");
      option.value = d.utc;
      option.textContent = readable(d.utc);
      date.appendChild(option);
    });
    date.hidden = !list.length;
    date.disabled = !list.length;
  }

  function show() {
    //  "A time I choose" is the one-off, and only then is a date box any
    //  use. Hiding it the rest of the time is the whole point of having
    //  named the schedules.
    var custom = pick.value === "";
    when.hidden = !custom;
    if (date) {
      date.hidden = custom;
      date.disabled = custom;
      if (!custom) fill(pick.value);
    }
  }

  pick.addEventListener("change", show);
  show();
};
