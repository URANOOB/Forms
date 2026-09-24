(() => {
  const container = document.getElementById("home-animation");
  if (!container || !window.lottie) return;

  const panel = document.getElementById("home-animation-panel");
  const hero = panel.closest(".home-hero");
  const toggle = document.getElementById("home-animation-toggle");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = reducedMotion.matches;
  let ready = false;
  const animation = window.lottie.loadAnimation({
    container,
    renderer: "svg",
    loop: true,
    autoplay: false,
    path: container.dataset.animation,
    rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
  });

  function updatePlayback() {
    if (!ready) return;
    if (paused || document.hidden) animation.pause();
    else animation.play();
    toggle.textContent = paused ? "Reproducir animación" : "Pausar animación";
  }

  animation.addEventListener("DOMLoaded", () => {
    ready = true;
    panel.hidden = false;
    hero.classList.add("has-animation");
    animation.resize();
    animation.goToAndStop(0, true);
    updatePlayback();
  });
  function hideAnimation() {
    ready = false;
    animation.pause();
    panel.hidden = true;
    hero.classList.remove("has-animation");
  }
  animation.addEventListener("data_failed", hideAnimation);
  animation.addEventListener("error", hideAnimation);
  toggle.addEventListener("click", () => {
    paused = !paused;
    updatePlayback();
  });
  reducedMotion.addEventListener("change", () => {
    paused = reducedMotion.matches;
    updatePlayback();
  });
  document.addEventListener("visibilitychange", updatePlayback);
})();
