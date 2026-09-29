(() => {
  const form = document.getElementById("public-form");
  if (!form || form.dataset.preview || form.dataset.edit) return;
  const ttl = 24 * 60 * 60 * 1000;
  const prefix = "forms:draft:v1:";
  const key = prefix + form.dataset.formId;
  const panel = document.getElementById("draft-panel");
  const message = document.getElementById("draft-status");
  const resumeButton = document.getElementById("draft-continue");
  const discardButton = document.getElementById("draft-discard");
  const token = form.elements.namedItem("submission_token");
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
  function removeStored() {
    try {
      localStorage.removeItem(key);
    } catch {
      storageFailure();
    }
    clearTimeout(expiryTimer);
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
        say(
          "El borrador guardado venció. Puedes completar el formulario; los próximos cambios iniciarán un nuevo borrador.",
        );
      },
      Math.max(0, draft.updatedAt + ttl - Date.now()),
    );
  }
  function store() {
    if (!draft || !available) return;
    try {
      localStorage.setItem(key, JSON.stringify(draft));
      armExpiry();
    } catch {
      storageFailure();
    }
  }
  function save(changed = false) {
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
    store();
    if (available)
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
      confirm(result.data);
      return true;
    }
    token.value = result.data.token;
    if (draft) {
      draft.token = token.value;
      store();
    }
    return false;
  }
  function confirm(data) {
    completed = true;
    removeStored();
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
    }
  });
  discardButton.addEventListener("click", () => {
    if (busy) return;
    removeStored();
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
      try {
        const item = JSON.parse(localStorage.getItem(storedKey));
        if (
          !item ||
          !Number.isFinite(item.updatedAt) ||
          item.updatedAt > Date.now() ||
          Date.now() - item.updatedAt >= ttl
        )
          localStorage.removeItem(storedKey);
      } catch {
        localStorage.removeItem(storedKey);
      }
    }
    draft = JSON.parse(localStorage.getItem(key));
    if (
      draft &&
      (!draft.answers ||
        typeof draft.answers !== "object" ||
        typeof draft.token !== "string")
    ) {
      removeStored();
      draft = null;
    }
  } catch {
    storageFailure();
  }
  if (draft && form.dataset.bound !== "true") {
    pending = true;
    form.inert = true;
    armExpiry();
    resumeButton.hidden = false;
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
      save();
      busy = true;
      submitButton.disabled = true;
      discardButton.disabled = true;
      form.inert = true;
      form.setAttribute("aria-busy", "true");
      status.textContent = "Comprobando el envío…";
      try {
        if (await recover()) return;
        status.textContent = "Enviando respuesta…";
        const { response, data } = await request(new FormData(form));
        if (response.ok && data.received) {
          confirm(data);
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
        busy = false;
        submitButton.disabled = completed;
        discardButton.disabled = false;
        form.inert = false;
        form.removeAttribute("aria-busy");
      }
    },
  };
})();
