// Shows one day's times at a time.
//
// Progressive enhancement on purpose: without this file every day's times
// are already on the page and the day cells are plain anchors to them, so
// the calendar still works. All this adds is not having to scroll.
(function () {
  "use strict";
  var cal = document.querySelector(".cms-cal");
  var panels = Array.prototype.slice.call(document.querySelectorAll(".cms-day-panel"));
  if (!cal || !panels.length) return;

  function show(day) {
    panels.forEach(function (panel) {
      panel.hidden = panel.dataset.day !== day;
    });
    cal.querySelectorAll(".cms-cal-day").forEach(function (cell) {
      cell.classList.toggle("is-chosen", cell.dataset.day === day);
    });
  }

  cal.addEventListener("click", function (e) {
    var cell = e.target.closest(".cms-cal-day[data-day]");
    if (!cell) return;
    e.preventDefault();
    show(cell.dataset.day);
    var panel = document.querySelector('.cms-day-panel[data-day="' + cell.dataset.day + '"]');
    if (panel) panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });

  // Open on the first day that has anything free, so the page never
  // greets someone with an empty space where the times should be.
  show(panels[0].dataset.day);
})();
