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

  // ---- Services as expandable rows: open one editor at a time ----
  var grid = document.getElementById("shipping-grid");
  if (grid) {
    var closeAll = function () {
      grid.querySelectorAll(".product-item").forEach(function (it) {
        var d = it.querySelector(".product-detail");
        if (d) d.hidden = true;
        it.querySelector(".product-summary").setAttribute("aria-expanded", "false");
        it.classList.remove("is-open");
      });
    };
    grid.querySelectorAll(".product-summary").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var item = btn.closest(".product-item");
        var detail = item.querySelector(".product-detail");
        var wasOpen = detail && !detail.hidden;
        closeAll();
        if (detail && !wasOpen) {
          detail.hidden = false;
          btn.setAttribute("aria-expanded", "true");
          item.classList.add("is-open");
        }
      });
    });
  }

  // ---- The ＋ Add delivery service panel: hidden until asked for ----
  var addToggle = document.getElementById("shipping-add-toggle");
  var addPanel = document.getElementById("shipping-add-panel");
  if (addToggle && addPanel) {
    addToggle.addEventListener("click", function () {
      var open = addPanel.hidden;
      addPanel.hidden = !open;
      addToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        var first = addPanel.querySelector("input, select, textarea");
        if (first) first.focus();
      }
    });
  }
})();
