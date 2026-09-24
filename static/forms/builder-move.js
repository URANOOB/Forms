(() => {
  const root = document.getElementById("builder");
  if (!root) return;
  const container = document.getElementById("builder-sections");
  let state = { sections: [], busy: false }, drag = null, frame = null, suppressClickUntil = 0;
  let originButton = null, movingId = null, noticeTimer = null;
  const sectionLabel = (section) => `Sección ${state.sections.indexOf(section) + 1}${section.title && section.title !== "Sección sin título" ? ` · ${section.title}` : ""}`;
  const dialog = document.createElement("dialog");
  dialog.className = "builder-move-dialog";
  dialog.setAttribute("aria-labelledby", "builder-move-title");
  dialog.innerHTML = `<header><div><h2 id="builder-move-title">Mover componente</h2><p data-move-name></p></div><button type="button" data-move-close aria-label="Cerrar"><span class="material-symbols-outlined" aria-hidden="true">close</span></button></header><form method="dialog"><label for="builder-move-section">Sección de destino</label><select id="builder-move-section"></select><label for="builder-move-position">Posición</label><select id="builder-move-position"></select><p class="move-help">Se conservarán las opciones y las condiciones del componente.</p><p data-move-error role="alert" hidden></p><footer><button type="button" data-move-close>Cancelar</button><button type="submit" class="move-confirm">Mover componente</button></footer></form>`;
  root.append(dialog);
  const sectionSelect = dialog.querySelector("#builder-move-section");
  const positionSelect = dialog.querySelector("#builder-move-position");
  const errorBox = dialog.querySelector("[data-move-error]");
  const notice = document.createElement("div");
  notice.className = "builder-move-notice";
  notice.setAttribute("role", "status");
  notice.setAttribute("aria-live", "polite");
  notice.hidden = true;
  root.append(notice);
  function announce(text) {
    clearTimeout(noticeTimer);
    notice.textContent = text;
    notice.hidden = false;
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 6500);
  }
  function requestMove(fieldId, sectionId, beforeId) {
    const detail = { fieldId, sectionId, beforeId };
    root.dispatchEvent(new CustomEvent("builder:move-field", { detail }));
    if (detail.moved) announce(`Componente movido a ${sectionLabel(state.sections.find((section) => section.id === sectionId))}. Puedes deshacer el cambio.`);
    return detail;
  }
  function populatePositions() {
    const section = state.sections.find((item) => item.id === sectionSelect.value);
    positionSelect.replaceChildren();
    (section?.fields || []).filter((field) => field.id !== movingId).forEach((field) => {
      positionSelect.add(new Option(`Antes de: ${field.label || "Componente sin título"}`, field.id));
    });
    positionSelect.add(new Option("Al final de la sección", ""));
    positionSelect.value = "";
    errorBox.hidden = true;
  }
  function openMove(button) {
    if (state.busy || root.dataset.archived === "true") return;
    const id = button.closest("[data-field]")?.dataset.field;
    const source = state.sections.find((section) => section.fields.some((field) => field.id === id));
    if (!source) return;
    movingId = id;
    originButton = button.closest(".question-more-picker")?.querySelector('[data-action="toggle-type-menu"]') || button;
    root.dispatchEvent(new Event("builder:close-menus"));
    const index = source.fields.findIndex((field) => field.id === id);
    dialog.querySelector("[data-move-name]").textContent = source.fields[index].label || "Componente sin título";
    sectionSelect.replaceChildren();
    state.sections.forEach((section) => sectionSelect.add(new Option(sectionLabel(section), section.id)));
    sectionSelect.value = source.id;
    populatePositions();
    positionSelect.value = source.fields[index + 1]?.id || "";
    dialog.showModal();
    sectionSelect.focus({ preventScroll: true });
  }
  sectionSelect.addEventListener("change", populatePositions);
  dialog.querySelectorAll("[data-move-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => {
    if (originButton?.isConnected) originButton.focus({ preventScroll: true });
    originButton = null;
  });
  dialog.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    const result = requestMove(movingId, sectionSelect.value, positionSelect.value || null);
    if (result.error) { errorBox.textContent = result.error; errorBox.hidden = false; }
    else {
      dialog.close();
      container.querySelector(`[data-field="${CSS.escape(movingId)}"] .question-drag-handle`)?.focus({ preventScroll: true });
    }
  });

  function scrollContainer(element) {
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (parent === document.scrollingElement) break;
      if (/(auto|scroll)/.test(getComputedStyle(parent).overflowY) && parent.scrollHeight > parent.clientHeight) return parent;
    }
    return document.scrollingElement;
  }
  function locate() {
    if (!drag?.started) return;
    drag.ghost.style.left = `${Math.max(8, Math.min(drag.x + 16, innerWidth - drag.ghost.offsetWidth - 8))}px`;
    drag.ghost.style.top = `${Math.max(8, Math.min(drag.y + 18, innerHeight - drag.ghost.offsetHeight - 8))}px`;
    const section = document.elementFromPoint(drag.x, drag.y)?.closest(".builder-section");
    drag.target = null;
    drag.marker.hidden = true;
    container.querySelectorAll(".is-drop-section").forEach((node) => node.classList.remove("is-drop-section"));
    if (!section || !container.contains(section)) {
      drag.ghost.textContent = "Suelta el componente en una sección";
      return;
    }
    section.classList.add("is-drop-section");
    const cards = [...section.querySelectorAll(".question-card")].filter((card) => card.dataset.field !== drag.fieldId);
    const before = cards.find((card) => { const rect = card.getBoundingClientRect(); return drag.y < rect.top + rect.height / 2; });
    const rect = (before || cards.at(-1) || section.querySelector('[data-action="add-question"]')).getBoundingClientRect();
    const y = before ? rect.top - 4 : cards.length ? rect.bottom + 4 : rect.top;
    drag.target = { sectionId: section.dataset.section, beforeId: before?.dataset.field || null };
    drag.marker.style.cssText = `top:${y}px;left:${rect.left}px;width:${rect.width}px`;
    drag.marker.hidden = false;
    const destination = state.sections.find((item) => item.id === section.dataset.section);
    drag.ghost.textContent = `Mover a ${sectionLabel(destination)}`;
  }
  function autoScroll() {
    if (!drag?.started) return;
    const scroller = drag.scroller;
    const rect = scroller === document.scrollingElement ? { top: 0, bottom: innerHeight } : scroller.getBoundingClientRect();
    const navigation = root.querySelector(".builder-main-toolbar").getBoundingClientRect();
    const top = Math.max(rect.top, 0, navigation.bottom > 0 && navigation.top < innerHeight ? navigation.bottom : 0);
    const bottom = Math.min(rect.bottom, innerHeight);
    const distance = drag.y < top + 65 ? -Math.min(20, (top + 65 - drag.y) / 3)
      : drag.y > bottom - 65 ? Math.min(20, (drag.y - bottom + 65) / 3) : 0;
    if (distance) scroller.scrollBy({ top: distance, behavior: "instant" });
    locate();
    frame = requestAnimationFrame(autoScroll);
  }
  function finish(cancel = false) {
    if (!drag) return;
    const previous = drag;
    drag = null;
    cancelAnimationFrame(frame);
    if (previous.handle.hasPointerCapture(previous.pointerId)) previous.handle.releasePointerCapture(previous.pointerId);
    previous.card.classList.remove("is-dragging");
    root.classList.remove("is-moving-component");
    container.querySelectorAll(".is-drop-section").forEach((node) => node.classList.remove("is-drop-section"));
    previous.ghost?.remove();
    previous.marker?.remove();
    if (!previous.started) return;
    suppressClickUntil = Date.now() + 400;
    if (!cancel && previous.target) {
      const result = requestMove(previous.fieldId, previous.target.sectionId, previous.target.beforeId);
      if (result.error) announce(result.error);
      if (result.moved) return;
    }
    previous.handle.focus({ preventScroll: true });
    if (cancel) announce("Movimiento cancelado.");
  }
  root.addEventListener("builder:navigation-update", (event) => {
    state = event.detail;
    if (drag && (state.busy || !drag.handle.isConnected)) finish(true);
  });
  root.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest(".question-drag-handle");
    if (!handle || event.button !== 0 || !event.isPrimary || state.busy || root.dataset.archived === "true") return;
    event.preventDefault();
    const card = handle.closest("[data-field]");
    drag = { handle, card, fieldId: card.dataset.field, pointerId: event.pointerId, x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, started: false, scroller: scrollContainer(card) };
    handle.setPointerCapture(event.pointerId);
  });
  root.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag.x = event.clientX; drag.y = event.clientY;
    if (!drag.started && Math.hypot(drag.x - drag.startX, drag.y - drag.startY) >= 6) {
      drag.started = true;
      drag.card.classList.add("is-dragging");
      root.classList.add("is-moving-component");
      drag.ghost = document.createElement("div");
      drag.ghost.className = "builder-drag-ghost";
      drag.ghost.textContent = "Suelta el componente en una sección";
      drag.marker = document.createElement("div");
      drag.marker.className = "builder-drop-marker";
      root.append(drag.ghost, drag.marker);
      autoScroll();
    }
  });
  root.addEventListener("pointerup", (event) => {
    if (drag?.pointerId !== event.pointerId) return;
    drag.x = event.clientX; drag.y = event.clientY;
    locate();
    finish();
  });
  root.addEventListener("pointercancel", (event) => { if (drag?.pointerId === event.pointerId) finish(true); });
  root.addEventListener("lostpointercapture", (event) => { if (drag?.pointerId === event.pointerId) finish(true); });
  window.addEventListener("blur", () => finish(true));
  root.addEventListener("builder:tab-change", () => finish(true));
  document.addEventListener("keydown", (event) => {
    if (drag && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(true); }
  }, true);
  root.addEventListener("click", (event) => {
    if (Date.now() < suppressClickUntil && event.detail > 0) { event.preventDefault(); event.stopImmediatePropagation(); return; }
    const button = event.target.closest('[data-action="move-question"]');
    if (button && !button.disabled) { event.preventDefault(); event.stopPropagation(); openMove(button); }
  }, true);
})();
