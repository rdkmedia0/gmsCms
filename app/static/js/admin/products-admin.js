// The Products screen: search, a list/gallery toggle (remembered per
// browser), click-to-open ONE product's editor at a time, an "add"
// panel behind the ＋ button, an on-sale tick that submits itself, and
// the three-way picture chooser (upload / Media Library / describe) each
// product form carries. Keeping the page short however many you sell.
(function () {
  "use strict";

  var grid = document.getElementById("products-grid");

  // ---- List / Gallery, remembered ----
  if (grid) {
    var KEY = "cms-products-view";
    var toggles = document.querySelectorAll("[data-products-view]");
    var setView = function (view) {
      if (view !== "gallery") view = "list";
      grid.setAttribute("data-view", view);
      toggles.forEach(function (b) {
        b.classList.toggle("is-active", b.dataset.productsView === view);
      });
      try { localStorage.setItem(KEY, view); } catch (e) { /* private mode */ }
    };
    toggles.forEach(function (b) {
      b.addEventListener("click", function () { setView(b.dataset.productsView); });
    });
    var saved = "list";
    try { saved = localStorage.getItem(KEY) || "list"; } catch (e) { /* ignore */ }
    setView(saved);

    // ---- Open one product's editor at a time ----
    var closeAll = function () {
      grid.querySelectorAll(".product-item").forEach(function (it) {
        it.querySelector(".product-detail").hidden = true;
        it.querySelector(".product-summary").setAttribute("aria-expanded", "false");
        it.classList.remove("is-open");
      });
    };
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
  }

  // ---- The ＋ Add product panel: hidden until asked for ----
  var addToggle = document.getElementById("products-add-toggle");
  var addPanel = document.getElementById("product-add-panel");
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

  // ---- On sale is a tick that submits itself ----
  document.querySelectorAll(".product-onsale-toggle").forEach(function (box) {
    box.addEventListener("change", function () {
      // The box carries form="onsale_N"; .form resolves it wherever it
      // is drawn. A ticked box posts active=1, an unticked one posts
      // nothing, which the archive route reads as "off sale".
      if (box.form) box.form.submit();
    });
  });

  // ---- Picture chooser: upload / Media Library / describe ----
  document.querySelectorAll("[data-image-controls]").forEach(function (root) {
    var file = root.querySelector("[data-image-file]");
    var libUrl = root.querySelector("[data-image-library-url]");
    var prompt = root.querySelector("[data-image-ai] input");
    var preview = root.querySelector("[data-image-preview]");
    var previewImg = root.querySelector("[data-preview-img]");

    var showPreview = function (src) {
      if (!preview || !previewImg) return;
      previewImg.src = src;
      preview.hidden = !src;
    };

    // Choosing one source clears the others, so only one answer is sent.
    var upBtn = root.querySelector("[data-image-upload]");
    if (upBtn && file) {
      upBtn.addEventListener("click", function () { file.click(); });
      file.addEventListener("change", function () {
        if (!file.files || !file.files.length) return;
        if (libUrl) libUrl.value = "";
        if (prompt) prompt.value = "";
        showPreview(URL.createObjectURL(file.files[0]));
      });
    }

    var libBtn = root.querySelector("[data-image-library]");
    if (libBtn && libUrl && window.cmsImagePicker) {
      libBtn.addEventListener("click", async function () {
        var url = await window.cmsImagePicker.open();
        if (!url) return;
        libUrl.value = url;
        if (file) file.value = "";
        if (prompt) prompt.value = "";
        showPreview(url);
      });
    }

    var aiBtn = root.querySelector("[data-image-ai-toggle]");
    var aiBox = root.querySelector("[data-image-ai]");
    if (aiBtn && aiBox) {
      aiBtn.addEventListener("click", function () {
        aiBox.hidden = !aiBox.hidden;
        if (!aiBox.hidden) {
          if (file) file.value = "";
          if (libUrl) libUrl.value = "";
          var inp = aiBox.querySelector("input");
          if (inp) inp.focus();
        }
      });
    }
  });
})();
