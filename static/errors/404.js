(() => {
  const container = document.getElementById("not-found-animation");
  if (!container || !window.lottie) return;

  const fallback = document.getElementById("not-found-fallback");
  const toggle = document.getElementById("animation-toggle");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const animation = window.lottie.loadAnimation({
    container,
    renderer: "svg",
    loop: true,
    autoplay: false,
    path: container.dataset.animation,
    rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
  });
  let paused = reducedMotion.matches;
  let ready = false;

  function updatePlayback() {
    if (!ready) return;
    if (paused || document.hidden) animation.pause();
    else animation.play();
    toggle.textContent = paused ? "Reproducir animación" : "Pausar animación";
  }

  animation.addEventListener("DOMLoaded", () => {
    ready = true;
    fallback.hidden = true;
    toggle.hidden = reducedMotion.matches;
    animation.goToAndStop(0, true);
    updatePlayback();
  });
  animation.addEventListener("data_failed", () => {
    container.hidden = true;
    fallback.hidden = false;
    toggle.hidden = true;
  });
  toggle.addEventListener("click", () => {
    paused = !paused;
    updatePlayback();
  });
  reducedMotion.addEventListener("change", () => {
    paused = reducedMotion.matches;
    toggle.hidden = !ready || reducedMotion.matches;
    updatePlayback();
  });
  document.addEventListener("visibilitychange", updatePlayback);
})();
