(() => {
  const root = document.getElementById("builder");
  if (!root) return;
  const navigation = root.querySelector(".builder-navigation");
  const toggle = document.getElementById("builder-index-toggle");
  const panel = document.getElementById("builder-index");
  const list = document.getElementById("builder-index-list");
  const search = document.getElementById("builder-index-search");
  const types = new Map(JSON.parse(document.getElementById("field-types").textContent));
  const display = new Set(["HEADING", "INFORMATION", "IMAGE"]);
  const normalize = (text) => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
  let state = { sections: [], active: null, busy: false };
  let entries = [];

  function close(restoreFocus = false) {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    if (restoreFocus) toggle.focus({ preventScroll: true });
  }
  function go(id) {
    if (state.busy) return;
    close();
    root.dispatchEvent(new CustomEvent("builder:navigate", { detail: id }));
  }
  function adjacent(direction) {
    const index = entries.findIndex((entry) => entry.field.id === state.active);
    if (index >= 0) return entries[index + direction];
    const sectionIndex = state.sections.findIndex((section) => section.id === state.active);
    if (sectionIndex < 0) return direction > 0 ? entries[0] : null;
    return direction > 0 ? entries.find((entry) => entry.sectionIndex >= sectionIndex)
      : entries.filter((entry) => entry.sectionIndex < sectionIndex).at(-1);
  }
  function button(label, target, className, subtitle = "") {
    const node = document.createElement("button");
    node.type = "button";
    node.className = className;
    node.dataset.editorTarget = target;
    node.disabled = state.busy;
    if (target === state.active) node.setAttribute("aria-current", "true");
    const title = document.createElement("span");
    title.textContent = label;
    node.append(title);
    if (subtitle) {
      const small = document.createElement("small");
      small.textContent = subtitle;
      node.append(small);
    }
    return node;
  }
  function renderIndex() {
    const scrollTop = list.scrollTop;
    const query = normalize(search.value.trim());
    const fragment = document.createDocumentFragment();
    if (!query || normalize("Pantalla de bienvenida").includes(query)) fragment.append(button("Pantalla de bienvenida", "welcome", "builder-index-section"));
    state.sections.forEach((section, index) => {
      const label = `Sección ${index + 1}${section.title && section.title !== "Sección sin título" ? ` · ${section.title}` : ""}`;
      const sectionMatches = normalize(label).includes(query);
      const matches = entries.filter((entry) => entry.section.id === section.id && (sectionMatches || normalize(`${entry.number} ${entry.field.label} ${entry.type}`).includes(query)));
      if (!sectionMatches && !matches.length) return;
      fragment.append(button(label, section.id, "builder-index-section", `${section.fields.length} elementos`));
      matches.forEach((entry) => fragment.append(button(
        `${entry.number ? `${entry.number}. ` : ""}${entry.field.label || "Sin título"}`,
        entry.field.id, "builder-index-question", entry.type,
      )));
    });
    document.getElementById("builder-index-empty").hidden = fragment.childNodes.length !== 0;
    list.replaceChildren(fragment);
    list.scrollTop = scrollTop;
  }
  function update() {
    let number = 0;
    entries = state.sections.flatMap((section, sectionIndex) => section.fields.map((field) => {
      const kind = field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio"
        ? field.configuration.additional_text ? "DROPDOWN_EXTRA" : field.configuration.searchable ? "DROPDOWN_SEARCH" : "DROPDOWN"
        : field.field_type;
      return { field, section, sectionIndex, number: display.has(field.field_type) ? null : ++number, type: types.get(kind) || kind };
    }));
    const current = entries.find((entry) => entry.field.id === state.active);
    const selectedSection = current?.section || state.sections.find((section) => section.id === state.active);
    document.getElementById("builder-index-count").textContent = `${state.sections.length} secciones · ${number} preguntas`;
    const sectionLabel = document.getElementById("builder-location-section");
    const questionLabel = document.getElementById("builder-location-question");
    sectionLabel.textContent = selectedSection ? `Sección ${state.sections.indexOf(selectedSection) + 1} de ${state.sections.length}${selectedSection.title !== "Sección sin título" ? ` · ${selectedSection.title}` : ""}` : "Estructura del formulario";
    questionLabel.textContent = current ? `${current.number ? `Editando pregunta ${current.number}` : "Editando bloque"} · ${current.field.label || "Sin título"}` : selectedSection ? "Selecciona una pregunta de esta sección" : "Usa el índice para ir a una pregunta";
    questionLabel.title = questionLabel.textContent;
    sectionLabel.title = sectionLabel.textContent;
    navigation.querySelector('[data-editor-step="-1"]').disabled = state.busy || !adjacent(-1);
    navigation.querySelector('[data-editor-step="1"]').disabled = state.busy || !adjacent(1);
    if (!panel.hidden) renderIndex();
  }
  root.addEventListener("builder:navigation-update", (event) => { state = event.detail; update(); });
  toggle.addEventListener("click", () => {
    if (!panel.hidden) { close(); return; }
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    renderIndex();
    positionNavigation();
    search.focus({ preventScroll: true });
    list.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest" });
  });
  document.getElementById("builder-index-close").addEventListener("click", () => close(true));
  search.addEventListener("input", () => { list.scrollTop = 0; renderIndex(); });
  navigation.addEventListener("click", (event) => {
    const target = event.target.closest("[data-editor-target]");
    if (target) go(target.dataset.editorTarget);
    const step = event.target.closest("[data-editor-step]");
    if (step && !step.disabled) {
      const next = adjacent(Number(step.dataset.editorStep));
      if (next) go(next.field.id);
    }
  });
  navigation.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) { event.preventDefault(); close(true); }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!navigation.contains(event.target)) close();
  });
  document.addEventListener("focusin", (event) => {
    if (!navigation.contains(event.target)) close();
  });
  root.addEventListener("builder:tab-change", () => close());
  const toolbar = root.querySelector(".builder-main-toolbar");
  function placeInViewport(element, left, top) {
    element.style.left = `${left}px`;
    element.style.top = `${top}px`;
    // Admin layout containment can make fixed coordinates relative to a wrapper.
    const bounds = element.getBoundingClientRect();
    element.style.left = `${left + left - bounds.left}px`;
    element.style.top = `${top + top - bounds.top}px`;
  }
  function positionNavigation() {
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || innerHeight;
    const contentLeft = root.getBoundingClientRect().left;
    const upperEdge = Math.max(top + 12, toolbar.getBoundingClientRect().bottom + 12);
    placeInViewport(navigation,
      Math.max(left + 12, Math.min(contentLeft + 12, left + width - 64)),
      Math.max(upperEdge, top + (height - navigation.offsetHeight) / 2));
    if (panel.hidden) return;
    const dock = navigation.getBoundingClientRect();
    panel.style.width = `${Math.min(380, width - 24)}px`;
    panel.style.maxHeight = `${Math.max(80, top + height - upperEdge - 12)}px`;
    const bounds = panel.getBoundingClientRect();
    placeInViewport(panel,
      Math.max(left + 12, Math.min(dock.right + 10, left + width - bounds.width - 12)),
      Math.max(upperEdge, Math.min(dock.top, top + height - bounds.height - 12)));
  }
  const syncToolbarHeights = () => {
    root.style.setProperty("--builder-toolbar-height", `${toolbar.offsetHeight}px`);
    positionNavigation();
  };
  const toolbarObserver = new ResizeObserver(syncToolbarHeights);
  toolbarObserver.observe(toolbar);
  toolbarObserver.observe(navigation);
  toolbarObserver.observe(root);
  window.addEventListener("resize", positionNavigation);
  document.addEventListener("scroll", positionNavigation, { passive: true, capture: true });
  window.visualViewport?.addEventListener("resize", positionNavigation);
  window.visualViewport?.addEventListener("scroll", positionNavigation);
  syncToolbarHeights();
})();
