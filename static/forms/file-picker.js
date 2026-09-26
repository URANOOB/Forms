(() => {
  const form = document.getElementById("public-form");
  if (!form || typeof DataTransfer === "undefined") return;
  const accessible = document.body.hasAttribute("data-public-accessibility");
  try { new DataTransfer(); } catch { return; }
  const widgets = [];
  const sizeLabel = (bytes) => bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toLocaleString("es-CO", { maximumFractionDigits: 1 })} MB`;
  const extension = (file) => file.name.split(".").pop().toLowerCase();
  const uploadIcon = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4m-4 4 4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg>';
  const create = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  for (const input of form.querySelectorAll('input[type="file"][data-max-files]')) {
    const field = input.closest("[data-field]");
    const root = create("div", "file-picker");
    const zone = create("div", "file-dropzone");
    const icon = create("span", "file-upload-icon");
    icon.innerHTML = uploadIcon;
    const title = create("strong", "file-drop-title", "Arrastre sus documentos aquí");
    const instruction = create("span", "file-drop-instruction", "o seleccione los archivos desde su dispositivo");
    const browse = create("span", "file-browse-label", "Seleccionar archivos");
    const status = create("p", "file-picker-status");
    status.setAttribute("role", "status");
    const error = create("p", "file-picker-error");
    error.setAttribute("role", "alert");
    if (accessible) error.id = `${input.id}-upload-error`;
    error.hidden = true;
    const cards = create("div", "file-cards");
    const note = create("p", "file-picker-note", "Revise y confirme cada archivo. Se enviarán al enviar el formulario.");
    const hintId = `${input.id}-upload-note`;
    note.id = hintId;
    input.setAttribute("aria-describedby", [input.getAttribute("aria-describedby"), hintId].filter(Boolean).join(" "));
    if (accessible) {
      input.setAttribute("aria-describedby", `${input.getAttribute("aria-describedby")} ${error.id}`);
      // Keep the visible action in the accessible name for voice control.
      const label = input.labels?.[0];
      if (label) {
        label.id ||= `${input.id}-label`;
        browse.id = `${input.id}-browse`;
        input.setAttribute("aria-labelledby", `${label.id} ${browse.id}`);
      }
    }
    input.before(root);
    zone.append(icon, title, instruction, browse, input);
    root.append(zone, status, error, cards, note);
    input.classList.add("file-picker-native");
    const widget = { input, root, zone, entries: [] };
    widgets.push(widget);
    const retainedCount = () => field.querySelectorAll("[data-stored-file]:not(:checked)").length;
    const maxFiles = Number(input.dataset.maxFiles);
    const maxBytes = Number(input.dataset.maxBytes);
    const accepted = input.accept.split(",").map((value) => value.trim().replace(/^\./, "").toLowerCase());
    const revoke = (entry) => { if (entry.url) URL.revokeObjectURL(entry.url); };
    const readyFiles = () => {
      const transfer = new DataTransfer();
      widget.entries.filter((entry) => entry.confirmed).forEach((entry) => transfer.items.add(entry.file));
      input.files = transfer.files;
      input.dataset.uploadPending = String(widget.entries.filter((entry) => !entry.confirmed).length);
    };
    function sync() {
      readyFiles();
      const pending = widget.entries.filter((entry) => !entry.confirmed).length;
      const ready = widget.entries.length - pending;
      status.textContent = widget.entries.length ? `${ready} ${ready === 1 ? "archivo listo" : "archivos listos"} para enviar${pending ? ` · ${pending} por confirmar` : ""}` : "";
      note.hidden = !widget.entries.length;
      root.querySelectorAll("button").forEach((button) => { button.disabled = input.disabled; });
      root.classList.toggle("is-disabled", input.disabled);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function preview(entry) {
      const box = create("div", "file-preview");
      const ext = extension(entry.file);
      const imageTypes = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
      if (imageTypes[ext] || ext === "pdf") {
        // Force an inert, expected media type instead of trusting the supplied MIME.
        entry.url = URL.createObjectURL(new Blob([entry.file], { type: imageTypes[ext] || "application/pdf" }));
        if (imageTypes[ext]) {
          const image = document.createElement("img");
          image.alt = `Vista previa de ${entry.file.name}`;
          image.src = entry.url;
          image.addEventListener("error", () => { box.replaceChildren(create("span", "file-preview-fallback", "No se pudo mostrar la imagen.")); });
          box.append(image);
        } else if (accessible) {
          // Browser PDF plugins can trap keyboard focus. The explicit link below
          // still opens the original preview in a separate tab.
          box.append(create("span", "file-preview-fallback", "Documento PDF. Usa «Ver documento» para abrirlo en otra pestaña."));
        } else {
          const documentPreview = document.createElement("object");
          documentPreview.type = "application/pdf";
          documentPreview.data = `${entry.url}#toolbar=0&navpanes=0&view=FitH`;
          documentPreview.setAttribute("aria-label", `Vista previa de ${entry.file.name}`);
          documentPreview.append(create("span", "file-preview-fallback", "Documento PDF. Use «Ver documento» para abrirlo."));
          box.append(documentPreview);
        }
      } else if (["txt", "csv"].includes(ext)) {
        const text = create("pre", "file-text-preview", "Cargando vista previa…");
        box.append(text);
        entry.file.slice(0, 4096).text().then((value) => {
          text.textContent = value || "El archivo no contiene texto.";
        }).catch(() => { text.textContent = "No se pudo mostrar la vista previa."; });
      } else {
        box.classList.add("file-preview-generic");
        box.append(create("span", "file-extension", ext.toUpperCase()), create("span", "file-preview-fallback", "Vista previa no disponible para este formato."));
      }
      return box;
    }
    function addCard(entry) {
      const card = create("article", "file-card");
      const details = create("div", "file-details");
      const name = create("h3", "file-name", entry.file.name);
      const metadata = create("p", "file-meta", `${extension(entry.file).toUpperCase()} · ${sizeLabel(entry.file.size)}`);
      const state = create("p", "file-state", "Pendiente de confirmación");
      const actions = create("div", "file-actions");
      const confirm = create("button", "file-confirm", "Confirmar archivo");
      confirm.type = "button";
      confirm.setAttribute("aria-label", `${accessible ? "Confirmar archivo" : "Confirmar"} ${entry.file.name}`);
      const remove = create("button", "file-remove", "Quitar");
      remove.type = "button";
      remove.setAttribute("aria-label", `Quitar ${entry.file.name}`);
      card.append(preview(entry));
      actions.append(confirm);
      if (entry.url) {
        const link = create("a", "file-open", "Ver documento");
        link.href = entry.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.setAttribute("aria-label", `${accessible ? "Ver documento" : "Ver"} ${entry.file.name} en otra pestaña`);
        actions.append(link);
      }
      actions.append(remove);
      details.append(name, metadata, state, actions);
      card.append(details);
      cards.append(card);
      confirm.addEventListener("click", () => {
        if (input.disabled) return;
        if (widget.entries.length + retainedCount() > maxFiles) {
          error.textContent = `Puede adjuntar hasta ${maxFiles} archivo(s), incluidos los ya guardados.`;
          error.hidden = false;
          return;
        }
        entry.confirmed = true;
        card.classList.add("is-confirmed");
        state.textContent = "✓ Confirmado · Listo para enviar";
        confirm.hidden = true;
        error.hidden = true;
        sync();
        remove.focus({ preventScroll: true });
      });
      remove.addEventListener("click", () => {
        if (input.disabled) return;
        widget.entries = widget.entries.filter((item) => item !== entry);
        revoke(entry);
        card.remove();
        error.hidden = true;
        sync();
        input.focus({ preventScroll: true });
      });
    }
    function receive(files) {
      if (input.disabled) return;
      const errors = [];
      for (const file of files) {
        if (!accepted.includes(extension(file))) { errors.push(`${file.name}: formato no permitido.`); continue; }
        if (!file.size) { errors.push(`${file.name}: el archivo está vacío.`); continue; }
        if (file.size > maxBytes) { errors.push(`${file.name}: supera el límite de ${sizeLabel(maxBytes)}.`); continue; }
        if (widget.entries.some((entry) => entry.file.name === file.name && entry.file.size === file.size && entry.file.lastModified === file.lastModified)) continue;
        if (widget.entries.length + retainedCount() >= maxFiles) { errors.push(`Puede adjuntar hasta ${maxFiles} archivo(s), incluidos los ya guardados.`); break; }
        const entry = { file, confirmed: false, url: null };
        widget.entries.push(entry);
        addCard(entry);
      }
      error.textContent = errors.join(" ");
      error.hidden = !errors.length;
      sync();
    }
    // Native selections replace FileList; maintain confirmed attachments separately.
    input.addEventListener("input", (event) => { if (event.isTrusted) event.stopPropagation(); });
    input.addEventListener("change", (event) => { if (event.isTrusted) receive([...input.files]); });
    let depth = 0;
    zone.addEventListener("dragenter", (event) => { event.preventDefault(); if (!input.disabled) { depth++; zone.classList.add("is-dragging"); } });
    zone.addEventListener("dragover", (event) => { event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = input.disabled ? "none" : "copy"; });
    zone.addEventListener("dragleave", (event) => { event.preventDefault(); depth = Math.max(0, depth - 1); if (!depth) zone.classList.remove("is-dragging"); });
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      depth = 0;
      zone.classList.remove("is-dragging");
      if (!input.disabled) receive([...(event.dataTransfer?.files || [])]);
    });
    form.addEventListener("reset", () => {
      widget.entries.forEach(revoke);
      widget.entries = [];
      cards.replaceChildren();
      error.hidden = true;
      setTimeout(sync, 0);
    });
    window.addEventListener("pagehide", (event) => { if (!event.persisted) widget.entries.forEach(revoke); });
    if (input.files.length) receive([...input.files]);
    else { note.hidden = true; input.dataset.uploadPending = "0"; }
  }
  new MutationObserver(() => {
    for (const { input, root } of widgets) {
      root.classList.toggle("is-disabled", input.disabled);
      root.querySelectorAll("button").forEach((button) => { if (button.disabled !== input.disabled) button.disabled = input.disabled; });
    }
  }).observe(form, { attributes: true, subtree: true, attributeFilter: ["disabled"] });
})();
