(() => {
  const walker = document.getElementById("raccoon-walker");
  const gif = document.getElementById("raccoon-gif");
  const still = document.getElementById("raccoon-still");
  if (!walker || !gif || !still) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = reducedMotion.matches;
  let hasStill = false;

  function updatePlayback() {
    const stopped = paused || document.hidden;
    walker.classList.toggle("is-paused", stopped);
    gif.hidden = stopped && hasStill;
    still.hidden = !stopped || !hasStill;
    const action = paused ? "Reproducir animación del mapache" : "Pausar animación del mapache";
    walker.title = action;
    walker.setAttribute("aria-label", `Created and Developed by H. ${action}`);
  }

  function prepareStill() {
    if (!gif.naturalWidth) return;
    // A static frame preserves the supplied transparent artwork when motion is paused.
    const context = still.getContext("2d");
    if (context) {
      context.drawImage(gif, 0, 0, still.width, still.height);
      hasStill = true;
    }
    updatePlayback();
  }

  gif.addEventListener("load", prepareStill);
  if (gif.complete) prepareStill();
  walker.addEventListener("click", () => {
    paused = !paused;
    updatePlayback();
  });
  reducedMotion.addEventListener("change", () => {
    paused = reducedMotion.matches;
    updatePlayback();
  });
  document.addEventListener("visibilitychange", updatePlayback);
  updatePlayback();
})();
