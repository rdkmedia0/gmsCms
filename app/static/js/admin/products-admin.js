// The Products screen: Active/Archived tabs (server-rendered), search,
// click-to-open ONE editor at a time, an "add" panel behind the ＋ button,
// the Available/Archived ticks that submit themselves, bulk archive/restore
// from the row checkboxes, and the three-way picture chooser each product
// form carries.
(function () {
  "use strict";

  var grid = document.getElementById("products-grid");

  if (grid) {
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

  // ---- The Available and Archived ticks each submit their own form ----
  document.querySelectorAll(".product-avail-toggle, .product-archive-toggle").forEach(function (box) {
    box.addEventListener("change", function () {
      // The box carries form="avail_N" / "arch_N"; .form resolves it
      // wherever it is drawn. A ticked box posts value=1, an unticked one
      // posts nothing, which each route reads as the "off" state.
      if (box.form) box.form.submit();
    });
  });

  // ---- Bulk select: the row ticks feed one Archive/Restore action ----
  var bulkBar = document.getElementById("products-bulk-bar");
  var bulkN = document.getElementById("products-bulk-n");
  var bulkClear = document.getElementById("products-bulk-clear");
  var boxes = document.querySelectorAll(".product-select-box");
  var syncBulk = function () {
    var n = 0;
    boxes.forEach(function (b) { if (b.checked) n++; });
    if (bulkN) bulkN.textContent = n;
    if (bulkBar) bulkBar.hidden = n === 0;
  };
  boxes.forEach(function (b) { b.addEventListener("change", syncBulk); });
  if (bulkClear) {
    bulkClear.addEventListener("click", function () {
      boxes.forEach(function (b) { b.checked = false; });
      syncBulk();
    });
  }
  syncBulk();

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

  // ---- Download file: upload a new one, or choose from the library ----
  document.querySelectorAll("[data-download-controls]").forEach(function (root) {
    var btn = root.querySelector("[data-download-upload]");
    var input = root.querySelector("[data-download-input]");
    var chosen = root.querySelector("[data-download-chosen]");
    var ref = root.querySelector(".download-file-ref");

    if (btn && input) {
      btn.addEventListener("click", function () { input.click(); });
      input.addEventListener("change", function () {
        if (!input.files || !input.files.length) return;
        // An uploaded file wins over a chosen one, so clear the select.
        if (ref) ref.value = "";
        if (chosen) {
          chosen.textContent = "New file: " + input.files[0].name;
          chosen.hidden = false;
        }
      });
    }
    // Picking an existing file drops any pending upload.
    if (ref) {
      ref.addEventListener("change", function () {
        if (ref.value && input) input.value = "";
        if (ref.value && chosen) chosen.hidden = true;
      });
    }
  });
})();
