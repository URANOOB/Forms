(() => {
  const container = document.getElementById("confirmation-animation");
  if (!container || !window.lottie || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const animation = window.lottie.loadAnimation({
    container,
    renderer: "svg",
    loop: false,
    autoplay: false,
    path: container.dataset.animation,
    rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
  });
  animation.addEventListener("DOMLoaded", () => {
    container.hidden = false;
    animation.resize();
    if (!document.hidden) animation.play();
  });
  animation.addEventListener("error", () => { container.hidden = true; });
  animation.addEventListener("data_failed", () => { container.hidden = true; });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) animation.pause();
    else if (container.hidden === false && animation.currentFrame < animation.totalFrames - 1) animation.play();
  });
})();
