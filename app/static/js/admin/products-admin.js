// The Products screen's catalogue: search, a list/gallery toggle
// (remembered per browser), and click-to-open ONE product's editor at a
// time -- so the page stays short however many products there are, instead
// of every product being a full open form stacked down the screen.
(function () {
  "use strict";

  var grid = document.getElementById("products-grid");
  if (!grid) return;

  // ---- List / Gallery, remembered ----
  var KEY = "cms-products-view";
  var toggles = document.querySelectorAll("[data-products-view]");

  function setView(view) {
    if (view !== "gallery") view = "list";
    grid.setAttribute("data-view", view);
    toggles.forEach(function (b) {
      b.classList.toggle("is-active", b.dataset.productsView === view);
    });
    try { localStorage.setItem(KEY, view); } catch (e) { /* private mode */ }
  }
  toggles.forEach(function (b) {
    b.addEventListener("click", function () { setView(b.dataset.productsView); });
  });
  var saved = "list";
  try { saved = localStorage.getItem(KEY) || "list"; } catch (e) { /* ignore */ }
  setView(saved);

  // ---- Open one product's editor at a time ----
  function closeAll() {
    grid.querySelectorAll(".product-item").forEach(function (it) {
      it.querySelector(".product-detail").hidden = true;
      it.querySelector(".product-summary").setAttribute("aria-expanded", "false");
      it.classList.remove("is-open");
    });
  }
  grid.querySelectorAll(".product-summary").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var item = btn.closest(".product-item");
      var detail = item.querySelector(".product-detail");
      var wasOpen = !detail.hidden;
      closeAll();
      if (!wasOpen) {
        detail.hidden = false;
        btn.setAttribute("aria-expanded", "true");
        item.classList.add("is-open");
      }
    });
  });

  // ---- Search by name ----
  var search = document.getElementById("products-search");
  var none = document.querySelector(".products-none-match");
  if (search) {
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      var shown = 0;
      grid.querySelectorAll(".product-item").forEach(function (it) {
        var match = !q || (it.dataset.name || "").indexOf(q) !== -1;
        it.hidden = !match;
        if (match) { shown++; }
      });
      if (none) { none.hidden = shown !== 0; }
    });
  }
})();
