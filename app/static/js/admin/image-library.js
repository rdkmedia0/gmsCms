(function () {
  const dataEl = document.getElementById("media-library-data");
  const images = dataEl ? JSON.parse(dataEl.textContent) : [];
  const grid = document.getElementById("media-library-grid");
  const lightbox = document.getElementById("media-lightbox");
  const lbImg = document.getElementById("media-lightbox-img");
  const lbCaption = document.getElementById("media-lightbox-caption");
  const deleteUrlBase = lightbox.dataset.deleteUrlBase;
  const generateFromUrl = lightbox.dataset.generateFromUrl;
  let current = -1;

  function show(index) {
    if (!images.length) return;
    current = (index + images.length) % images.length;
    const item = images[current];
    lbImg.src = item.url;
    lbCaption.textContent = item.prompt ? (item.source + " — " + item.prompt) : item.source;
    lightbox.hidden = false;
  }
  function close() { lightbox.hidden = true; }

  if (grid) {
    grid.querySelectorAll(".media-library-thumb-btn[data-index]").forEach((btn) => {
      btn.addEventListener("click", () => show(parseInt(btn.dataset.index, 10)));
    });
    grid.querySelectorAll(".media-library-delete").forEach((btn) => {
      btn.addEventListener("click", () => deleteFile(btn.dataset.filename));
    });
  }

  document.getElementById("media-lightbox-prev").addEventListener("click", () => show(current - 1));
  document.getElementById("media-lightbox-next").addEventListener("click", () => show(current + 1));
  document.getElementById("media-lightbox-close").addEventListener("click", close);
  lightbox.addEventListener("click", (e) => { if (e.target === lightbox) close(); });
  document.addEventListener("keydown", (e) => {
    if (lightbox.hidden) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") show(current - 1);
    else if (e.key === "ArrowRight") show(current + 1);
  });

  async function deleteFile(filename) {
    if (!confirm("Delete this file permanently? This cannot be undone.")) return;
    try {
      const res = await fetch(deleteUrlBase.replace("__FN__", encodeURIComponent(filename)), {
        method: "POST",
        headers: { "X-Inline-Edit": "1" },
      });
      if (res.ok) location.reload();
      else alert("Delete failed.");
    } catch {
      alert("Delete failed — check your connection.");
    }
  }

  document.getElementById("media-lightbox-delete").addEventListener("click", () => {
    if (current === -1) return;
    deleteFile(images[current].filename);
  });

  document.getElementById("media-lightbox-generate").addEventListener("click", async () => {
    if (current === -1) return;
    const prompt = window.prompt("Describe the new image (based on this one):", "");
    if (!prompt || !prompt.trim()) return;
    const btn = document.getElementById("media-lightbox-generate");
    const original = btn.textContent;
    btn.disabled = true;
    const stop = window.cmsElapsedTimer((seconds) => { btn.textContent = "Generating… " + seconds + "s"; });
    try {
      const formData = new URLSearchParams();
      formData.set("source_filename", images[current].filename);
      formData.set("prompt", prompt.trim());
      const res = await fetch(generateFromUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
        body: formData,
      });
      const data = await res.json();
      stop();
      btn.disabled = false;
      btn.textContent = original;
      if (res.ok && data.url) {
        location.reload();
      } else {
        alert(data.error || "Generation failed.");
      }
    } catch {
      stop();
      btn.disabled = false;
      btn.textContent = original;
      alert("Generation failed — check your connection.");
    }
  });
})();
