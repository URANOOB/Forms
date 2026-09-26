(() => {
  const container = document.getElementById("confirmation-animation");
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const reduced = () => motionQuery.matches || document.body.dataset.publicMotion === "reduce";
  if (!container || !window.lottie || reduced()) return;

  const animation = window.lottie.loadAnimation({
    container,
    renderer: "svg",
    loop: false,
    autoplay: false,
    path: container.dataset.animation,
    rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
  });
  animation.addEventListener("DOMLoaded", () => {
    if (reduced()) return;
    container.hidden = false;
    animation.resize();
    if (!document.hidden) animation.play();
  });
  animation.addEventListener("error", () => { container.hidden = true; });
  animation.addEventListener("data_failed", () => { container.hidden = true; });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) animation.pause();
    else if (!reduced() && container.hidden === false && animation.currentFrame < animation.totalFrames - 1) animation.play();
  });
  const updateMotion = () => {
    if (reduced()) { animation.pause(); container.hidden = true; }
  };
  motionQuery.addEventListener("change", updateMotion);
  document.addEventListener("public:accessibility-change", updateMotion);
})();
