(() => {
  const config = document.getElementById("platform-session");
  if (!config) return;
  const timeout = Number(config.dataset.timeout) * 1000;
  const interval = Math.min(30000, timeout / 4);
  let deadline = Date.now() + timeout;
  let pendingActivity = false;
  let checking = false;
  let lastSent = Date.now();

  function closeSession() {
    if (window.platformSessionExpired) return;
    window.platformSessionExpired = true;
    const login = new URL(config.dataset.loginUrl, location.origin);
    login.searchParams.set("expired", "1");
    login.searchParams.set("next", location.pathname + location.search);
    // Hide private content even if navigation fails because the device is offline.
    const message = document.createElement("p");
    message.textContent = "Tu sesión se cerró por inactividad. Inicia sesión de nuevo para continuar.";
    const link = document.createElement("a");
    link.href = login.href;
    link.textContent = "Iniciar sesión";
    document.body.replaceChildren(message, link);
    location.replace(login.href);
  }

  async function check(active = false) {
    if (checking || window.platformSessionExpired) return;
    checking = true;
    const started = Date.now();
    if (active) {
      pendingActivity = false;
      lastSent = started;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const csrf = config.dataset.csrf;
      const response = await fetch(config.dataset.url, {
        method: active ? "POST" : "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: active ? { "X-CSRFToken": csrf || "" } : {},
        signal: controller.signal,
      });
      if (response.status === 401) { closeSession(); return; }
      if (!response.ok) throw new Error("session_check_failed");
      const result = await response.json();
      deadline = started + result.remaining_seconds * 1000;
      if (Date.now() >= deadline) closeSession();
    } catch {
      if (active) pendingActivity = true;
      if (Date.now() >= deadline) closeSession();
    } finally {
      clearTimeout(timer);
      checking = false;
    }
  }

  function activity(event) {
    if (!event.isTrusted || document.hidden || window.platformSessionExpired) return;
    if (Date.now() >= deadline) { check(); return; }
    pendingActivity = true;
    if (Date.now() - lastSent >= interval) check(true);
  }
  for (const name of ["pointerdown", "pointermove", "keydown", "input", "scroll"])
    document.addEventListener(name, activity, { passive: true, capture: true });
  setInterval(() => {
    if (Date.now() >= deadline) check();
    else if (pendingActivity && !document.hidden && Date.now() - lastSent >= interval) check(true);
  }, Math.min(1000, interval));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
  window.addEventListener("pageshow", (event) => { if (event.persisted) check(); });
  check();
})();
