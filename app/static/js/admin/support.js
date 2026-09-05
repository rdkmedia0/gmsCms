// The Support screen's Copy buttons: a wallet address to the clipboard,
// and the button says so for a moment. The address is in a readonly box
// beside it as well, so without a clipboard (an old browser, a plain
// http page where the API is refused) it can still be selected by hand.
(function () {
  "use strict";
  document.querySelectorAll(".support-copy").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var text = btn.getAttribute("data-copy") || "";
      var was = btn.textContent;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Copied";
      } catch (e) {
        //  Fall back to selecting the box, which is the next best thing.
        var box = btn.parentElement && btn.parentElement.querySelector("input");
        if (box) { box.focus(); box.select(); }
        btn.textContent = "Select and copy";
      }
      setTimeout(function () { btn.textContent = was; }, 1600);
    });
  });
})();
