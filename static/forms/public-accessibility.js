(() => {
  const body = document.body;
  if (!body.hasAttribute("data-public-accessibility")) return;
  const panel = document.getElementById("accessibility-panel");
  const trigger = document.getElementById("accessibility-open");
  const storageKey = "logicforms-public-accessibility-v1";
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const defaults = { text: "normal", contrast: "normal", spacing: "normal", focus: false, motion: false };
  let preferences = { ...defaults };
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (stored && typeof stored === "object") {
      for (const [key, allowed] of Object.entries({ text: ["normal", "large", "extra"], contrast: ["normal", "high"], spacing: ["normal", "wide"] })) {
        if (allowed.includes(stored[key])) preferences[key] = stored[key];
      }
      for (const key of ["focus", "motion"]) preferences[key] = stored[key] === true;
    }
  } catch { /* Preferences remain usable when browser storage is unavailable. */ }

  function apply(save = false) {
    document.documentElement.dataset.publicText = preferences.text;
    body.dataset.publicContrast = preferences.contrast;
    body.dataset.publicSpacing = preferences.spacing;
    body.dataset.publicFocus = preferences.focus ? "strong" : "normal";
    body.dataset.publicMotion = preferences.motion || motionQuery.matches ? "reduce" : "normal";
    for (const key of ["text", "contrast", "spacing"]) {
      const name = key === "text" ? "public-text-size" : `public-${key}`;
      panel.querySelector(`input[name="${name}"][value="${preferences[key]}"]`).checked = true;
    }
    document.getElementById("public-focus").checked = preferences.focus;
    document.getElementById("public-motion").checked = preferences.motion || motionQuery.matches;
    document.getElementById("public-motion").disabled = motionQuery.matches;
    document.dispatchEvent(new CustomEvent("public:accessibility-change"));
    if (save) {
      try { localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch { /* Session only. */ }
    }
  }
  apply();
  motionQuery.addEventListener("change", () => apply());
  if (typeof panel.showModal !== "function") return;
  document.getElementById("public-accessibility-toolbar").hidden = false;
  trigger.addEventListener("click", () => {
    panel.showModal();
    document.getElementById("accessibility-close").focus();
  });
  document.getElementById("accessibility-close").addEventListener("click", () => panel.close());
  panel.addEventListener("close", () => trigger.focus({ preventScroll: true }));
  panel.addEventListener("change", (event) => {
    const input = event.target;
    const key = { "public-text-size": "text", "public-contrast": "contrast", "public-spacing": "spacing" }[input.name];
    if (key) preferences[key] = input.value;
    else if (input.id === "public-focus") preferences.focus = input.checked;
    else if (input.id === "public-motion") preferences.motion = input.checked;
    else return;
    apply(true);
  });

  const read = document.getElementById("accessibility-read");
  const stop = document.getElementById("accessibility-stop");
  const toolbarStop = document.getElementById("accessibility-stop-toolbar");
  const speechStatus = document.getElementById("accessibility-speech-status");
  const synth = window.speechSynthesis;
  const speechAvailable = Boolean(synth && window.SpeechSynthesisUtterance);
  let sequence = 0;
  let reading = false;
  function stopReading(message = "Lectura detenida.") {
    sequence++;
    if (reading) synth?.cancel();
    reading = false;
    stop.disabled = true;
    read.disabled = !speechAvailable;
    if (document.activeElement === stop && speechAvailable) read.focus({ preventScroll: true });
    // Do not remove the currently focused button from the keyboard sequence.
    if (document.activeElement === toolbarStop) trigger.focus({ preventScroll: true });
    toolbarStop.hidden = true;
    speechStatus.textContent = message;
  }
  stop.addEventListener("click", () => stopReading());
  toolbarStop.addEventListener("click", () => stopReading());
  document.getElementById("accessibility-reset").addEventListener("click", () => {
    preferences = { ...defaults };
    apply(true);
    stopReading("Preferencias restablecidas.");
  });
  if (!speechAvailable) {
    read.disabled = true;
    speechStatus.textContent = "La lectura en voz alta no está disponible en este navegador.";
    return;
  }
  read.addEventListener("click", () => {
    stopReading("");
    const welcome = document.getElementById("welcome-screen");
    const section = document.querySelector(".form-section:not([hidden])");
    const scope = welcome && !welcome.hidden ? welcome : section || document.getElementById("public-main");
    // Deliberately read author-provided headings and instructions only, never
    // input values, selected answers, filenames, errors or uploaded previews.
    const nodes = [...scope.querySelectorAll("h1, .section-intro h2, .section-intro .hint, .field > h3, .field > label, .field legend, .field .help:not(.additional-choice-text .help), .field > .hint, .information, .welcome-text, .confirmation-title, .confirmation-description, .success-card > p")];
    const texts = nodes.filter((node) => !node.closest("[hidden]")).map((node) => node.textContent.replace(/\s+/g, " ").trim()).filter(Boolean);
    // Short utterances avoid the long-text limits of several browser engines.
    const chunks = texts.flatMap((text) => text.match(/.{1,180}(?:\s|$)|\S{1,180}/gu) || [text]);
    if (!chunks.length) { speechStatus.textContent = "No hay preguntas o instrucciones visibles para leer."; return; }
    const token = sequence;
    const voice = synth.getVoices().find((item) => item.lang.startsWith("es") && item.localService)
      || synth.getVoices().find((item) => item.lang.startsWith("es"));
    reading = true;
    stop.disabled = false;
    read.disabled = true;
    toolbarStop.hidden = false;
    speechStatus.textContent = "Leyendo la sección visible…";
    function speak(index) {
      if (token !== sequence) return;
      if (index === chunks.length) { stopReading("Lectura finalizada."); return; }
      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      utterance.lang = "es-CO";
      if (voice) utterance.voice = voice;
      utterance.rate = 0.95;
      utterance.onend = () => speak(index + 1);
      utterance.onerror = () => {
        if (token === sequence) stopReading("No se pudo continuar la lectura. Puedes intentarlo de nuevo.");
      };
      synth.speak(utterance);
    }
    // Keep focus on an enabled control once playback disables its button.
    stop.focus({ preventScroll: true });
    speak(0);
  });
  document.addEventListener("public:section-change", () => { if (reading) stopReading(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden && reading) stopReading(); });
  window.addEventListener("pagehide", () => { if (reading) stopReading(); });
})();
