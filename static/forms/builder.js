(() => {
  const root = document.getElementById("builder");
  if (!root) return;
  let state = JSON.parse(document.getElementById("builder-data").textContent);
  const welcomeSettings = () => state.welcome ||= {};
  const types = JSON.parse(document.getElementById("field-types").textContent);
  const themeConfig = JSON.parse(document.getElementById("theme-config").textContent);
  const container = document.getElementById("builder-sections");
  const status = document.getElementById("save-status");
  const message = document.getElementById("builder-message");
  const csrf = root.querySelector("[name=csrfmiddlewaretoken]").value;
  const display = new Set(["HEADING", "INFORMATION", "IMAGE"]);
  const choices = new Set(["SINGLE_CHOICE", "MULTIPLE_CHOICE"]);
  const grids = new Set(["GRID_SINGLE", "GRID_MULTIPLE"]);
  const files = new Set(["FILE", "DOCUMENT"]);
  const questionTypeIcons = {
    SHORT_TEXT: "short_text", LONG_TEXT: "subject", SINGLE_CHOICE: "radio_button_checked",
    MULTIPLE_CHOICE: "check_box", DROPDOWN: "arrow_drop_down_circle", DROPDOWN_SEARCH: "search", DROPDOWN_EXTRA: "edit_note", FILE: "cloud_upload",
    LINEAR_SCALE: "linear_scale", RATING: "star", GRID_SINGLE: "apps",
    GRID_MULTIPLE: "grid_on", DATE: "calendar_today", TIME: "schedule",
    EMAIL: "mail", PHONE: "call", NUMBER: "tag", BOOLEAN: "toggle_on",
    HEADING: "title", INFORMATION: "info", IMAGE: "image",
  };
  let openTypeMenu = null;
  let dirty = false,
    busy = false,
    active = null,
    imageTarget = null;
  const expandedBranches = new Map();
  const branchDrafts = new Map();
  const expandedAdditional = new Map();
  const expandedDescriptions = new Map();
  const undoStack = [], redoStack = [];
  // Only editor content belongs in history; server versions and access stay current.
  const snapshot = () => JSON.stringify({
    title: state.title, description: state.description,
    appearance: state.appearance || {}, welcome: state.welcome || {},
    sections: state.sections, rules: state.rules,
  });
  let currentSnapshot = snapshot(), savedSnapshot = currentSnapshot;
  let lastEdit = null;
  const uid = () =>
    globalThis.crypto?.randomUUID?.() ||
    `local_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (ch) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[ch],
    );
  const fields = () => state.sections.flatMap((section) => section.fields);
  const findField = (id) => fields().find((field) => field.id === id);
  const catalogChildren = (field) => fields().filter((item) => item.configuration.option_filter?.source === field.stable_key);
  const findSection = (id) =>
    state.sections.find((section) => section.id === id);
  const selectedSection = () =>
    state.sections.find(
      (section) =>
        section.id === active ||
        section.fields.some((field) => field.id === active),
    ) || state.sections.at(-1);
  const icon = (action, symbol, label, extra = "") =>
    `<button type="button" class="icon-button" data-action="${action}" aria-label="${esc(label)}" title="${esc(label)}" ${extra}><span class="material-symbols-outlined" aria-hidden="true">${symbol}</span></button>`;
  const options = (items, value) =>
    items
      .map(
        ([key, label]) =>
          `<option value="${esc(key)}" ${String(value) === String(key) ? "selected" : ""}>${esc(label)}</option>`,
      )
      .join("");
  function notify(text, error = false) {
    message.textContent = text;
    message.hidden = !text;
    message.style.color = error ? "" : "#384471";
  }
  function updateHistoryButtons() {
    const unavailable = busy || root.dataset.archived === "true";
    root.querySelector('[data-action="undo"]').disabled = unavailable || !undoStack.length;
    root.querySelector('[data-action="redo"]').disabled = unavailable || !redoStack.length;
  }
  function updateDirtyStatus() {
    dirty = currentSnapshot !== savedSnapshot;
    status.textContent = dirty ? "Cambios sin guardar"
      : root.dataset.base ? "Formulario guardado" : "Formulario sin guardar";
    updateNavigation();
  }
  function updateNavigation() {
    root.dispatchEvent(new CustomEvent("builder:navigation-update", { detail: {
      sections: state.sections, active, dirty, busy,
    } }));
  }
  function changed(input = null) {
    const next = snapshot();
    if (next === currentSnapshot) return;
    const now = Date.now();
    if (!input || lastEdit?.input !== input || now - lastEdit.time > 750) {
      undoStack.push(currentSnapshot);
      if (undoStack.length > 100) undoStack.shift();
    }
    lastEdit = input ? { input, time: now } : null;
    redoStack.length = 0;
    currentSnapshot = next;
    updateDirtyStatus();
    updateHistoryButtons();
  }
  function restoreHistory(action) {
    const source = action === "undo" ? undoStack : redoStack;
    const destination = action === "undo" ? redoStack : undoStack;
    if (busy || root.dataset.archived === "true" || !source.length) return;
    destination.push(currentSnapshot);
    currentSnapshot = source.pop();
    Object.assign(state, JSON.parse(currentSnapshot));
    lastEdit = null;
    if (!findField(active) && !findSection(active)) active = null;
    document.getElementById("form-title").value = state.title;
    notify("");
    render();
    updateDirtyStatus();
    updateHistoryButtons();
  }
  function newSection() {
    return {
      id: uid(),
      title: "Sección sin título",
      description: "",
      configuration: { hide_header: true },
      fields: [],
    };
  }
  function newField(kind = "SINGLE_CHOICE") {
    return {
      id: uid(),
      stable_key: `q_${uid().replaceAll("-", "_").replaceAll(".", "_")}`,
      label:
        kind === "IMAGE"
          ? "Descripción de la imagen"
          : kind === "HEADING"
            ? "Título sin editar"
            : "Pregunta sin título",
      help_text: "",
      field_type: kind,
      required: false,
      placeholder: "",
      configuration: kind === "SINGLE_CHOICE" ? { widget: "radio" } : {},
      validation: {},
      image: null,
      image_url: "",
      options: choices.has(kind)
        ? [{ label: "Opción 1", value: uid(), is_active: true }]
        : [],
    };
  }
  const canBranch = (field) =>
    field.field_type === "BOOLEAN" || choices.has(field.field_type);
  function simpleBranch(rule, field) {
    return (
      rule.source === field.id &&
      rule.action === "SHOW" &&
      (rule.operator === "IS_NOT_EMPTY" || rule.operator ===
        (field.field_type === "MULTIPLE_CHOICE" ? "CONTAINS" : "EQUALS")) &&
      (!rule.group_key ||
        state.rules.filter((r) => r.group_key === rule.group_key).length === 1)
    );
  }
  function additionalToggle(field) {
    const expanded = expandedAdditional.get(field.id) ?? true;
    return `<button type="button" class="additional-toggle" data-action="toggle-additional-settings" aria-expanded="${expanded}" aria-controls="additional-settings-${esc(field.id)}"><span class="additional-toggle-icon material-symbols-outlined" aria-hidden="true">edit_note</span><span class="additional-toggle-copy"><strong>Campo adicional</strong><small>Configura cuándo aparece y qué información solicitar.</small></span><span class="additional-toggle-chevron material-symbols-outlined" aria-hidden="true">expand_more</span></button>`;
  }
  function branchTargets(field) {
    let number = 0;
    return state.sections.flatMap((section, index) => {
      const context = `Sección ${index + 1} · ${section.title || "Sin título"}`;
      return [
        ...(!section.fields.includes(field) && section.fields.length
          ? [{ value: `s:${section.id}`, label: context, context: `${section.fields.length} componentes`, type: "SECTION" }]
          : []),
        ...section.fields.map((item) => ({
          value: `f:${item.id}`, label: `${++number}. ${item.label || "Sin título"}`,
          context, type: editorType(item),
        })).filter((item) => item.value !== `f:${field.id}`),
      ];
    });
  }
  const branchTypeLabel = (type) => type === "SECTION" ? "Sección completa"
    : types.find(([key]) => key === type)?.[1] || type;
  const branchAnswer = (rule) => rule.operator === "IS_NOT_EMPTY" ? "any" : JSON.stringify(rule.expected);
  const normalizeBranchSearch = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
  function answerBranches(field) {
    if (!canBranch(field)) return "";
    const branches = state.rules.map((rule, index) => ({ rule, index }))
      .filter(({ rule }) => simpleBranch(rule, field));
    if (!(expandedBranches.get(field.id) ?? branches.length > 0)) return `<div id="branches-${esc(field.id)}" hidden></div>`;
    if (!branchDrafts.has(field.id)) branchDrafts.set(field.id, []);
    const drafts = branchDrafts.get(field.id);
    if (!branches.length && !drafts.length) drafts.push({ id: uid(), answer: "any" });
    const answers = [["any", "Cualquier opción"], ...(field.field_type === "BOOLEAN"
      ? [[true, "Sí"], [false, "No"]]
      : field.options.filter((o) => o.is_active).map((o) => [o.value, o.label]))
      .map(([value, label]) => [JSON.stringify(value), label])];
    const targets = branchTargets(field);
    const entries = [...branches, ...drafts.map((draft) => ({ draft }))];
    return `<div class="answer-branches" id="branches-${esc(field.id)}">
      <div class="branch-settings-heading"><strong>Mostrar según respuesta</strong>${icon("toggle-branches", "close", "Cerrar configuración de mostrar según respuesta")}</div>
      <p>El contenido elegido se mostrará cuando se cumpla la condición.</p>
      <div class="branch-rules">${entries.map(({ rule, index, draft }, position) => {
        const current = rule ? (rule.target_field ? `f:${rule.target_field}` : `s:${rule.target_section}`) : "";
        const selected = targets.find((target) => target.value === current);
        const answer = rule ? branchAnswer(rule) : draft.answer;
        const rowKey = draft ? `draft-${draft.id}` : `rule-${index}`;
        const availableAnswers = answers.some(([value]) => value === answer) ? answers
          : [...answers, [answer, "Opción no disponible — revise la condición"]];
        return `<div class="branch-rule" data-branch-key="${esc(rowKey)}" data-branch-rule="${rule ? index : ""}" data-branch-draft="${esc(draft?.id || "")}">
          <div class="branch-rule-heading"><strong>Regla ${position + 1}</strong><span>${draft ? "Elija un destino para completar" : "Configurada"}</span>${icon("remove-branch", "close", "Quitar regla")}</div>
          <label class="branch-source-label">Si selecciona<select data-branch-answer aria-label="Respuesta que activa la regla ${position + 1}">${options(availableAnswers, answer)}</select></label>
          <div class="branch-target-label">Entonces mostrar</div>
          <details class="branch-target-picker">
            <summary><span class="material-symbols-outlined" aria-hidden="true">${selected ? questionTypeIcons[selected.type] || "view_agenda" : "search"}</span><span>${selected ? `<strong>${esc(selected.label)}</strong><small>${esc(selected.context)} · ${esc(branchTypeLabel(selected.type))}</small>` : "Seleccionar componente…"}</span><span class="material-symbols-outlined" aria-hidden="true">expand_more</span></summary>
            <div class="branch-target-panel">
              <div class="branch-target-filters"><label>Buscar<input type="search" data-branch-search placeholder="Nombre, número o sección…" autocomplete="off"></label></div>
              <div class="branch-target-results">${targets.map((target) => `<button type="button" data-action="choose-branch-target" data-target="${esc(target.value)}" data-search="${esc(normalizeBranchSearch(`${target.label} ${target.context} ${branchTypeLabel(target.type)}`))}" aria-pressed="${target.value === current}"><span class="material-symbols-outlined" aria-hidden="true">${questionTypeIcons[target.type] || "view_agenda"}</span><span><strong>${esc(target.label)}</strong><small>${esc(target.context)} · ${esc(branchTypeLabel(target.type))}</small></span><span class="material-symbols-outlined branch-target-check" aria-hidden="true">check</span></button>`).join("")}</div>
              <p class="branch-target-count" role="status">${targets.length ? `${targets.length} destinos disponibles` : "Añada otra pregunta o sección para elegir un destino."}</p>
            </div>
          </details>
          <p class="branch-rule-error" role="alert" hidden></p>
        </div>`;
      }).join("")}</div>
      <button type="button" class="branch-add" data-action="add-branch"><span class="material-symbols-outlined" aria-hidden="true">add</span>Añadir regla</button>
      <p class="branch-hint">«Cualquier opción» se activa al responder. Puede añadir varios destinos con ＋. Las reglas con el mismo destino funcionan como alternativas: basta con cumplir una.</p>
    </div>`;
  }
  function filterBranchTargets(el) {
    const panel = el.closest(".branch-target-panel");
    const query = normalizeBranchSearch(panel.querySelector("[data-branch-search]").value.trim());
    let count = 0;
    panel.querySelectorAll("[data-target]").forEach((button) => {
      button.hidden = !button.dataset.search.includes(query);
      if (!button.hidden) count++;
    });
    panel.querySelector(".branch-target-count").textContent = count
      ? `${count} ${count === 1 ? "destino disponible" : "destinos disponibles"}`
      : "No hay coincidencias. Cambie el texto de búsqueda.";
  }
  function focusBranch(field, key, selector = "summary") {
    container.querySelector(`[data-field="${CSS.escape(field.id)}"] [data-branch-key="${CSS.escape(key)}"] ${selector}`)?.focus({ preventScroll: true });
  }
  function updateBranch(field, row, target) {
    const index = row.dataset.branchRule === "" ? null : Number(row.dataset.branchRule);
    const answer = row.querySelector("[data-branch-answer]").value;
    if (index === null && !target) {
      const draft = branchDrafts.get(field.id)?.find((item) => item.id === row.dataset.branchDraft);
      if (draft) draft.answer = answer;
      return;
    }
    const previous = index === null ? null : state.rules[index];
    const destination = target || (previous.target_field ? `f:${previous.target_field}` : `s:${previous.target_section}`);
    if (!branchTargets(field).some((item) => item.value === destination)) return;
    const [kind, id] = destination.split(":");
    const rule = {
      source: field.id,
      operator: answer === "any" ? "IS_NOT_EMPTY" : field.field_type === "MULTIPLE_CHOICE" ? "CONTAINS" : "EQUALS",
      expected: answer === "any" ? null : JSON.parse(answer), action: "SHOW",
      target_field: kind === "f" ? id : null, target_section: kind === "s" ? id : null,
      group_key: previous?.group_key || null, group_operator: previous?.group_operator || "AND",
    };
    const duplicate = state.rules.some((item, i) => i !== index && simpleBranch(item, field)
      && item.operator === rule.operator && item.expected === rule.expected
      && item.target_field === rule.target_field && item.target_section === rule.target_section);
    if (duplicate) {
      const error = row.querySelector(".branch-rule-error");
      error.textContent = "Ya existe una regla con esa respuesta y ese destino. Elija otra combinación.";
      error.hidden = false;
      if (previous) row.querySelector("[data-branch-answer]").value = branchAnswer(previous);
      return;
    }
    const key = `rule-${index ?? state.rules.length}`;
    if (index === null) {
      state.rules.push(rule);
      branchDrafts.set(field.id, branchDrafts.get(field.id).filter((draft) => draft.id !== row.dataset.branchDraft));
    } else state.rules[index] = rule;
    expandedBranches.set(field.id, true);
    changed();
    render();
    focusBranch(field, key, target ? "summary" : "[data-branch-answer]");
  }
  function editorType(field) {
    if (field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio")
      return field.configuration.additional_text ? "DROPDOWN_EXTRA" : field.configuration.searchable ? "DROPDOWN_SEARCH" : "DROPDOWN";
    return field.field_type === "DOCUMENT" ? "FILE" : field.field_type;
  }
  function typeOptions(field) {
    const value = editorType(field);
    const available = [
      "SHORT_TEXT", "LONG_TEXT", "NUMBER", "EMAIL", "PHONE", "SINGLE_CHOICE", "MULTIPLE_CHOICE", "DROPDOWN", "DROPDOWN_SEARCH", "DROPDOWN_EXTRA",
      "FILE", "LINEAR_SCALE", "RATING", "GRID_SINGLE", "GRID_MULTIPLE", "DATE", "TIME",
    ];
    // Keep existing fields accurately labelled without offering their legacy types.
    const current = !available.includes(value)
      ? `<option value="${esc(value)}" selected disabled hidden>${esc(types.find(([key]) => key === value)?.[1] || value)}</option>`
      : "";
    return current + options(available.map((key) => types.find(([type]) => type === key)), value);
  }
  function typePicker(field) {
    const value = editorType(field);
    const label = types.find(([key]) => key === value)?.[1] || value;
    const symbol = (key) => `<span class="material-symbols-outlined" aria-hidden="true">${questionTypeIcons[key] || "help_outline"}</span>`;
    const available = ["SHORT_TEXT", "LONG_TEXT", "NUMBER", "EMAIL", "PHONE", "SINGLE_CHOICE", "MULTIPLE_CHOICE", "DROPDOWN", "DROPDOWN_SEARCH", "DROPDOWN_EXTRA", "FILE", "LINEAR_SCALE", "RATING", "GRID_SINGLE", "GRID_MULTIPLE", "DATE", "TIME"];
    const menuId = `type-menu-${field.id}`;
    const importAction = `<button type="button" role="menuitem" class="catalog-menu-entry" tabindex="-1" data-open-catalog aria-haspopup="dialog" aria-controls="catalog-import"><span class="material-symbols-outlined" aria-hidden="true">table_view</span><span class="catalog-menu-copy"><strong>Crear campos desde archivo</strong><small>Elige campos y relaciones</small></span></button>`;
    return `<div class="question-type-picker"><select data-prop="field_type" hidden aria-label="Tipo de pregunta">${typeOptions(field)}</select><button type="button" class="question-type" data-action="toggle-type-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="${esc(menuId)}" aria-label="Tipo de pregunta: ${esc(label)}">${symbol(value)}<span class="question-type-label">${esc(label)}</span><span class="material-symbols-outlined" aria-hidden="true">expand_more</span></button><div id="${esc(menuId)}" class="question-type-menu" popover="manual" role="menu" aria-label="Tipo de pregunta">${available.map((key) => `<button type="button" role="menuitemradio" aria-checked="${key === value}" tabindex="-1" data-action="choose-question-type" data-type="${key}">${symbol(key)}<span>${esc(types.find(([type]) => type === key)?.[1] || key)}</span></button>${key === "DROPDOWN_EXTRA" ? importAction : ""}`).join("")}</div></div>`;
  }
  function closeTypeMenu(restoreFocus = false) {
    if (!openTypeMenu) return;
    const menu = openTypeMenu;
    openTypeMenu = null;
    const trigger = menu.parentElement.querySelector('[data-action="toggle-type-menu"]');
    menu.hidePopover();
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus({ preventScroll: true });
  }
  function positionTypeMenu() {
    if (!openTypeMenu) return;
    const menu = openTypeMenu;
    const trigger = menu.parentElement.querySelector('[data-action="toggle-type-menu"]');
    const rect = trigger.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || window.innerHeight;
    menu.style.width = `${Math.min(Math.max(rect.width, 300), width - 16)}px`;
    menu.style.maxHeight = `${Math.min(520, height - 16)}px`;
    const size = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left + 8, Math.min(rect.right - size.width, left + width - size.width - 8))}px`;
    const below = rect.bottom + 6;
    const above = rect.top - size.height - 6;
    menu.style.top = `${Math.max(top + 8, Math.min(below + size.height <= top + height - 8 ? below : above, top + height - size.height - 8))}px`;
  }
  function showTypeMenu(trigger, last = false) {
    closeTypeMenu();
    const menu = trigger.parentElement.querySelector(".question-type-menu");
    openTypeMenu = menu;
    menu.showPopover();
    trigger.setAttribute("aria-expanded", "true");
    positionTypeMenu();
    const items = [...menu.querySelectorAll("button")];
    const selected = menu.querySelector('[aria-checked="true"]');
    (last ? items.at(-1) : selected || items[0]).focus({ preventScroll: true });
    (last ? items.at(-1) : selected || items[0]).scrollIntoView({ block: "nearest" });
  }
  function descriptionVisible(field) {
    return expandedDescriptions.get(field.id) ?? Boolean(field.help_text?.trim());
  }
  function questionMoreMenu(field) {
    const id = `question-more-${field.id}`;
    const count = state.rules.filter((rule) => simpleBranch(rule, field)).length;
    const expanded = expandedBranches.get(field.id) ?? count > 0;
    return `<div class="question-more-picker"><button type="button" class="icon-button" data-action="toggle-type-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="${esc(id)}" aria-label="Más opciones del componente" title="Más opciones"><span class="material-symbols-outlined" aria-hidden="true">more_vert</span></button><div id="${esc(id)}" class="question-type-menu question-more-menu" popover="manual" role="menu" aria-label="Más opciones del componente"><button type="button" role="menuitemcheckbox" aria-checked="${descriptionVisible(field)}" aria-controls="question-description-${esc(field.id)}" tabindex="-1" data-action="toggle-description"><span class="material-symbols-outlined" aria-hidden="true">notes</span><span>Descripción</span><span class="more-menu-check material-symbols-outlined" aria-hidden="true">check</span></button>${canBranch(field) ? `<button type="button" role="menuitemcheckbox" aria-checked="${expanded}" aria-controls="branches-${esc(field.id)}" tabindex="-1" data-action="toggle-branches"><span class="material-symbols-outlined" aria-hidden="true">account_tree</span><span>Mostrar según respuesta${count ? `<small class="more-menu-detail">${count} ${count === 1 ? "condición" : "condiciones"}</small>` : ""}</span><span class="more-menu-check material-symbols-outlined" aria-hidden="true">check</span></button>` : ""}<button type="button" role="menuitem" tabindex="-1" data-action="move-question"><span class="material-symbols-outlined" aria-hidden="true">drive_file_move</span><span>Mover a otra sección</span></button></div></div>`;
  }
  root.addEventListener("builder:close-menus", () => closeTypeMenu(true));
  function additionalTextOptions(field) {
    const config = field.configuration;
    const available = field.options.filter((option) => option.is_active);
    const target = config.additional_text === "other"
      ? available.find((option) => /^(otro|otra|otros|otras)$/i.test(option.label.trim()))?.value
      : config.additional_text_option;
    const selected = config.additional_text === "any" ? "any"
      : available.some((option) => option.value === target) ? `option:${target}` : "";
    return `<option value="" disabled ${selected ? "" : "selected"}>Selecciona una opción</option>`
      + options([["any", "Al elegir cualquier opción"], ...available.map((option) =>
        [`option:${option.value}`, option.label || "Opción sin título"]
      )], selected);
  }
  function additionalSummary(field) {
    const select = document.createElement("select");
    select.innerHTML = additionalTextOptions(field);
    const option = select.selectedOptions[0];
    if (!option?.value) return "Selecciona cuándo mostrar el campo adicional.";
    return "Se muestra al elegir una opción de la lista.";
  }
  function settingsFor(field) {
    const config = field.configuration;
    if (editorType(field) === "DROPDOWN_EXTRA") {
      const inputType = config.additional_text_type || "text";
      const placeholder = config.additional_text_placeholder ?? "Por favor escriba cual";
      const inputTypes = [["text", "Texto"], ["number", "Numérico"], ["email", "Correo electrónico"]];
      const typeLabel = inputTypes.find(([value]) => value === inputType)?.[1] || "Texto";
      const expanded = expandedAdditional.get(field.id) ?? true;
      return `<div class="additional-choice-settings" id="additional-settings-${esc(field.id)}" ${expanded ? "" : "hidden"}>
        <p data-additional-summary>${esc(additionalSummary(field))}</p>
        <div class="additional-choice-controls">
          ${additionalPicker(field, "trigger")}
          ${additionalPicker(field, "type")}
        </div>
        <label>Placeholder del campo adicional<input type="text" data-config="additional_text_placeholder" maxlength="200" value="${esc(placeholder)}" placeholder="Ejemplo: Escribe tu número de documento"></label>
        <div class="additional-preview-card" role="group" aria-label="Vista previa del campo adicional">
          <div class="additional-preview-heading"><span><span class="material-symbols-outlined" aria-hidden="true">visibility</span>Vista previa</span><span class="additional-preview-type">${typeLabel}</span></div>
          <label>Campo adicional<input data-additional-preview type="${inputType === "number" ? "text" : esc(inputType)}" placeholder="${esc(placeholder.trim() || "Por favor escriba cual")}" disabled></label>
          <p>Así se verá el campo al seleccionar la opción indicada.</p>
        </div>
      </div>`;
    }
    if (grids.has(field.field_type)) {
      return `<div class="grid-editor">${["rows", "columns"].map((axis) => `<div><h3>${axis === "rows" ? "Filas" : "Columnas"}</h3>${(config[axis] || []).map((item, i) => `<div class="option-row"><input data-axis="${axis}" data-axis-index="${i}" maxlength="150" aria-label="${axis === "rows" ? "Fila" : "Columna"} ${i + 1}" value="${esc(item.label)}">${icon("remove-axis", "close", "Quitar", `data-axis="${axis}" data-index="${i}"`)}</div>`).join("")}<button type="button" class="text-button" data-action="add-axis" data-axis="${axis}">＋ Añadir ${axis === "rows" ? "fila" : "columna"}</button></div>`).join("")}</div><p class="rule-link">${field.field_type === "GRID_SINGLE" ? "Una opción por fila." : "Varias opciones por fila."} Si es obligatoria, se deben responder todas las filas.</p>`;
    }
    if (["LINEAR_SCALE", "RATING"].includes(field.field_type)) {
      const rating = field.field_type === "RATING", start = rating ? 1 : config.min ?? 1, end = config.max ?? 5;
      const symbol = { star: "★", heart: "♥", thumb: "👍" }[config.symbol || "star"];
      return `<div class="type-settings">${!rating ? `<label>Desde <select data-config="min" data-number>${options([[0, "0"], [1, "1"]], start)}</select></label>` : ""}<label>${rating ? "Cantidad" : "Hasta"} <select data-config="max" data-number>${options(Array.from({ length: 9 }, (_, i) => [i + 2, String(i + 2)]), end)}</select></label>${rating ? `<label>Símbolo <select data-config="symbol">${options([["star", "Estrellas"], ["heart", "Corazones"], ["thumb", "Pulgares"]], config.symbol || "star")}</select></label>` : ""}</div><div class="scale-preview">${Array.from({ length: end - start + 1 }, (_, i) => `<span>${rating ? `<b>${symbol}</b>` : ""}${start + i}</span>`).join("")}</div>${!rating ? `<div class="type-settings"><label>Etiqueta inicial <input data-config="min_label" maxlength="150" placeholder="Opcional" value="${esc(config.min_label || "")}"></label><label>Etiqueta final <input data-config="max_label" maxlength="150" placeholder="Opcional" value="${esc(config.max_label || "")}"></label></div>` : ""}`;
    }
    if (files.has(field.field_type)) {
      const extensions = config.extensions || ["pdf", "jpg", "jpeg", "png", "webp", "docx", "xlsx", "txt", "csv"];
      return `<div class="type-settings"><label>Máximo de archivos <select data-config="max_files" data-number>${options([1, 2, 3, 4, 5].map((n) => [n, String(n)]), config.max_files || 1)}</select></label><label>Tamaño por archivo <select data-config="max_mb" data-number>${options([1, 2, 5, 10].map((n) => [n, `${n} MB`]), config.max_mb || 5)}</select></label></div><fieldset class="file-extensions"><legend>Tipos permitidos</legend>${["pdf", "jpg", "jpeg", "png", "webp", "docx", "xlsx", "txt", "csv"].map((ext) => `<label><input type="checkbox" data-extension="${ext}" ${extensions.includes(ext) ? "checked" : ""}> ${ext.toUpperCase()}</label>`).join("")}</fieldset><p class="rule-link">Los archivos se consultan desde Respuestas.</p>`;
    }
    return "";
  }
  function questionIdentity(field) {
    const number = fields().filter((item) => !display.has(item.field_type)).findIndex((item) => item.id === field.id) + 1;
    const kind = editorType(field);
    const label = types.find(([key]) => key === kind)?.[1] || kind;
    return `<span class="question-identity"><span class="question-number">${number ? `Pregunta ${number}` : "Bloque informativo"}</span><span class="question-kind"><span class="material-symbols-outlined" aria-hidden="true">${questionTypeIcons[kind] || "notes"}</span>${esc(label)}</span></span>`;
  }
  function questionPreview(field) {
    let answer = "";
    if (choices.has(field.field_type)) {
      const entries = field.options.filter((option) => option.is_active);
      if (field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio") {
        answer = field.configuration.searchable
          ? '<span class="preview-dropdown"><span class="material-symbols-outlined" aria-hidden="true">search</span> Busca y selecciona una opción <span aria-hidden="true">⌄</span></span>'
          : '<span class="preview-dropdown">Selecciona una opción <span aria-hidden="true">⌄</span></span>';
        if (field.configuration.additional_text || entries.some((option) => /^(otro|otra|otros|otras)$/i.test(option.label.trim())))
          answer += `<span class="preview-placeholder">${esc(field.configuration.additional_text_placeholder?.trim() || "Por favor escriba cual")}</span>`;
      } else {
        answer = `<span class="preview-options">${entries.slice(0, 4).map((option) => `<span class="preview-option"><span class="option-marker ${field.field_type === "MULTIPLE_CHOICE" ? "square" : ""}" aria-hidden="true"></span>${option.image_url ? `<img class="option-image-thumbnail" src="${esc(option.image_url)}" alt="">` : ""}<span>${esc(option.label)}</span></span>`).join("")}${entries.length > 4 ? `<span class="preview-more">+ ${entries.length - 4} opciones</span>` : ""}</span>`;
      }
    } else if (grids.has(field.field_type)) {
      const config = field.configuration;
      answer = `<span class="preview-grid"><span>${esc((config.columns || []).map((item) => item.label).join(" · "))}</span>${(config.rows || []).slice(0, 3).map((row) => `<span>${esc(row.label)} <span aria-hidden="true">${field.field_type === "GRID_MULTIPLE" ? "□" : "○"}　${field.field_type === "GRID_MULTIPLE" ? "□" : "○"}</span></span>`).join("")}<span class="preview-more">${config.rows?.length || 0} filas · ${config.columns?.length || 0} columnas</span></span>`;
    } else if (["LINEAR_SCALE", "RATING"].includes(field.field_type)) {
      const rating = field.field_type === "RATING", start = rating ? 1 : field.configuration.min ?? 1;
      const end = field.configuration.max ?? 5;
      const symbol = { star: "★", heart: "♥", thumb: "👍" }[field.configuration.symbol || "star"];
      answer = `<span class="preview-scale">${Array.from({ length: end - start + 1 }, (_, i) => `<span>${rating ? symbol : start + i}</span>`).join("")}</span>`;
    } else if (files.has(field.field_type)) {
      answer = '<span class="preview-upload"><span class="material-symbols-outlined" aria-hidden="true">upload_file</span> Añadir archivo</span>';
    } else if (!display.has(field.field_type)) {
      answer = `<span class="preview-placeholder">${esc({ BOOLEAN: "Sí / No", NUMBER: "Respuesta numérica", DATE: "Día / mes / año", TIME: "Hora : minutos", LONG_TEXT: "Texto de respuesta larga", EMAIL: "Correo electrónico", PHONE: "Número de teléfono" }[field.field_type] || "Texto de respuesta corta")}</span>`;
    }
    return `${questionIdentity(field)}<span class="preview-title">${esc(field.label || "Pregunta sin título")}${field.required ? '<span class="preview-required" aria-label="Obligatoria"> *</span>' : ""}</span>${field.help_text && field.help_text.trim() !== field.label.trim() ? `<span class="preview-help">${esc(field.help_text)}</span>` : ""}${field.image_url ? `<img class="preview-image" src="${esc(field.image_url)}" alt="">` : ""}${answer}`;
  }
  function selectCard(id) {
    if (active === id) return;
    // Keep the selected card in place when the previous editor collapses above it.
    const anchorId = id || active;
    const anchor = anchorId && container.querySelector(`[data-field="${CSS.escape(anchorId)}"], [data-section="${CSS.escape(anchorId)}"]`);
    const anchorTop = anchor?.getBoundingClientRect().top;
    if (openTypeMenu && openTypeMenu.closest("[data-field]").dataset.field !== id) closeTypeMenu();
    active = id;
    for (const card of container.querySelectorAll(".question-card")) {
      const selected = card.dataset.field === id;
      const preview = card.querySelector(".question-preview");
      card.classList.toggle("active", selected);
      card.querySelector(".question-editor").hidden = !selected;
      preview.hidden = selected;
      if (!selected) {
        const field = findField(card.dataset.field);
        preview.innerHTML = questionPreview(field);
        preview.setAttribute("aria-label", `Editar: ${field.label || "Pregunta sin título"}`);
      }
    }
    updateNavigation();
    if (anchor && Number.isFinite(anchorTop)) {
      // Unfold can scroll an inner layout container instead of the window.
      for (let parent = anchor.parentElement; parent; parent = parent.parentElement) {
        if (parent === document.scrollingElement) continue;
        if (!/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) continue;
        const offset = anchor.getBoundingClientRect().top - anchorTop;
        if (Math.abs(offset) < 1) break;
        parent.scrollBy({ top: offset, behavior: "instant" });
      }
      const offset = anchor.getBoundingClientRect().top - anchorTop;
      if (Math.abs(offset) >= 1) window.scrollBy({ top: offset, behavior: "instant" });
    }
  }
  function question(field, section) {
    let body = "";
    if (choices.has(field.field_type)) {
      body = `<div class="option-list">${field.options.map((o, i) => `<div class="option-row"><span class="option-marker ${field.field_type === "MULTIPLE_CHOICE" ? "square" : ""}" aria-hidden="true"></span><input data-option="${i}" maxlength="240" aria-label="Opción ${i + 1}" value="${esc(o.label)}">${o.image_url ? `<img class="option-image-thumbnail" src="${esc(o.image_url)}" alt="Imagen de ${esc(o.label)}">` : ""}${icon("upload-option-image", "image", o.image_url ? "Cambiar imagen de la opción" : "Añadir imagen a la opción", `data-option="${i}"`)}${o.image_url ? icon("remove-option-image", "hide_image", "Quitar imagen de la opción", `data-option="${i}"`) : ""}${icon("remove-option", "close", "Quitar opción", `data-option="${i}"`)}</div>`).join("")}<button type="button" class="text-button" data-action="add-option">＋ Añadir opción</button></div>`;
      const relation = field.configuration.option_filter;
      const dependents = catalogChildren(field);
      if (relation || dependents.length || field.configuration.catalog_import) {
        const parent = fields().find((item) => item.stable_key === relation?.source);
        body = `<div class="catalog-link-note"><strong>${relation ? `Opciones según «${esc(parent?.label || "Campo no disponible") }»` : dependents.length ? `Agrupa las opciones de ${dependents.map((item) => `«${esc(item.label)}»`).join(", ")}` : "Opciones importadas desde Excel"}</strong><p>Para cambiar códigos o relaciones, vuelve a importar la tabla.</p></div><details class="catalog-option-list"><summary>${field.options.length} opciones importadas · Ver lista</summary><ul>${field.options.map((option) => `<li><code>${esc(option.value)}</code> ${esc(option.label)}</li>`).join("")}</ul></details>`;
      }
    } else if (grids.has(field.field_type) || files.has(field.field_type) || ["LINEAR_SCALE", "RATING"].includes(field.field_type))
      body = settingsFor(field);
    else if (!display.has(field.field_type))
      body = `<div class="answer-placeholder">${esc({ BOOLEAN: "Sí / No", NUMBER: "Respuesta numérica", EMAIL: "correo@ejemplo.com", PHONE: "Ingrese el número de teléfono", DATE: "Día / mes / año", TIME: "Hora : minutos", LONG_TEXT: "Texto de respuesta larga" }[field.field_type] || "Texto de respuesta corta")}</div>`;
    if (field.image_url)
      body += `<img class="question-image" src="${esc(field.image_url)}" alt="${esc(field.label)}"><button type="button" class="text-button" data-action="remove-image">Quitar imagen</button>`;
    else if (field.field_type === "IMAGE")
      body +=
        '<div class="image-empty"><button type="button" class="text-button" data-action="upload-image">Seleccionar imagen</button><p>PNG, JPG o WebP · Hasta 5 MB</p></div>';
    body += answerBranches(field);
    if (editorType(field) === "DROPDOWN_EXTRA") body += additionalToggle(field) + settingsFor(field);
    return `<article class="question-card ${active === field.id ? "active" : ""}" data-field="${esc(field.id)}"><button type="button" class="question-drag-handle" data-action="move-question" aria-label="Arrastrar o mover: ${esc(field.label || 'Componente sin título')}" title="Arrastra para mover o pulsa para elegir destino"><span class="material-symbols-outlined" aria-hidden="true">drag_indicator</span></button><button type="button" class="question-preview" data-action="activate-question" aria-label="Editar: ${esc(field.label || "Pregunta sin título")}" ${active === field.id ? "hidden" : ""}>${questionPreview(field)}</button><div class="question-editor" ${active === field.id ? "" : "hidden"}><div class="question-top"><input class="question-title" data-prop="label" maxlength="240" aria-label="Título de la pregunta" value="${esc(field.label)}">${typePicker(field)}</div><input class="question-help" id="question-description-${esc(field.id)}" ${descriptionVisible(field) ? "" : "hidden"} data-prop="help_text" maxlength="10000" aria-label="Descripción de la pregunta" placeholder="Descripción (opcional)" value="${esc(field.help_text)}">${body}<footer class="question-footer"><div class="question-actions">${icon("duplicate-question", "content_copy", "Duplicar pregunta")}${icon("remove-question", "delete", "Eliminar pregunta")}${!display.has(field.field_type) ? `<label class="required-toggle">Obligatorio <input type="checkbox" data-prop="required" ${field.required ? "checked" : ""}></label>` : ""}${questionMoreMenu(field)}</div></footer></div></article>`;
  }
  function sectionNavigation(section, index) {
    const destinations = [
      ["NEXT", "Ir a la siguiente sección"],
      ...state.sections.flatMap((item, i) => item.id === section.id ? [] : [
        [item.id, `Ir a la sección ${i + 1} (${item.title})`],
      ]),
      ["SUBMIT", "Enviar formulario"],
    ];
    return `<div class="section-routing"><label for="next-${esc(section.id)}">Después de la sección ${index + 1}</label><select id="next-${esc(section.id)}" data-section-next>${options(destinations, section.configuration?.next_section || "NEXT")}</select></div>`;
  }
  function sectionHeader(section, index) {
    const hideHeader = section.configuration?.hide_header === true;
    const count = section.fields.filter((field) => !display.has(field.field_type)).length;
    const heading = hideHeader ? "" : `<div class="section-card"><input class="section-title" data-section-prop="title" maxlength="200" aria-label="Título de la sección" value="${esc(section.title)}"><textarea data-section-prop="description" rows="1" maxlength="10000" aria-label="Descripción de la sección" placeholder="Descripción (opcional)">${esc(section.description)}</textarea></div>`;
    return `<div class="section-toolbar"><div class="section-badge">Sección ${index + 1} de ${state.sections.length}</div><label class="section-header-toggle"><input type="checkbox" data-section-header ${hideHeader ? "" : "checked"}> ${hideHeader ? "Añadir título y descripción" : "Mostrar título y descripción"}</label><div class="section-actions">${icon("up-section", "arrow_upward", "Subir sección")}${icon("down-section", "arrow_downward", "Bajar sección")}${icon("remove-section", "delete", "Eliminar sección")}</div></div><div class="section-context"><span class="section-question-count">${count} ${count === 1 ? "pregunta" : "preguntas"}</span><span>${section.fields.length ? "Selecciona una pregunta para editarla" : "Añade la primera pregunta de esta sección"}</span></div>${heading}`;
  }
  function renderWelcome(syncInputs = true) {
    const welcome = welcomeSettings();
    if (syncInputs) {
      root.querySelectorAll("[data-welcome]").forEach((input) => {
        input.value = welcome[input.dataset.welcome] ?? ({ horizontal: "right", vertical: "center", button_label: "Comenzar" }[input.dataset.welcome] || "");
      });
    }
    const preview = document.getElementById("welcome-preview");
    preview.dataset.horizontal = welcome.horizontal || "right";
    preview.dataset.vertical = welcome.vertical || "center";
    const image = document.getElementById("welcome-preview-image");
    image.hidden = !welcome.image_url;
    if (welcome.image_url) image.src = welcome.image_url;
    else image.removeAttribute("src");
    document.getElementById("remove-welcome-image").hidden = !welcome.image;
    document.getElementById("welcome-preview-title").textContent = welcome.title || state.title || "Formulario sin título";
    document.getElementById("welcome-preview-text").textContent = welcome.text || state.description || "";
    document.getElementById("welcome-preview-button").textContent = welcome.button_label || "Comenzar";
  }
  function renderBackground() {
    const pattern = state.appearance?.background || "plain";
    root.querySelector(".builder-canvas").dataset.formBackground = pattern;
    root.querySelectorAll("[data-pattern]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.pattern === pattern));
    });
    renderTheme();
  }
  function additionalPicker(field, kind) {
    const isType = kind === "type";
    const label = isType ? "Tipo de campo" : "Mostrar campo adicional";
    const id = `additional-${kind}-${field.id}`;
    const select = document.createElement("select");
    select.innerHTML = isType
      ? options([["text", "Texto"], ["number", "Numérico"], ["email", "Correo electrónico"]], field.configuration.additional_text_type || "text")
      : additionalTextOptions(field);
    const selected = select.selectedOptions[0];
    const symbol = (value) => isType ? ({ text: "short_text", number: "tag", email: "mail" }[value] || "short_text") : value === "any" ? "list_alt" : "rule";
    const hints = { text: "Respuesta libre", number: "Solo dígitos del 0 al 9", email: "Valida el formato del correo" };
    return `<div class="additional-picker-field"><span id="${esc(id)}-label">${label}</span>
      <div class="question-type-picker additional-choice-picker" data-additional-picker="${kind}">
        <select hidden ${isType ? 'data-config="additional_text_type"' : "data-additional-trigger"} aria-label="${label}">${select.innerHTML}</select>
        <button type="button" class="question-type" data-action="toggle-type-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="${esc(id)}-menu" aria-labelledby="${esc(id)}-label ${esc(id)}-value"><span class="material-symbols-outlined additional-picker-icon" aria-hidden="true">${symbol(selected?.value)}</span><span class="question-type-label" id="${esc(id)}-value">${esc(selected?.textContent || "Selecciona una opción")}</span><span class="material-symbols-outlined additional-picker-chevron" aria-hidden="true">expand_more</span></button>
        <div id="${esc(id)}-menu" class="question-type-menu additional-choice-menu" popover="manual" role="menu" aria-label="${label}">
          ${[...select.options].filter((option) => !option.disabled).map((option) => `<button type="button" role="menuitemradio" aria-checked="${option.selected}" tabindex="-1" data-action="choose-picker-option" data-type="${esc(option.value)}"><span class="material-symbols-outlined additional-picker-icon" aria-hidden="true">${symbol(option.value)}</span><span class="additional-option-label">${esc(option.textContent)}${isType ? `<small>${hints[option.value]}</small>` : ""}</span><span class="material-symbols-outlined additional-picker-check" aria-hidden="true">check</span></button>`).join("")}
        </div>
      </div></div>`;
  }
  function renderTheme() {
    const appearance = { ...themeConfig.defaults, ...state.appearance };
    const canvas = root.querySelector(".builder-canvas");
    for (const key of ["color", "background_color"]) canvas.style.setProperty(`--form-${key.replaceAll("_", "-")}`, appearance[key]);
    for (const key of ["heading", "question", "text"]) {
      canvas.style.setProperty(`--form-${key}-font`, themeConfig.fonts[appearance[`${key}_font`]]);
      canvas.style.setProperty(`--form-${key}-size`, `${appearance[`${key}_size`]}px`);
    }
    root.querySelectorAll("[data-theme]").forEach((input) => { input.value = appearance[input.dataset.theme]; });
    root.querySelectorAll("[data-action='theme-color']").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.color === appearance.color));
    });
    root.querySelectorAll('[data-action="theme-background"]').forEach((button) => {
      button.setAttribute("aria-pressed", String(appearance.background === "plain" && button.dataset.color === appearance.background_color.toLowerCase()));
    });
    root.querySelectorAll('.background-swatch[data-form-background="plain"]').forEach((swatch) => {
      swatch.style.background = appearance.background_color;
    });
    const imageUrl = appearance.header_image ? themeConfig.image_url_template.replace("{id}", appearance.header_image) : "";
    const image = document.getElementById("builder-header-image");
    image.hidden = !imageUrl;
    if (imageUrl) image.src = imageUrl;
    else image.removeAttribute("src");
  }
  function updateTheme(input) {
    state.appearance ||= {};
    const key = input.dataset.theme;
    const value = input.hasAttribute("data-number") ? Number(input.value) : input.value;
    if (state.appearance[key] === value) return;
    state.appearance[key] = value;
    if (key === "background_color") state.appearance.background = "plain";
    changed(input);
    renderBackground();
  }
  function positionThemePanel() {
    const top = Math.max(0, Math.min(root.querySelector(".builder-tabs").getBoundingClientRect().bottom, window.innerHeight - 180));
    root.style.setProperty("--theme-panel-top", `${top}px`);
  }
  function setThemePanel(open, restoreFocus = false) {
    document.getElementById("builder-backgrounds").hidden = !open;
    root.classList.toggle("theme-open", open);
    const trigger = root.querySelector('[data-action="toggle-background"]');
    trigger.setAttribute("aria-expanded", String(open));
    if (open) positionThemePanel();
    if (restoreFocus) trigger.focus({ preventScroll: true });
  }
  function renderSettings() {
    const notifications = state.notifications || {};
    const emailFields = fields().filter((field) => field.field_type === "EMAIL");
    const emailKey = notifications.respondent_email_stable_key || "";
    root.querySelectorAll("[data-notification]").forEach((input) => {
      if (input.type === "checkbox") input.checked = notifications[input.dataset.notification] !== false;
      else input.innerHTML = options([["", "Automático"], ...emailFields.map((field) => [field.stable_key, field.label]), ...(emailKey && !emailFields.some((field) => field.stable_key === emailKey) ? [[emailKey, "Campo eliminado — elige otro"]] : [])], emailKey);
    });
    const summary = state.response_summary || {};
    const eligible = fields().filter((field) => !["HEADING", "INFORMATION", "IMAGE", "FILE", "DOCUMENT", "GRID_SINGLE", "GRID_MULTIPLE"].includes(field.field_type));
    const choices = [["", "Automático"], ...eligible.map((field) => [field.stable_key, field.label])];
    const summaryOptions = (selected, empty) => options([["", empty], ...choices.slice(1), ...(selected && !eligible.some((field) => field.stable_key === selected) ? [[selected, "Campo eliminado — elige otro"]] : [])], selected || "");
    document.getElementById("response-summary-fields").innerHTML = `<label>Título de la respuesta<select data-summary-title>${summaryOptions(summary.title, "Automático: nombre del respondiente")}</select></label>${[0, 1, 2].map((i) => `<div class="response-summary-setting"><label>Dato ${i + 1}<select data-summary-field="${i}">${summaryOptions(summary.fields?.[i]?.key, "Sin seleccionar")}</select></label><label class="summary-mask"><input type="checkbox" data-summary-mask="${i}" ${summary.fields?.[i]?.masked ? "checked" : ""} ${summary.fields?.[i]?.key ? "" : "disabled"}> Ocultar parte del dato (•••• 4521)</label></div>`).join("")}`;
    root.querySelectorAll("[data-form-setting]").forEach((input) => {
      input.value = state[input.dataset.formSetting] || "";
    });
    const settings = state.settings || {};
    const date = (value) => value ? new Date(value).toLocaleString("es-CO") : "—";
    const set = (id, text) => { document.getElementById(id).textContent = text; };
    set("settings-status", settings.status_label || "No publicado");
    set("settings-active-version", settings.active_version ? `v${settings.active_version}` : "Sin publicar");
    set("settings-created-by", settings.created_by || "—");
    set("settings-created-at", date(settings.created_at));
    set("settings-updated-at", date(settings.updated_at));
    set("settings-access-hint", {
      PUBLISHED: "Cualquier persona con el enlace puede responder sin iniciar sesión.",
      PAUSED: "El enlace es público, pero la recepción de respuestas está pausada.",
      ARCHIVED: "Este formulario está archivado y no recibe respuestas.",
    }[settings.status] || "Publica el formulario para recibir respuestas.");
    const published = ["PUBLISHED", "PAUSED"].includes(settings.status);
    const accepting = settings.status === "PUBLISHED";
    const publicSwitch = document.getElementById("settings-public-switch");
    const receptionSwitch = document.getElementById("settings-reception-switch");
    publicSwitch.setAttribute("aria-checked", String(published));
    receptionSwitch.setAttribute("aria-checked", String(accepting));
    publicSwitch.disabled = settings.status === "ARCHIVED";
    const headerSwitch = document.getElementById("builder-public-switch");
    headerSwitch.setAttribute("aria-checked", String(published));
    headerSwitch.disabled = settings.status === "ARCHIVED";
    set("builder-public-state", published ? "Publicado" : "No publicado");
    receptionSwitch.disabled = !published;
    set("settings-public-state", published ? "Público" : "No público");
    set("settings-reception-state", accepting ? "Activada" : published ? "Pausada" : "Publica el formulario para activar la recepción");
    document.getElementById("settings-sharing").hidden = !settings.active_version;
    const url = document.getElementById("share-url").value;
    document.getElementById("settings-share-url").value = url;
    document.getElementById("settings-public-link").href = url;
    document.getElementById("settings-public-link").hidden = !published;
    const shareToggle = document.getElementById("builder-share-toggle");
    shareToggle.disabled = !published;
    if (!published) shareToggle.setAttribute("aria-expanded", "false");
    document.getElementById("sharing").hidden = !published || shareToggle.getAttribute("aria-expanded") !== "true";
    document.getElementById("settings-versions").innerHTML = (settings.versions || []).map((version) =>
      `<tr><td>v${esc(version.number)}</td><td>${esc(version.status)}</td><td>${esc(version.schema_version)}</td><td>${esc(date(version.created_at))}</td><td>${esc(date(version.published_at))}</td></tr>`
    ).join("") || '<tr><td colspan="5">No hay versiones guardadas.</td></tr>';
  }
  function render() {
    closeTypeMenu();
    renderBackground();
    renderWelcome();
    renderSettings();
    container.innerHTML = state.sections
      .map(
        (section, i) =>
          `<section class="builder-section" aria-label="Sección ${i + 1}" data-section="${esc(section.id)}">${sectionHeader(section, i)}${section.fields.map((f) => question(f, section)).join("")}<button type="button" class="text-button" data-action="add-question">＋ Añadir pregunta</button>${sectionNavigation(section, i)}</section>`,
      )
      .join("");
    container.querySelectorAll(".question-card").forEach((card) => {
      const field = findField(card.dataset.field);
      card.querySelector(".question-editor").insertAdjacentHTML("afterbegin", `<div class="question-editing-context">${questionIdentity(field)}<span>Editando pregunta</span></div>`);
    });
    updateNavigation();
    if (root.dataset.archived === "true")
      root
        .querySelectorAll("button,input,select,textarea")
        .forEach((el) => {
          if (!el.closest(".builder-tabs, #builder-responses-panel, .builder-sidebar-toggle, .builder-navigation")) el.disabled = true;
        });
  }
  function focusCard(id) {
    root
      .querySelector(
        `[data-field="${CSS.escape(id)}"], [data-section="${CSS.escape(id)}"]`,
      )
      ?.scrollIntoView({ behavior: "instant", block: "start" });
  }
  root.addEventListener("builder:import-catalog", (event) => {
    const request = event.detail;
    if (busy || root.dataset.archived === "true") { request.error = "No se puede importar en este momento."; return; }
    if (fields().length + request.fields.length > 200) { request.error = "El formulario admite hasta 200 componentes."; return; }
    let section = selectedSection();
    if (!section) { section = newSection(); state.sections.push(section); }
    const imported = structuredClone(request.fields);
    // Every application gets fresh stable keys, including repeated imports of one file.
    const keys = new Map(imported.map((field) => [field.stable_key, `q_${uid().replaceAll("-", "_")}`]));
    for (const field of imported) {
      field.id = uid();
      field.stable_key = keys.get(field.stable_key);
      if (field.configuration.option_filter) field.configuration.option_filter.source = keys.get(field.configuration.option_filter.source);
    }
    const index = section.fields.findIndex((field) => field.id === active);
    section.fields.splice(index < 0 ? section.fields.length : index + 1, 0, ...imported);
    active = imported[0].id;
    changed();
    render();
    focusCard(active);
    notify(`Se añadieron ${imported.length} campos relacionados. Guarda para conservarlos.`);
  });
  root.addEventListener("builder:navigate", (event) => {
    if (busy) return;
    const id = event.detail;
    if (id === "welcome") {
      selectCard(null);
      root.querySelector(".welcome-editor").scrollIntoView({ block: "start" });
      root.querySelector('[data-welcome="title"]').focus({ preventScroll: true });
      return;
    }
    if (!findField(id) && !findSection(id)) return;
    selectCard(id);
    focusCard(id);
    const target = container.querySelector(`[data-field="${CSS.escape(id)}"] .question-title, [data-section="${CSS.escape(id)}"] .section-toolbar`);
    if (target) {
      if (!target.matches("input")) target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
  });
  root.addEventListener("builder:move-field", (event) => {
    const request = event.detail;
    if (busy || root.dataset.archived === "true") {
      request.error = "No se puede mover el componente en este momento.";
      return;
    }
    const source = state.sections.find((section) => section.fields.some((field) => field.id === request.fieldId));
    const destination = findSection(request.sectionId);
    if (!source || !destination) { request.error = "No se encontró la sección de destino."; return; }
    const field = source.fields.find((item) => item.id === request.fieldId);
    const remaining = destination.fields.filter((item) => item !== field);
    const index = request.beforeId == null ? remaining.length : remaining.findIndex((item) => item.id === request.beforeId);
    if (index < 0) { request.error = "La posición de destino ya no está disponible."; return; }
    if (source === destination && source.fields.indexOf(field) === index) return;
    const proposed = state.sections.map((section) => {
      const items = section.fields.filter((item) => item !== field);
      if (section === destination) items.splice(index, 0, field);
      return { ...section, fields: items };
    });
    const ordered = proposed.flatMap((section) => section.fields);
    const invalidRelation = ordered.find((item, index) => item.configuration.option_filter
      && ordered.findIndex((source) => source.stable_key === item.configuration.option_filter.source) >= index);
    if (invalidRelation) {
      request.error = `El agrupador debe aparecer antes de «${invalidRelation.label}».`;
      return;
    }
    // Moving a source into its own conditional section can create a dependency cycle.
    const graph = new Map(fields().map((item) => [item.id, new Set()]));
    for (const rule of state.rules) {
      const targets = rule.target_field ? [rule.target_field]
        : (proposed.find((section) => section.id === rule.target_section)?.fields || []).map((item) => item.id);
      if (!targets.length) {
        request.error = "Esta sección se utiliza en una condición y no puede quedar vacía. Cambia su condición antes de mover el último componente.";
        return;
      }
      targets.forEach((target) => graph.get(target)?.add(rule.source));
    }
    const visiting = new Set(), visited = new Set();
    function hasCycle(id) {
      if (visiting.has(id)) return true;
      if (visited.has(id)) return false;
      visiting.add(id);
      for (const dependency of graph.get(id) || []) if (hasCycle(dependency)) return true;
      visiting.delete(id);
      visited.add(id);
      return false;
    }
    if ([...graph.keys()].some(hasCycle)) {
      request.error = "Ese destino haría que una condición dependiera de sí misma. Elige otra sección o ajusta las condiciones.";
      return;
    }
    source.fields.splice(source.fields.indexOf(field), 1);
    destination.fields.splice(index, 0, field);
    active = field.id;
    changed();
    render();
    focusCard(field.id);
    container.querySelector(`[data-field="${CSS.escape(field.id)}"] [data-action="move-question"]`)?.focus({ preventScroll: true });
    request.moved = true;
  });
  function pruneRules(ids) {
    const before = state.rules.length;
    state.rules = state.rules.filter(
      (r) =>
        !ids.includes(r.source) &&
        !ids.includes(r.target_field) &&
        !ids.includes(r.target_section),
    );
    if (before !== state.rules.length)
      notify(
        "Se retiraron las condiciones asociadas al contenido eliminado. Revisa las condiciones antes de publicar.",
      );
  }
  root.addEventListener("focusin", (e) => {
    if (openTypeMenu && !openTypeMenu.parentElement.contains(e.target)) closeTypeMenu();
    const field = e.target.closest("[data-field]");
    if (field && !e.target.closest(".question-preview")) {
      if (active !== field.dataset.field) selectCard(field.dataset.field);
    } else if (!field && e.target.closest("[data-section]"))
      selectCard(e.target.closest("[data-section]").dataset.section);
    else if (e.target.id === "form-title") selectCard(null);
  });
  root.addEventListener("keydown", (e) => {
    const branchPicker = e.target.closest(".branch-target-picker[open]");
    if (e.key === "Escape" && branchPicker) {
      e.preventDefault();
      branchPicker.open = false;
      branchPicker.querySelector("summary").focus({ preventScroll: true });
      return;
    }
    if (e.key === "Enter" && e.target.hasAttribute("data-branch-search")) {
      e.preventDefault();
      branchPicker?.querySelector('[data-target]:not([hidden])')?.focus();
      return;
    }
    if (e.key === "Escape" && e.target.closest(".theme-panel")) {
      e.preventDefault();
      setThemePanel(false, true);
      return;
    }
    const trigger = e.target.closest('[data-action="toggle-type-menu"]');
    if (!busy && trigger && ["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      showTypeMenu(trigger, e.key === "ArrowUp");
      return;
    }
    if (openTypeMenu) {
      if (e.key === "Escape" || e.key === "Tab") {
        if (e.key === "Escape") e.preventDefault();
        closeTypeMenu(true);
        return;
      }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
        e.preventDefault();
        const items = [...openTypeMenu.querySelectorAll("button")];
        const index = items.indexOf(document.activeElement);
        const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1
          : (index + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items[next].focus({ preventScroll: true });
        items[next].scrollIntoView({ block: "nearest" });
        return;
      }
    }
    if (e.key !== "Escape" || busy) return;
    const card = e.target.closest(".question-card.active");
    if (!card) return;
    selectCard(null);
    card.querySelector(".question-preview").focus({ preventScroll: true });
  });
  root.addEventListener("input", (e) => {
    const el = e.target;
    if (el.hasAttribute("data-branch-search")) { filterBranchTargets(el); return; }
    if (el.dataset.theme) { updateTheme(el); return; }
    if (el.dataset.formSetting) {
      state[el.dataset.formSetting] = el.value;
      if (el.dataset.formSetting === "title") document.getElementById("form-title").value = el.value;
      changed(el);
      renderWelcome(false);
      return;
    }
    if (el.dataset.welcome) {
      welcomeSettings()[el.dataset.welcome] = el.value;
      changed(el);
      renderWelcome(false);
      return;
    }
    if (el.tagName === "SELECT" || el.type === "checkbox" || el.type === "file")
      return;
    if (el.id === "form-title") {
      state.title = el.value;
      document.getElementById("settings-title").value = el.value;
      renderWelcome(false);
    }
    else if (el.dataset.sectionProp)
      findSection(el.closest("[data-section]").dataset.section)[
        el.dataset.sectionProp
      ] = el.value;
    else if (el.closest("[data-field]")) {
      const f = findField(el.closest("[data-field]").dataset.field);
      if (el.dataset.config) {
        f.configuration[el.dataset.config] = el.value;
        if (el.dataset.config === "additional_text_placeholder") {
          const preview = el.closest("[data-field]").querySelector("[data-additional-preview]");
          if (preview) preview.placeholder = el.value.trim() || "Por favor escriba cual";
        }
      }
      else if (el.dataset.axis) f.configuration[el.dataset.axis][+el.dataset.axisIndex].label = el.value;
      else if (el.hasAttribute("data-option")) {
        f.options[+el.dataset.option].label = el.value;
        const trigger = el.closest("[data-field]").querySelector("[data-additional-trigger]");
        if (trigger) {
          const picker = trigger.closest(".additional-picker-field");
          if (picker) picker.outerHTML = additionalPicker(f, "trigger");
          else trigger.innerHTML = additionalTextOptions(f);
        }
        const summary = el.closest("[data-field]").querySelector("[data-additional-summary]");
        if (summary) summary.textContent = additionalSummary(f);
      }
      else if (el.dataset.prop) f[el.dataset.prop] = el.value;
      else return;
    } else return;
    changed(el);
  });
  root.addEventListener("focusout", () => { lastEdit = null; });
  root.addEventListener("change", (e) => {
    const el = e.target;
    if (el.matches("[data-notification]")) {
      state.notifications = { notify_internal_on_submission: true, notify_respondent_on_validated: true, notify_respondent_on_rejected: true, respondent_email_stable_key: "", ...state.notifications };
      state.notifications[el.dataset.notification] = el.type === "checkbox" ? el.checked : el.value;
      changed();
      return;
    }
    if (el.matches("[data-summary-title],[data-summary-field],[data-summary-mask]")) {
      const container = document.getElementById("response-summary-fields");
      state.response_summary = {
        title: container.querySelector("[data-summary-title]").value,
        fields: [...container.querySelectorAll("[data-summary-field]")].map((select, i) => ({ key: select.value, masked: container.querySelector(`[data-summary-mask="${i}"]`).checked })).filter((entry) => entry.key),
      };
      changed();
      renderSettings();
      return;
    }
    if (el.dataset.theme) { updateTheme(el); return; }
    if (el.hasAttribute("data-additional-trigger")) {
      const field = findField(el.closest("[data-field]").dataset.field);
      if (el.value === "any") {
        field.configuration.additional_text = "any";
        delete field.configuration.additional_text_option;
      } else if (el.value.startsWith("option:")) {
        field.configuration.additional_text = "option";
        field.configuration.additional_text_option = el.value.slice(7);
      } else return;
      changed();
      render();
      return;
    }
    if (el.dataset.config || el.dataset.extension) {
      const field = findField(el.closest("[data-field]").dataset.field);
      if (el.dataset.extension) {
        field.configuration.extensions = [...el.closest(".file-extensions").querySelectorAll("input:checked")].map((input) => input.dataset.extension);
      } else {
        field.configuration[el.dataset.config] = el.hasAttribute("data-number") ? Number(el.value) : el.value;
      }
      changed();
      if (el.tagName === "SELECT") render();
      return;
    }
    if (el.hasAttribute("data-section-header")) {
      const section = findSection(el.closest("[data-section]").dataset.section);
      section.configuration = { ...section.configuration, hide_header: !el.checked };
      changed();
      render();
      container.querySelector(`[data-section="${CSS.escape(section.id)}"] [data-section-header]`)?.focus();
      return;
    }
    if (el.hasAttribute("data-section-next")) {
      const section = findSection(el.closest("[data-section]").dataset.section);
      section.configuration = { ...section.configuration, next_section: el.value };
      changed();
      return;
    }
    if (el.hasAttribute("data-branch-answer")) {
      updateBranch(findField(el.closest("[data-field]").dataset.field), el.closest(".branch-rule"));
      return;
    }
    const card = el.closest("[data-field]");
    if (!card || !el.dataset.prop) return;
    const field = findField(card.dataset.field),
      prop = el.dataset.prop;
    if (prop === "required") field.required = el.checked;
    else if (prop === "field_type") {
      const dropdown = ["DROPDOWN", "DROPDOWN_SEARCH", "DROPDOWN_EXTRA"].includes(el.value);
      const kind = dropdown ? "SINGLE_CHOICE" : el.value;
      if ((field.configuration.option_filter && !dropdown) || (catalogChildren(field).length && kind !== "SINGLE_CHOICE")) {
        notify("Este campo forma parte de una lista relacionada. Conserva un tipo de selección compatible.", true);
        render();
        return;
      }
      if (kind === "SINGLE_CHOICE" && field.field_type === kind) {
        field.configuration.widget = dropdown ? "select" : "radio";
        field.configuration.searchable = el.value === "DROPDOWN_SEARCH";
        if (el.value === "DROPDOWN_EXTRA") field.configuration.additional_text ||= "any";
        else {
          delete field.configuration.additional_text;
          delete field.configuration.additional_text_option;
        }
        changed();
        render();
        return;
      }
      if (
        state.rules.some((r) => r.source === field.id) &&
        !confirm(
          "Cambiar el tipo quitará las condiciones que usan esta respuesta. ¿Continuar?",
        )
      ) {
        render();
        return;
      }
      state.rules = state.rules.filter((r) => r.source !== field.id);
      field.field_type = kind;
      field.validation = {};
      field.configuration = {};
      field.options = choices.has(kind)
        ? field.options.length
          ? field.options
          : [{ label: "Opción 1", value: uid(), is_active: true }]
        : [];
      if (display.has(kind)) field.required = false;
      if (kind === "SINGLE_CHOICE") field.configuration.widget = dropdown ? "select" : "radio";
      if (el.value === "DROPDOWN_SEARCH") field.configuration.searchable = true;
      if (el.value === "DROPDOWN_EXTRA") field.configuration.additional_text = "any";
      if (grids.has(kind)) {
        field.configuration = {
          rows: [{ id: uid(), label: "Fila 1" }],
          columns: [{ id: uid(), label: "Columna 1" }, { id: uid(), label: "Columna 2" }],
        };
      }
      if (["LINEAR_SCALE", "RATING"].includes(kind)) field.configuration = { min: 1, max: 5, symbol: "star" };
    } else if (prop === "widget") field.configuration.widget = el.value;
    else return;
    changed();
    render();
  });
  async function initializeForm() {
    if (root.dataset.base) return;
    const response = await fetch(root.dataset.createUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({
        creation_token: root.dataset.creationToken,
        title: state.title,
      }),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.error || "No se pudo crear el formulario.");
    root.dataset.base = data.editor_url;
    state.version = data.version;
    state.fingerprint = data.fingerprint;
    state.number = data.number;
    state.settings = data.settings;
    document.getElementById("share-url").value = data.share_url;
    document.getElementById("builder-public").href = data.share_url;
    if (data.responses_url) {
      const responses = document.getElementById("builder-responses");
      responses.dataset.url = data.responses_url;
      responses.hidden = false;
    }
    history.replaceState(null, "", data.editor_url);
    renderSettings();
  }
  async function save(publish = false) {
    if (busy) return false;
    const sectionIndex = state.sections.findIndex((section) => section.id === active || section.fields.some((field) => field.id === active));
    const fieldIndex = sectionIndex < 0 ? -1 : state.sections[sectionIndex].fields.findIndex((field) => field.id === active);
    busy = true;
    updateNavigation();
    notify("");
    status.textContent = publish ? "Publicando…" : "Guardando…";
    const controls = [...root.querySelectorAll("input,textarea,select,button")];
    const disabled = controls.map((control) => control.disabled);
    controls.forEach((el) => (el.disabled = true));
    try {
      await initializeForm();
      const response = await fetch(
        root.dataset.base + (publish ? "publish/" : "save/"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify(state),
        },
      );
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "No se pudo guardar.");
      state = result;
      currentSnapshot = snapshot();
      savedSnapshot = currentSnapshot;
      lastEdit = null;
      document.getElementById("form-title").value = state.title;
      dirty = false;
      active = fieldIndex >= 0 ? state.sections[sectionIndex]?.fields[fieldIndex]?.id || null
        : state.sections[sectionIndex]?.id || null;
      render();
      status.textContent = "Formulario guardado";
      if (publish) {
        notify("Formulario publicado. Ya puedes compartir el enlace.");
      }
      return true;
    } catch (error) {
      notify(error.message || "No se pudo guardar. Revisa tu conexión.", true);
      status.textContent = "No se guardaron los cambios";
      return false;
    } finally {
      busy = false;
      controls.forEach((el, index) => (el.disabled = disabled[index]));
      renderSettings();
      updateHistoryButtons();
      updateNavigation();
    }
  }
  root.addEventListener("click", async (e) => {
    if (e.target.closest("[data-open-catalog]")) return;
    const button = e.target.closest("button[data-action]");
    if (!button && !busy) {
      const card = e.target.closest(".question-card");
      if (card && active !== card.dataset.field) selectCard(card.dataset.field);
      else if (!card && e.target.closest(".builder-canvas")) {
        selectCard(e.target.closest("[data-section]")?.dataset.section || null);
      }
    }
    if (!button || button.disabled || busy) return;
    const action = button.dataset.action;
    if (action === "undo" || action === "redo") {
      restoreHistory(action);
      return;
    }
    if (action === "toggle-background") {
      const palette = document.getElementById("builder-backgrounds");
      const opening = palette.hidden || document.getElementById("builder-questions-panel").hidden;
      if (opening) root.querySelector('[data-builder-tab="questions"]').click();
      setThemePanel(opening);
      if (opening) palette.querySelector('[data-action="close-theme"]').focus({ preventScroll: true });
      return;
    }
    if (action === "close-theme") {
      setThemePanel(false, true);
      return;
    }
    if (action === "theme-color") {
      state.appearance = { ...state.appearance, color: button.dataset.color };
      changed();
      renderTheme();
      return;
    }
    if (action === "theme-background") {
      state.appearance = { ...state.appearance, background: "plain", background_color: button.dataset.color };
      changed();
      renderBackground();
      return;
    }
    if (action === "toggle-sharing") {
      const sharing = document.getElementById("sharing");
      sharing.hidden = !sharing.hidden;
      button.setAttribute("aria-expanded", String(!sharing.hidden));
      return;
    }
    if (action === "toggle-type-menu") {
      if (openTypeMenu === button.parentElement.querySelector(".question-type-menu")) closeTypeMenu(true);
      else showTypeMenu(button);
      return;
    }
    if (action === "choose-question-type" || action === "choose-picker-option") {
      const picker = button.closest(".question-type-picker");
      const fieldId = picker.closest("[data-field]").dataset.field;
      const pickerKind = picker.dataset.additionalPicker;
      const select = picker.querySelector("select");
      closeTypeMenu(true);
      if (select.value !== button.dataset.type) {
        select.value = button.dataset.type;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        const pickerSelector = pickerKind ? `[data-additional-picker="${pickerKind}"] ` : "";
        root.querySelector(`[data-field="${CSS.escape(fieldId)}"] ${pickerSelector}[data-action="toggle-type-menu"]`)?.focus({ preventScroll: true });
      }
      return;
    }
    if (action === "select-background") {
      state.appearance = { ...state.appearance, background: button.dataset.pattern };
      changed();
      renderBackground();
      return;
    }
    if (action === "welcome-image") {
      imageTarget = "welcome";
      document.getElementById("image-upload").click();
      return;
    }
    if (action === "remove-welcome-image") {
      Object.assign(welcomeSettings(), { image: null, image_url: "" });
      changed();
      renderWelcome(false);
      return;
    }
    const card = button.closest("[data-field]"),
      field = card ? findField(card.dataset.field) : null;
    const sectionElement = button.closest("[data-section]");
    let section = sectionElement
      ? findSection(sectionElement.dataset.section)
      : selectedSection();
    if (action === "activate-question") {
      selectCard(field.id);
      card.querySelector(".question-title").focus({ preventScroll: true });
      return;
    }
    if (action === "save" || action === "publish") {
      await save(action === "publish");
      return;
    }
    if (action === "toggle-public" || action === "toggle-reception") {
      const isPublic = ["PUBLISHED", "PAUSED"].includes(state.settings?.status);
      if (action === "toggle-public" && !isPublic) {
        await save(true);
        return;
      }
      const operation = action === "toggle-public" ? "unpublish"
        : state.settings?.status === "PUBLISHED" ? "pause" : "resume";
      busy = true;
      const controls = [...root.querySelectorAll("input,textarea,select,button")];
      const disabled = controls.map((control) => control.disabled);
      controls.forEach((control) => { control.disabled = true; });
      try {
        const response = await fetch(root.dataset.base + `${operation}/`, {
          method: "POST", headers: { "X-CSRFToken": csrf },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "No se pudo actualizar el acceso.");
        state.settings = data.settings;
        notify({
          unpublish: "El formulario ya no es público.",
          pause: "Recepción de respuestas pausada.",
          resume: "Recepción de respuestas activada.",
        }[operation]);
      } catch (error) {
        notify(error.message || "No se pudo actualizar el acceso.", true);
      } finally {
        busy = false;
        controls.forEach((control, index) => { control.disabled = disabled[index]; });
        renderSettings();
      }
      return;
    }
    if (action === "preview") {
      const tab = window.open("about:blank", "_blank");
      if (tab) tab.opener = null;
      if ((!dirty && state.status === "PUBLISHED") || (await save())) {
        if (tab) tab.location = root.dataset.base + "preview/";
        else location.href = root.dataset.base + "preview/";
      } else tab?.close();
      return;
    }
    if (action === "copy-link") {
      const input = button.closest(".settings-link-bar")?.querySelector("input") || document.getElementById("share-url");
      try {
        await navigator.clipboard.writeText(input.value);
        notify("Enlace copiado.");
      } catch {
        input.focus();
        input.select();
        notify("Selecciona y copia el enlace con Ctrl+C.");
      }
      return;
    }
    if (action === "add-axis" || action === "remove-axis") {
      const axis = button.dataset.axis;
      if (action === "add-axis") {
        if (field.configuration[axis].length >= (axis === "rows" ? 20 : 10)) {
          notify(`Puedes añadir hasta ${axis === "rows" ? "20 filas" : "10 columnas"}.`, true);
          return;
        }
        field.configuration[axis].push({ id: uid(), label: `${axis === "rows" ? "Fila" : "Columna"} ${field.configuration[axis].length + 1}` });
      } else {
        if (field.configuration[axis].length <= 1) {
          notify("La cuadrícula necesita al menos una fila y una columna.", true);
          return;
        }
        field.configuration[axis].splice(+button.dataset.index, 1);
      }
    } else if (action === "add-section") {
      section = newSection();
      state.sections.push(section);
      active = section.id;
    } else if (["add-question", "add-text", "add-image"].includes(action)) {
      if (!section) {
        section = newSection();
        state.sections.push(section);
      }
      const f = newField(
        action === "add-text"
          ? "HEADING"
          : action === "add-image"
            ? "IMAGE"
            : "SINGLE_CHOICE",
      );
      const index = section.fields.findIndex((x) => x.id === active);
      section.fields.splice(
        index < 0 ? section.fields.length : index + 1,
        0,
        f,
      );
      active = f.id;
    } else if (action === "remove-section") {
      const removedKeys = new Set(section.fields.map((item) => item.stable_key));
      if (fields().some((item) => !removedKeys.has(item.stable_key) && removedKeys.has(item.configuration.option_filter?.source))) {
        notify("Esta sección contiene el agrupador de otro campo. Elimina primero el campo dependiente o muévelo a esta sección.", true);
        return;
      }
      if (
        section.fields.length &&
        !confirm("¿Eliminar esta sección, sus preguntas y sus condiciones?")
      )
        return;
      pruneRules([section.id, ...section.fields.map((f) => f.id)]);
      state.sections = state.sections.filter((s) => s !== section);
      for (const remaining of state.sections) {
        if (remaining.configuration?.next_section === section.id) {
          remaining.configuration.next_section = "NEXT";
          notify("Se retiró la sección de destino. Los saltos hacia ella ahora continúan a la siguiente sección.");
        }
      }
      active = null;
    } else if (action === "up-section" || action === "down-section") {
      const index = state.sections.indexOf(section),
        to = index + (action === "up-section" ? -1 : 1);
      if (to < 0 || to >= state.sections.length) return;
      [state.sections[index], state.sections[to]] = [
        state.sections[to],
        state.sections[index],
      ];
    } else if (action === "remove-question") {
      if (catalogChildren(field).length) { notify("Elimina primero los campos que dependen de este agrupador.", true); return; }
      pruneRules([field.id]);
      section.fields = section.fields.filter((f) => f !== field);
      active = section.id;
    } else if (action === "duplicate-question") {
      const f = structuredClone(field);
      f.id = uid();
      f.stable_key = `q_${uid().replaceAll("-", "_").replaceAll(".", "_")}`;
      f.label += " (copia)";
      section.fields.splice(section.fields.indexOf(field) + 1, 0, f);
      active = f.id;
      const groups = new Map();
      state.rules
        .filter((r) => r.target_field === field.id)
        .forEach((r) => {
          const copy = { ...r, target_field: f.id };
          if (r.group_key) {
            if (!groups.has(r.group_key)) groups.set(r.group_key, uid());
            copy.group_key = groups.get(r.group_key);
          }
          state.rules.push(copy);
        });
    } else if (action === "add-option")
      field.options.push({
        label: `Opción ${field.options.length + 1}`,
        value: uid(),
        is_active: true,
      });
    else if (action === "remove-option") {
      const value = field.options[+button.dataset.option].value;
      if (
        state.rules.some(
          (r) =>
            r.source === field.id &&
            (r.expected === value ||
              (Array.isArray(r.expected) && r.expected.includes(value))),
        )
      ) {
        notify(
          "Esta opción se usa en una condición. Modifica o elimina esa condición antes de quitar la opción.",
          true,
        );
        return;
      }
      field.options.splice(+button.dataset.option, 1);
      if (field.configuration.additional_text_option === value)
        field.configuration.additional_text_option = field.options.find((option) => option.is_active)?.value || "";
    } else if (action === "upload-option-image") {
      imageTarget = { field: field.id, option: field.options[+button.dataset.option].value };
      document.getElementById("image-upload").click();
      return;
    } else if (action === "remove-option-image") {
      Object.assign(field.options[+button.dataset.option], { image: null, image_url: "" });
    } else if (action === "upload-image") {
      imageTarget = field.id;
      document.getElementById("image-upload").click();
      return;
    } else if (action === "remove-image") {
      field.image = null;
      field.image_url = "";
    } else if (action === "toggle-description") {
      const expanded = !descriptionVisible(field);
      expandedDescriptions.set(field.id, expanded);
      closeTypeMenu();
      const input = card.querySelector(".question-help");
      input.hidden = !expanded;
      button.setAttribute("aria-checked", String(expanded));
      const target = expanded ? input : card.querySelector('.question-more-picker > [data-action="toggle-type-menu"]');
      target?.focus({ preventScroll: true });
      return;
    } else if (action === "toggle-additional-settings") {
      const expanded = !(expandedAdditional.get(field.id) ?? true);
      expandedAdditional.set(field.id, expanded);
      closeTypeMenu();
      const settings = document.getElementById(`additional-settings-${field.id}`);
      settings.hidden = !expanded;
      button.setAttribute("aria-expanded", String(expanded));
      button.focus({ preventScroll: true });
      return;
    } else if (action === "toggle-branches") {
      const open =
        expandedBranches.get(field.id) ??
        state.rules.some((r) => simpleBranch(r, field));
      expandedBranches.set(field.id, !open);
      render();
      const updatedCard = container.querySelector(`[data-field="${CSS.escape(field.id)}"]`);
      const target = open ? updatedCard.querySelector('.question-more-picker > [data-action="toggle-type-menu"]')
        : updatedCard.querySelector('[data-branch-answer]');
      target?.focus({ preventScroll: true });
      return;
    } else if (action === "add-branch") {
      const draft = { id: uid(), answer: "any" };
      const drafts = branchDrafts.get(field.id) || [];
      drafts.push(draft);
      branchDrafts.set(field.id, drafts);
      render();
      focusBranch(field, `draft-${draft.id}`, "[data-branch-answer]");
      return;
    } else if (action === "choose-branch-target") {
      updateBranch(field, button.closest(".branch-rule"), button.dataset.target);
      return;
    } else if (action === "remove-branch") {
      const row = button.closest(".branch-rule");
      if (row.dataset.branchRule !== "") {
        state.rules.splice(Number(row.dataset.branchRule), 1);
        changed();
      } else branchDrafts.set(field.id, branchDrafts.get(field.id).filter((draft) => draft.id !== row.dataset.branchDraft));
      render();
      container.querySelector(`[data-field="${CSS.escape(field.id)}"] [data-action="add-branch"]`)?.focus({ preventScroll: true });
      return;
    } else if (action === "remove-rule")
      state.rules.splice(+button.dataset.rule, 1);
    else return;
    changed();
    render();
    if (
      [
        "add-question",
        "add-text",
        "add-image",
        "add-section",
        "duplicate-question",
      ].includes(action)
    )
      focusCard(active);
  });
  document
    .getElementById("image-upload")
    .addEventListener("change", async (e) => {
      const file = e.target.files[0],
        target = imageTarget;
      e.target.value = "";
      if (!file || busy) return;
      if (file.size > 5 * 1024 * 1024) {
        notify("La imagen debe pesar hasta 5 MB.", true);
        return;
      }
      busy = true;
      status.textContent = "Subiendo imagen…";
      updateHistoryButtons();
      const payload = new FormData();
      payload.append("image", file);
      try {
        await initializeForm();
        const response = await fetch(root.dataset.base + "image/", {
          method: "POST",
          headers: { "X-CSRFToken": csrf },
          body: payload,
        });
        const data = await response.json();
        if (!response.ok)
          throw new Error(data.error || "No se pudo subir la imagen.");
        const field = findField(target && typeof target === "object" ? target.field : target);
        if (target === "welcome") {
          Object.assign(welcomeSettings(), { image: data.id, image_url: data.url });
          changed();
          renderWelcome(false);
        } else if (field && typeof target === "object") {
          const option = field.options.find((item) => item.value === target.option);
          if (option) {
            Object.assign(option, { image: data.id, image_url: data.url });
            changed();
            render();
          }
        } else if (field) {
          field.image = data.id;
          field.image_url = data.url;
          changed();
          render();
        }
      } catch (error) {
        notify(error.message, true);
        status.textContent = "La imagen no se subió";
      } finally {
        busy = false;
        updateHistoryButtons();
      }
    });
  window.addEventListener("beforeunload", (e) => {
    if (dirty || busy) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  document.addEventListener("click", (e) => {
    if (openTypeMenu && !e.composedPath().includes(openTypeMenu.parentElement)) closeTypeMenu();
    // Rendering a panel replaces its button before the click reaches document.
    // The original event path still identifies it as a click inside the editor.
    if (!busy && !e.composedPath().includes(root)) selectCard(null);
  });
  window.addEventListener("resize", positionTypeMenu);
  root.addEventListener("builder:tab-change", (event) => {
    closeTypeMenu();
    if (event.detail !== "questions") setThemePanel(false);
  });
  window.addEventListener("resize", positionThemePanel);
  window.addEventListener("scroll", positionThemePanel, { passive: true, capture: true });
  window.addEventListener("scroll", positionTypeMenu, true);
  window.visualViewport?.addEventListener("resize", positionTypeMenu);
  if (!state.sections.length) {
    state.sections.push(newSection());
    state.sections[0].fields.push(newField());
    changed();
  }
  render();
  updateHistoryButtons();
})();
