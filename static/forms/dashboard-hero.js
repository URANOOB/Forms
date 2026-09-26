(() => {
  const track = document.getElementById("metrics-heading-track");
  const visual = document.getElementById("metrics-heading-visual");
  const art = document.getElementById("metrics-heading-art");
  const frame = document.getElementById("metrics-heading-frame");
  const toggle = document.getElementById("metrics-animation-toggle");
  if (!track || !visual || !art || !frame || !toggle || !window.lottie) return;

  const paths = [1, 2, 3, 4, 5]
    .map((number) => track.getAttribute(`data-animation-${number}`))
    .filter(Boolean);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let nextIndex = 0;
  let direction = 1;
  let animation = null;
  let travel = null;
  let loadTimeout = null;
  let ready = false;
  let paused = reducedMotion.matches;
  let failedInSequence = 0;

  function labelToggle() {
    const label = paused ? "Reproducir animaciones" : "Pausar animaciones";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    toggle.querySelector(".material-symbols-outlined").textContent = paused ? "play_arrow" : "pause";
  }

  function fitArtwork(instance) {
    const drawing = frame.querySelector("svg > g");
    if (!drawing) return;

    const facing = art.style.transform;
    art.style.transform = "";
    frame.style.transform = "";
    const origin = frame.getBoundingClientRect();
    const lastFrame = Math.max(0, Math.floor(instance.totalFrames - 1));
    let left = Infinity;
    let top = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    for (const fraction of [0, 0.25, 0.5, 0.75]) {
      instance.goToAndStop(Math.floor(lastFrame * fraction), true);
      const bounds = drawing.getBoundingClientRect();
      left = Math.min(left, bounds.left);
      top = Math.min(top, bounds.top);
      right = Math.max(right, bounds.right);
      bottom = Math.max(bottom, bounds.bottom);
    }
    instance.goToAndStop(0, true);

    const width = right - left;
    const height = bottom - top;
    if (width > 0 && height > 0) {
      const scale = Math.min((visual.clientWidth - 14) / width, (visual.clientHeight - 12) / height);
      const x = (visual.clientWidth - width * scale) / 2 - (left - origin.left) * scale;
      const y = visual.clientHeight - 2 - (bottom - origin.top) * scale;
      frame.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    }
    art.style.transform = facing;
  }

  function stopCurrent() {
    ready = false;
    clearTimeout(loadTimeout);
    loadTimeout = null;
    if (travel) {
      travel.onfinish = null;
      travel.cancel();
      travel = null;
    }
    animation?.destroy();
    animation = null;
    frame.replaceChildren();
    art.style.transform = "";
    frame.style.transform = "";
  }

  function startTravel() {
    if (!ready || travel) return;
    visual.style.transform = "";
    const distance = Math.max(0, track.clientWidth - visual.offsetWidth);
    const duration = Math.max(6500, Math.min(12000, distance * 7));
    const returning = direction === -1;
    art.style.transform = returning ? "scaleX(-1)" : "";
    const from = returning ? distance : 0;
    const to = returning ? 0 : distance;
    direction *= -1;
    travel = visual.animate(
      [{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
      { duration, easing: "linear", fill: "forwards" },
    );
    travel.onfinish = () => {
      travel = null;
      startNext();
    };
  }

  function updatePlayback() {
    if (!ready) return;
    if (paused || document.hidden) {
      travel?.pause();
      animation.pause();
    } else {
      startTravel();
      travel?.play();
      animation.play();
    }
    labelToggle();
  }

  function startNext() {
    stopCurrent();
    if (!paths.length || failedInSequence >= paths.length) {
      toggle.hidden = true;
      return;
    }

    const path = paths[nextIndex];
    nextIndex = (nextIndex + 1) % paths.length;
    const instance = window.lottie.loadAnimation({
      container: frame,
      renderer: "svg",
      loop: true,
      autoplay: false,
      path,
      rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
    });
    animation = instance;

    function showAnimation() {
      if (animation !== instance || ready) return;
      clearTimeout(loadTimeout);
      loadTimeout = null;
      ready = true;
      failedInSequence = 0;
      toggle.hidden = false;
      instance.resize();
      fitArtwork(instance);
      if (paused && reducedMotion.matches) {
        visual.style.transform = `translateX(${Math.max(0, (track.clientWidth - visual.offsetWidth) / 2)}px)`;
      }
      updatePlayback();
    }

    function skipFailed() {
      if (animation !== instance || ready) return;
      failedInSequence += 1;
      startNext();
    }

    instance.addEventListener("DOMLoaded", showAnimation);
    instance.addEventListener("data_failed", skipFailed);
    instance.addEventListener("error", skipFailed);
    if (instance.isLoaded) requestAnimationFrame(showAnimation);
    loadTimeout = setTimeout(skipFailed, 8000);
  }

  toggle.addEventListener("click", () => {
    paused = !paused;
    updatePlayback();
  });
  reducedMotion.addEventListener("change", () => {
    paused = reducedMotion.matches;
    updatePlayback();
  });
  document.addEventListener("visibilitychange", updatePlayback);
  window.addEventListener("resize", () => {
    if (!ready) return;
    animation.resize();
    fitArtwork(animation);
    updatePlayback();
  });

  startNext();
})();
