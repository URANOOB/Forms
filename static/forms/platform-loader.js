(() => {
  if (window.platformLoader) return;
  const config = document.getElementById('platform-loader-config');
  const pending = new Map();
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let timer, animation, playerPromise, visible = false;
  const indicator = document.createElement('div');
  indicator.id = 'platform-loader';
  indicator.hidden = true;
  indicator.setAttribute('role', 'status');
  indicator.setAttribute('aria-live', 'polite');
  indicator.setAttribute('aria-atomic', 'true');
  // A manual popover stays visible above modal dialogs without taking focus.
  if (indicator.showPopover) indicator.setAttribute('popover', 'manual');
  const picture = document.createElement('div');
  picture.className = 'platform-loader-animation';
  picture.setAttribute('aria-hidden', 'true');
  picture.hidden = true;
  const label = document.createElement('span');
  indicator.append(picture, label);
  document.body.append(indicator);

  function playback() {
    if (!animation) return;
    if (!visible || document.hidden || reducedMotion.matches) animation.pause();
    else animation.play();
  }
  function loadPlayer() {
    if (window.lottie) return Promise.resolve(window.lottie);
    if (!playerPromise) playerPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = config.dataset.player;
      script.onload = () => resolve(window.lottie);
      script.onerror = reject;
      document.head.append(script);
    });
    return playerPromise;
  }
  async function show() {
    if (!pending.size) return;
    // Keep the status accessible when the rest of the page is inert behind a dialog.
    const modal = [...document.querySelectorAll('dialog[open]')].at(-1);
    (modal || document.body).append(indicator);
    visible = true;
    label.textContent = [...pending.values()].at(-1);
    indicator.hidden = false;
    indicator.showPopover?.();
    try {
      const player = await loadPlayer();
      if (!visible) return;
      if (!animation) {
        animation = player.loadAnimation({
          container: picture, renderer: 'svg', loop: true, autoplay: false,
          path: config.dataset.animation,
          rendererSettings: { preserveAspectRatio: 'xMidYMid meet' },
        });
        animation.addEventListener('DOMLoaded', () => {
          picture.hidden = false;
          animation.resize();
          animation.goToAndStop(0, true);
          playback();
        });
        const fallback = () => { picture.hidden = true; animation.pause(); };
        animation.addEventListener('data_failed', fallback);
        animation.addEventListener('error', fallback);
      }
      playback();
    } catch { /* Keep the text visible if the animation cannot load. */ }
  }
  function hide() {
    clearTimeout(timer);
    visible = false;
    indicator.hidePopover?.();
    indicator.hidden = true;
    playback();
  }
  window.platformLoader = {
    start(message = 'Cargando…') {
      const token = Symbol();
      pending.set(token, message);
      if (visible) label.textContent = message;
      else if (pending.size === 1) timer = setTimeout(show, 250);
      return () => {
        pending.delete(token);
        if (!pending.size) hide();
        else if (visible) label.textContent = [...pending.values()].at(-1);
      };
    },
  };
  reducedMotion.addEventListener('change', playback);
  document.addEventListener('visibilitychange', playback);
  window.addEventListener('pagehide', () => { pending.clear(); hide(); });
})();
