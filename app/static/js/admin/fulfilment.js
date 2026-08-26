// Show only the fields that belong to the chosen outcome.
//
// The alternative — every field visible at once — asks the owner to
// understand a data model before they can sell a thing. One question,
// then only what that answer needs.
(function () {
  "use strict";
  document.querySelectorAll(".fulfilment-form").forEach(function (form) {
    var select = form.querySelector(".fulfilment-kind");
    var groups = form.querySelectorAll(".fulfilment-fields");
    function sync() {
      groups.forEach(function (group) {
        var off = group.dataset.for !== select.value;
        group.hidden = off;
        // Hidden is not the same as absent: two outcomes both have a
        // "ref" and a "quantity", so leaving the unused one enabled
        // would post the wrong answer alongside the right one.
        group.querySelectorAll("input, select").forEach(function (field) {
          field.disabled = off;
        });
      });
    }
    select.addEventListener("change", sync);
    sync();
  });
})();
