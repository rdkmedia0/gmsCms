// Show only the fields that belong to the chosen delivery type.
//
// The type dropdown lives IN the product form now (Add and Edit), so this
// keys off the .fulfilment-kind select itself and drives the field groups
// within whatever form holds it -- not a dedicated fulfilment form. The
// alternative — every field visible at once — asks the owner to understand
// a data model before they can sell a thing. One question, then only what
// that answer needs.
(function () {
  "use strict";
  document.querySelectorAll(".fulfilment-kind").forEach(function (select) {
    var form = select.closest("form");
    if (!form) return;
    var groups = form.querySelectorAll(".fulfilment-fields");
    function sync() {
      groups.forEach(function (group) {
        var off = group.dataset.for !== select.value;
        group.hidden = off;
        // Hidden is not the same as absent: two types both have a "ref"
        // and a "quantity", so leaving the unused one enabled would post
        // the wrong answer alongside the right one.
        group.querySelectorAll("input, select").forEach(function (field) {
          field.disabled = off;
        });
      });
    }
    select.addEventListener("change", sync);
    sync();
  });
})();
