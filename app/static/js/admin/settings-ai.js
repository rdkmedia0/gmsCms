(function () {
  var select = document.getElementById("ai_provider");
  var fieldsets = document.querySelectorAll(".ai-provider-fields");
  function sync() {
    fieldsets.forEach(function (fs) {
      fs.hidden = fs.dataset.provider !== select.value;
    });
  }
  select.addEventListener("change", sync);
  sync();

  // "Load Models" — fetches live from whatever's currently typed in the
  // url/key fields (not necessarily saved yet), then fills every target
  // <select> named in data-targets. Gemini's second target
  // (gemini_image_model) only gets entries flagged image_gen by the
  // backend (see assistant.list_models) — everything else gets the
  // full list, each option labeled with a (vision) tag when known.
  var modelsUrl = document.getElementById("ai-settings-form").dataset.modelsUrl;
  document.querySelectorAll(".cms-load-models-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var provider = btn.dataset.provider;
      var url = btn.dataset.urlInput ? document.getElementById(btn.dataset.urlInput).value.trim() : "";
      var key = btn.dataset.keyInput ? document.getElementById(btn.dataset.keyInput).value.trim() : "";
      var targetIds = btn.dataset.targets.split(",");
      var originalLabel = btn.textContent;
      btn.textContent = "Loading…";
      btn.disabled = true;
      var body = new URLSearchParams();
      body.set("provider", provider);
      body.set("url", url);
      body.set("api_key", key);
      fetch(modelsUrl, { method: "POST", body: body })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (res) {
          btn.textContent = originalLabel;
          btn.disabled = false;
          if (!res.ok) { alert(res.data.error || "Could not load models."); return; }
          targetIds.forEach(function (id) {
            var sel = document.getElementById(id);
            if (!sel) return;
            var isImageTarget = sel.classList.contains("cms-model-select-image");
            var current = sel.value;
            var models = res.data.models.filter(function (m) { return !isImageTarget || m.image_gen; });
            sel.innerHTML = "";
            models.forEach(function (m) {
              var opt = document.createElement("option");
              opt.value = m.id;
              opt.textContent = m.id + (m.vision ? "  (vision)" : "");
              sel.appendChild(opt);
            });
            if (models.some(function (m) { return m.id === current; })) sel.value = current;
            else if (current) {
              var keep = document.createElement("option");
              keep.value = current; keep.textContent = current; keep.selected = true;
              sel.insertBefore(keep, sel.firstChild);
            }
          });
        })
        .catch(function () {
          btn.textContent = originalLabel;
          btn.disabled = false;
          alert("Could not load models — check the connection.");
        });
    });
  });
})();
