(() => {
  const form = document.getElementById("public-form");
  if (!form || form.dataset.preview || form.dataset.edit) return;
  const ttl = 24 * 60 * 60 * 1000;
  const prefix = "forms:draft:v1:";
  const baseKey = prefix + form.dataset.formId;
  let key = baseKey;
  let storedRevision = null;
  let writes = Promise.resolve();
  let separateDraft = false;
  const panel = document.getElementById("draft-panel");
  const message = document.getElementById("draft-status");
  const resumeButton = document.getElementById("draft-continue");
  const discardButton = document.getElementById("draft-discard");
  const draftChoice = document.getElementById("draft-choice");
  const draftChoiceLabel = document.getElementById("draft-choice-label");
  const token = form.elements.namedItem("submission_token");
  let forkToken = null;
  const submitButton = document.getElementById("submit-button");
  const status = document.getElementById("submit-status");
  const controls = () =>
    [
      ...form.querySelectorAll("input[name],select[name],textarea[name]"),
    ].filter(
      (input) => input.name.startsWith("answer_") && input.type !== "file",
    );
  let draft = null;
  let pending = false;
  let busy = false;
  let completed = false;
  let available = true;
  let expiryTimer;

  function say(text) {
    panel.hidden = false;
    message.textContent = text;
  }
  function storageFailure() {
    available = false;
    say(
      "Este navegador no permite guardar el borrador. Mantén esta página abierta hasta confirmar el envío.",
    );
  }
  function validDraft(item) {
    return item && Number.isFinite(item.updatedAt) &&
      item.updatedAt <= Date.now() && Date.now() - item.updatedAt < ttl &&
      item.answers && typeof item.answers === "object" && !Array.isArray(item.answers) &&
      typeof item.token === "string" && typeof item.version === "string";
  }
  function readStored(name) {
    try {
      const item = JSON.parse(localStorage.getItem(name));
      return validDraft(item) ? item : null;
    } catch { return null; }
  }
  function storageOperation(operation) {
    writes = writes.then(() => navigator.locks
      ? navigator.locks.request(baseKey, operation)
      : operation()).catch(storageFailure);
    return writes;
  }
  function removeStored() {
    clearTimeout(expiryTimer);
    return storageOperation(() => {
      if (localStorage.getItem(key) === storedRevision) localStorage.removeItem(key);
      storedRevision = null;
    });
  }
  function armExpiry() {
    clearTimeout(expiryTimer);
    if (!draft) return;
    expiryTimer = setTimeout(
      () => {
        removeStored();
        draft = null;
        pending = false;
        form.inert = false;
        resumeButton.hidden = true;
        draftChoiceLabel.hidden = true;
        say(
          "El borrador guardado venció. Puedes completar el formulario; los próximos cambios iniciarán un nuevo borrador.",
        );
      },
      Math.max(0, draft.updatedAt + ttl - Date.now()),
    );
  }
  function store() {
    if (!draft || !available) return;
    const snapshot = { ...draft };
    return storageOperation(async () => {
      // A lock makes the comparison and write atomic across tabs. Without Web Locks,
      // use a private key for this page instead of sharing a read/modify/write slot.
      if (localStorage.getItem(key) !== storedRevision ||
          (!navigator.locks && !separateDraft)) {
        key = `${baseKey}:${crypto.randomUUID()}`;
        separateDraft = true;
        // Never reuse the original submission identity, even while offline.
        forkToken = "";
      }
      if (forkToken === "") {
        // Save the answers before contacting the server. A closed/offline page
        // resumes with an empty identity and obtains a signed one before recovery.
        snapshot.token = token.value = "";
        if (draft) draft.token = "";
        storedRevision = JSON.stringify(snapshot);
        localStorage.setItem(key, storedRevision);
        try { sessionStorage.setItem(baseKey, key); } catch { /* Optional resume hint. */ }
        if (navigator.onLine) {
          try { forkToken = await freshToken(); } catch { /* Retry before sending. */ }
        }
      }
      if (forkToken !== null) {
        snapshot.token = forkToken;
        token.value = forkToken;
        if (draft) draft.token = forkToken;
      }
      const serialized = JSON.stringify(snapshot);
      localStorage.setItem(key, serialized);
      storedRevision = serialized;
      try { sessionStorage.setItem(baseKey, key); } catch { /* Optional resume hint. */ }
      armExpiry();
      if (separateDraft)
        say("Borrador guardado por separado para evitar sobrescribir los datos de otra pestaña. Puedes recuperarlo al volver a esta pestaña.");
    });
  }
  async function save(changed = false) {
    if (pending || completed) return;
    const answers = {};
    for (const input of controls()) {
      answers[input.name] ??= [];
      if (["checkbox", "radio"].includes(input.type)) {
        if (input.checked) answers[input.name].push(input.value);
      } else if (input.multiple) {
        answers[input.name] = [...input.selectedOptions].map(
          (option) => option.value,
        );
      } else answers[input.name].push(input.value);
    }
    draft = {
      version: form.dataset.versionId,
      token: token.value,
      updatedAt: changed || !draft ? Date.now() : draft.updatedAt,
      answers,
      hadFiles:
        [...form.querySelectorAll('input[type="file"]')].some(
          (input) => input.files.length > 0,
        ) ||
        [...form.querySelectorAll('input[type="file"]')].some(
          (input) => Number(input.dataset.uploadPending) > 0,
        ) ||
        Boolean(draft?.hadFiles),
    };
    await store();
    if (available && !separateDraft)
      say(
        navigator.onLine
          ? "Borrador guardado en este navegador durante 24 horas desde el último cambio."
          : "Sin conexión. Borrador guardado en este navegador; podrás enviarlo cuando vuelva internet.",
      );
  }
  async function request(data) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(form.action || location.href, {
        method: "POST",
        body: data,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.headers.get("content-type")?.includes("application/json")) {
        throw new Error(
          response.status === 413
            ? "Los archivos superan el límite del servidor. Reduce su tamaño y reintenta."
            : response.status === 400
              ? "El envío supera los límites o contiene datos no válidos. Reduce las selecciones o los archivos y reintenta; tus respuestas siguen en esta página."
            : response.status === 429
              ? "Se alcanzó el límite de intentos. Espera un minuto y vuelve a intentar."
              : response.status === 403
                ? "La sesión de envío venció. Recarga la página para continuar con el borrador."
                : "No se pudo confirmar el envío. Revisa tu conexión y vuelve a intentar.",
        );
      }
      return { response, data: await response.json() };
    } finally {
      clearTimeout(timeout);
    }
  }
  async function recover() {
    if (!token.value) {
      token.value = await freshToken();
      if (forkToken !== null) forkToken = token.value;
      if (draft) {
        draft.token = token.value;
        await store();
      }
    }
    const body = new FormData();
    body.set(
      "csrfmiddlewaretoken",
      form.elements.namedItem("csrfmiddlewaretoken").value,
    );
    body.set("submission_token", token.value);
    body.set("submission_action", "recover");
    const result = await request(body);
    if (!result.response.ok)
      throw new Error(result.data.message || "No se pudo verificar el envío.");
    if (result.data.received) {
      await confirm(result.data);
      return true;
    }
    token.value = result.data.token;
    if (forkToken) forkToken = token.value;
    if (draft) {
      draft.token = token.value;
      await store();
    }
    return false;
  }
  async function freshToken() {
    const body = new FormData();
    body.set("csrfmiddlewaretoken", form.elements.namedItem("csrfmiddlewaretoken").value);
    body.set("submission_action", "fork");
    body.set("submission_version", form.dataset.versionId);
    const result = await request(body);
    if (!result.response.ok || !result.data.token)
      throw new Error(result.data.message || "No se pudo preparar el envío. Vuelve a intentar.");
    return result.data.token;
  }
  async function confirm(data) {
    completed = true;
    await removeStored();
    draft = null;
    status.textContent = "Respuesta recibida.";
    location.assign(data.redirect);
  }
  function restore() {
    if (!draft || Date.now() - draft.updatedAt >= ttl) return;
    if (draft.version !== form.dataset.versionId) {
      say(
        "El formulario cambió. Conéctate para comprobar el envío anterior o descarta el borrador para comenzar de nuevo.",
      );
      return;
    }
    pending = false;
    form.inert = false;
    resumeButton.hidden = true;
    draftChoiceLabel.hidden = true;
    for (const input of controls()) {
      const values = draft.answers[input.name];
      if (!Array.isArray(values)) continue;
      if (["checkbox", "radio"].includes(input.type))
        input.checked = values.includes(input.value);
      else if (input.multiple) {
        for (const option of input.options)
          option.selected = values.includes(option.value);
      } else input.value = values[0] ?? "";
    }
    token.value = draft.token;
    form.dispatchEvent(new CustomEvent("draft:restored"));
    // Repaint custom date/select widgets after all values and conditions are restored.
    for (const input of controls())
      input.dispatchEvent(new Event("change", { bubbles: false }));
    document.getElementById("welcome-start")?.click();
    say(
      draft.hadFiles
        ? "Borrador recuperado. Vuelve a seleccionar los archivos adjuntos antes de enviar."
        : "Borrador recuperado. Puedes continuar; vence a las 24 horas del último cambio.",
    );
  }
  resumeButton.addEventListener("click", async () => {
    if (!draft) return;
    resumeButton.disabled = true;
    discardButton.disabled = true;
    draftChoice.disabled = true;
    token.value = draft.token;
    try {
      if (navigator.onLine && (await recover())) return;
      restore();
    } catch (error) {
      // Offline recovery is still useful. The server is checked again before submission.
      if (draft?.version === form.dataset.versionId) restore();
      else
        say(
          error instanceof TypeError || error.name === "AbortError"
            ? "No se pudo comprobar el envío anterior. Revisa la conexión y vuelve a intentar."
            : `${error.message} Puedes descartar el borrador para comenzar de nuevo.`,
        );
    } finally {
      resumeButton.disabled = false;
      discardButton.disabled = false;
      draftChoice.disabled = false;
    }
  });
  discardButton.addEventListener("click", async () => {
    if (busy) return;
    await removeStored();
    draft = null;
    // A new visit gets a new signed nonce and resets custom attachment widgets too.
    location.reload();
  });
  for (const name of ["input", "change"])
    form.addEventListener(name, (event) => {
      if (event.target.name?.startsWith("answer_")) save(true);
    });
  window.addEventListener("offline", () => {
    if (draft && !pending) save();
  });
  window.addEventListener("online", () => {
    if (draft && !pending)
      say("La conexión volvió. Puedes enviar tu respuesta.");
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && completed) location.reload();
  });

  try {
    // Expired values are never restored, including drafts of other forms on this origin.
    for (const storedKey of Object.keys(localStorage).filter((name) =>
      name.startsWith(prefix),
    )) {
      if (!readStored(storedKey)) {
        const revision = localStorage.getItem(storedKey);
        const cleanup = () => {
          // Recheck inside the same lock used by writers: another tab may have
          // renewed an expired draft since this page first inspected it.
          if (localStorage.getItem(storedKey) === revision && !readStored(storedKey))
            localStorage.removeItem(storedKey);
        };
        if (navigator.locks)
          navigator.locks.request(storedKey.split(":").slice(0, 4).join(":"), cleanup).catch(storageFailure);
        else cleanup();
      }
    }
    let remembered;
    try { remembered = sessionStorage.getItem(baseKey); } catch { /* Optional hint. */ }
    const candidates = Object.keys(localStorage).filter((name) =>
      (name === baseKey || name.startsWith(`${baseKey}:`)) && readStored(name));
    if (remembered && candidates.includes(remembered)) key = remembered;
    else if (candidates.length) key = candidates.sort((a, b) =>
      (readStored(b)?.updatedAt || 0) - (readStored(a)?.updatedAt || 0))[0];
    storedRevision = localStorage.getItem(key);
    draft = readStored(key);
    for (const [index, name] of candidates.entries()) {
      const item = readStored(name);
      if (!item) continue;
      const option = document.createElement("option");
      option.value = name;
      option.textContent = `Borrador ${index + 1} · ${new Date(item.updatedAt).toLocaleString()}`;
      option.selected = name === key;
      draftChoice.append(option);
    }
    draftChoice.addEventListener("change", () => {
      if (!pending || busy) return;
      try {
        key = draftChoice.value;
        storedRevision = localStorage.getItem(key);
        draft = readStored(key);
        if (!draft) { location.reload(); return; }
        sessionStorage.setItem(baseKey, key);
        armExpiry();
        resumeButton.textContent = draft.version === form.dataset.versionId
          ? "Continuar borrador" : "Comprobar envío anterior";
      } catch { storageFailure(); }
    });
  } catch {
    storageFailure();
  }
  if (draft && form.dataset.bound !== "true") {
    pending = true;
    form.inert = true;
    armExpiry();
    resumeButton.hidden = false;
    draftChoiceLabel.hidden = draftChoice.options.length < 2;
    const changedVersion = draft.version !== form.dataset.versionId;
    resumeButton.textContent = changedVersion
      ? "Comprobar envío anterior"
      : "Continuar borrador";
    say(
      changedVersion
        ? "El formulario cambió. Puedes comprobar si el envío anterior fue recibido o descartar el borrador para completar la nueva versión."
        : "Tienes un formulario pendiente en este navegador. Puedes continuar o descartar los datos guardados.",
    );
  } else if (form.dataset.bound === "true") {
    // Server validation owns the displayed values; do not overwrite them with a local draft.
    draft = null;
    save(true);
  } else if (available) {
    say(
      "Tus respuestas se guardarán en este navegador durante 24 horas desde el último cambio. En un dispositivo compartido, descarta los datos al terminar.",
    );
  }

  window.publicDraft = {
    async submit() {
      if (busy || pending || completed) return;
      busy = true;
      submitButton.disabled = true;
      discardButton.disabled = true;
      form.inert = true;
      form.setAttribute("aria-busy", "true");
      status.textContent = "Comprobando el envío…";
      const stopLoading = window.platformLoader?.start('Enviando respuesta…');
      try {
        await save();
        if (await recover()) return;
        status.textContent = "Enviando respuesta…";
        const { response, data } = await request(new FormData(form));
        if (response.ok && data.received) {
          await confirm(data);
          return;
        }
        if (data.token) {
          token.value = data.token;
          save();
        }
        form.inert = false;
        const summary = document.getElementById("error-summary");
        summary
          .querySelectorAll("[data-client-form-error]")
          .forEach((item) => item.remove());
        const list = document.createElement("ul");
        list.className = "errorlist";
        list.dataset.clientFormError = "";
        for (const [name, errors] of Object.entries(data.errors || {})) {
          const input = [...form.elements].find(
            (element) => element.name === name,
          );
          for (const error of errors) {
            const item = document.createElement("li");
            const link = document.createElement(input ? "a" : "span");
            if (input) link.href = `#${input.id}`;
            const label = input
              ?.closest("[data-field]")
              ?.querySelector("legend,label")
              ?.textContent.trim();
            link.textContent = `${label ? label + ": " : ""}${error.message}`;
            item.append(link);
            list.append(item);
          }
        }
        if (list.children.length) {
          summary.append(list);
          summary.hidden = false;
          summary.focus();
        }
        status.textContent =
          data.message ||
          "Revisa los campos indicados y vuelve a enviar. Tus datos y archivos siguen en esta página.";
      } catch (error) {
        status.textContent =
          error instanceof TypeError || error.name === "AbortError"
            ? "No se pudo confirmar el envío. Conservamos tus datos en esta página. Revisa la conexión y pulsa Enviar respuesta para reintentar."
            : error.message;
      } finally {
        stopLoading?.();
        busy = false;
        submitButton.disabled = completed;
        discardButton.disabled = false;
        form.inert = false;
        form.removeAttribute("aria-busy");
      }
    },
  };
})();
