(() => {
  document.querySelectorAll(".response-action-menu").forEach((menu) => {
    menu.addEventListener("toggle", (event) => {
      if (event.newState !== "open") return;
      const button = document.querySelector(`[popovertarget="${menu.id}"]`);
      const rect = button.getBoundingClientRect();
      menu.style.left = `${Math.max(8, Math.min(rect.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
      menu.style.top = `${Math.max(8, rect.bottom + menu.offsetHeight + 8 < innerHeight ? rect.bottom + 6 : rect.top - menu.offsetHeight - 6)}px`;
    });
  });
  document.addEventListener("click", (event) => {
    const filters = document.querySelector(".response-filters[open]");
    if (filters && !filters.contains(event.target)) filters.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") document.querySelectorAll(".response-filters[open]").forEach((item) => { item.open = false; });
  });
  const selection = document.getElementById("response-selection-form");
  if (selection) {
    const boxes = [...selection.querySelectorAll('[name="selected"]')];
    const all = document.getElementById("response-select-all");
    const updateSelection = () => {
      const count = boxes.filter((box) => box.checked).length;
      all.checked = boxes.length > 0 && count === boxes.length;
      all.indeterminate = count > 0 && count < boxes.length;
      document.getElementById("response-selection-count").textContent = count ? `${count} seleccionadas` : "Selecciona respuestas para descargarlas";
      document.getElementById("response-export-selected").disabled = !count;
    };
    all.addEventListener("change", () => { boxes.forEach((box) => { box.checked = all.checked; }); updateSelection(); });
    boxes.forEach((box) => box.addEventListener("change", updateSelection));
    updateSelection();
  }
  const expandAnchor = () => {
    if (["#response-history", "#response-flags"].includes(location.hash)) {
      const section = document.querySelector(location.hash);
      if (section) section.open = true;
    }
  };
  expandAnchor();
  window.addEventListener("hashchange", expandAnchor);
  const updateReason = (form) => {
    const required = form.elements.status.value === "REJECTED";
    form.elements.note.required = required;
    form.querySelector("[data-note-label]").textContent = required ? "Motivo del rechazo *" : "Nota sobre el cambio";
    const submit = form.querySelector('[type="submit"]');
    submit.textContent = form.elements.status.selectedOptions[0]?.textContent || "Selecciona una acción";
    submit.classList.toggle("review-danger", required);
  };
  document.querySelectorAll("[data-review-form]").forEach((form) => {
    form.elements.status.addEventListener("change", () => updateReason(form));
    updateReason(form);
  });
  const dialog = document.getElementById("review-dialog");
  if (!dialog) return;
  const form = document.getElementById("board-review-form");
  const error = document.getElementById("review-error");
  const reload = document.getElementById("review-reload");
  const transitions = JSON.parse(document.getElementById("review-transitions").textContent);
  let pending = false, opener = null;
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-review-url]");
    if (!button || pending) return;
    const menu = button.closest(".response-action-menu");
    opener = menu ? document.querySelector(`[popovertarget="${menu.id}"]`) : button;
    if (menu?.matches(":popover-open")) menu.hidePopover();
    form.reset();
    form.action = button.dataset.reviewUrl;
    form.elements.revision.value = button.dataset.revision;
    form.elements.status.replaceChildren(...transitions[button.dataset.status].map(([value, label]) => new Option(label, value)));
    if (button.dataset.reviewTarget) form.elements.status.value = button.dataset.reviewTarget;
    document.getElementById("review-dialog-response").textContent = button.dataset.title;
    error.hidden = reload.hidden = true;
    reload.href = location.href;
    updateReason(form);
    dialog.showModal();
  });
  dialog.querySelectorAll("[data-close-review]").forEach((button) => button.addEventListener("click", () => { if (!pending) dialog.close(); }));
  dialog.addEventListener("cancel", (event) => { if (pending) event.preventDefault(); });
  dialog.addEventListener("close", () => opener?.focus());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    const data = new FormData(form);
    pending = true;
    error.hidden = reload.hidden = true;
    const controls = [...dialog.querySelectorAll("button,input,select,textarea")];
    controls.forEach((control) => { control.disabled = true; });
    const submit = form.querySelector('[type="submit"]');
    submit.textContent = "Guardando…";
    try {
      const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } });
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("No se pudo guardar. Revisa tu sesión y actualiza el tablero.");
      const payload = await response.json();
      if (!response.ok) {
        reload.hidden = response.status !== 409;
        throw new Error(Object.values(payload.errors || {}).flat().map((item) => item.message).join(" ") || "No se pudo cambiar el estado.");
      }
      location.reload();
    } catch (failure) {
      error.textContent = failure.message || "No se pudo guardar. Vuelve a intentarlo.";
      error.hidden = false;
    } finally {
      pending = false;
      controls.forEach((control) => { control.disabled = false; });
      updateReason(form);
    }
  });
})();
