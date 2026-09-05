// Delivery services: add and remove weight-band rows in a service's rate
// table. The rows are plain inputs named band_up_to / band_amount, so the
// whole table posts as two parallel lists the save route zips back
// together -- no per-row form, no ids to keep in step. The blank row this
// clones lives in a <template> on the page.
(function () {
  "use strict";

  var tpl = document.getElementById("shipping-band-template");

  function newRow() {
    if (!tpl) return null;
    var frag = tpl.content.cloneNode(true);
    return frag.firstElementChild;
  }

  function wireRemove(row) {
    var btn = row.querySelector(".shipping-band-remove");
    if (btn) {
      btn.addEventListener("click", function () { row.remove(); });
    }
  }

  document.querySelectorAll(".shipping-band").forEach(wireRemove);

  document.querySelectorAll(".shipping-band-add").forEach(function (add) {
    add.addEventListener("click", function () {
      var body = add.closest("form").querySelector(".shipping-bands-body");
      var row = newRow();
      if (body && row) {
        body.appendChild(row);
        wireRemove(row);
        var first = row.querySelector("input");
        if (first) first.focus();
      }
    });
  });
})();
