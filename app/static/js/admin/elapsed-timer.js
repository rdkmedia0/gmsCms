// Shared "elapsed seconds" counter for slow async actions (AI image/theme
// generation, chat replies) that can take anywhere from a few seconds to
// over a minute — three different templates used to each hand-roll their
// own setInterval for this exact pattern. `render(seconds)` is called
// immediately with 0, then once per second; call the returned function to
// stop (skip calling it if the page is about to navigate away anyway).
window.cmsElapsedTimer = function cmsElapsedTimer(render) {
  let seconds = 0;
  render(seconds);
  const id = setInterval(function () {
    seconds += 1;
    render(seconds);
  }, 1000);
  return function stop() { clearInterval(id); };
};
