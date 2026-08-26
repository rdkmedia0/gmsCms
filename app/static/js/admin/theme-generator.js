document.getElementById("theme-gen-form").addEventListener("submit", function () {
  const btn = document.getElementById("tg-submit");
  btn.disabled = true;
  window.cmsElapsedTimer(function (seconds) {
    btn.textContent = "✨ Generating… " + seconds + "s (this can take up to a minute)";
  });
});
