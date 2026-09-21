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
    MULTIPLE_CHOICE: "check_box", DROPDOWN: "arrow_drop_down_circle", FILE: "cloud_upload",
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
  function changed() {
    dirty = true;
    status.textContent = "Cambios sin guardar";
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
      rule.operator ===
        (field.field_type === "MULTIPLE_CHOICE" ? "CONTAINS" : "EQUALS") &&
      (!rule.group_key ||
        state.rules.filter((r) => r.group_key === rule.group_key).length === 1)
    );
  }
  function answerBranches(field) {
    if (!canBranch(field)) return "";
    const branches = state.rules
      .map((rule, index) => ({ rule, index }))
      .filter(({ rule }) => simpleBranch(rule, field));
    if (!(expandedBranches.get(field.id) ?? branches.length > 0)) return "";
    const answers =
      field.field_type === "BOOLEAN"
        ? [
            [true, "Sí"],
            [false, "No"],
          ]
        : field.options
            .filter((o) => o.is_active)
            .map((o) => [o.value, o.label]);
    const targets = state.sections.flatMap((section) => [
      ...(!section.fields.includes(field) && section.fields.length
        ? [[`s:${section.id}`, `Sección: ${section.title}`]]
        : []),
      ...section.fields
        .filter((f) => f.id !== field.id)
        .map((f) => [
          `f:${f.id}`,
          `${display.has(f.field_type) ? "Bloque" : "Pregunta"}: ${f.label}`,
        ]),
    ]);
    let html =
      '<div class="answer-branches"><h3>Mostrar según respuesta</h3><p>Elige qué pregunta, imagen o sección aparece al seleccionar cada respuesta. Ese contenido estará oculto hasta entonces.</p>';
    for (const [value, label] of answers) {
      const matching = branches.filter(({ rule }) => rule.expected === value);
      html += `<div class="answer-branch"><div class="branch-answer">Si ${field.field_type === "BOOLEAN" ? "responde" : "selecciona"} <strong>${esc(label)}</strong></div>`;
      for (const entry of [...matching, null]) {
        const current = entry
          ? entry.rule.target_field
            ? `f:${entry.rule.target_field}`
            : `s:${entry.rule.target_section}`
          : "";
        html += `<div class="branch-destination"><span aria-hidden="true">↳</span><span>Mostrar</span><select data-branch-source="${esc(field.id)}" data-branch-answer="${esc(JSON.stringify(value))}" data-branch-rule="${entry ? entry.index : ""}" aria-label="Componente para ${esc(label)}">${options([["", entry ? "Quitar este componente" : matching.length ? "Añadir otro componente…" : "Selecciona un componente…"], ...targets], current)}</select>${entry ? icon("remove-rule", "close", "Quitar componente condicional", `data-rule="${entry.index}"`) : ""}</div>`;
      }
      html += "</div>";
    }
    if (!targets.length)
      html +=
        "<p>Añade otra pregunta o sección para poder seleccionarla aquí.</p>";
    html +=
      '<p class="branch-hint">Puedes encadenarlas: Sí → mostrar una lista; un elemento de esa lista → mostrar otra pregunta o sección. Si cambia la respuesta, el contenido que ya no corresponde se oculta.</p></div>';
    return html;
  }
  function typeOptions(field) {
    const value = field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio"
      ? "DROPDOWN" : field.field_type === "DOCUMENT" ? "FILE" : field.field_type;
    const available = [
      "SHORT_TEXT", "LONG_TEXT", "SINGLE_CHOICE", "MULTIPLE_CHOICE", "DROPDOWN",
      "FILE", "LINEAR_SCALE", "RATING", "GRID_SINGLE", "GRID_MULTIPLE", "DATE", "TIME",
    ];
    // Keep existing fields accurately labelled without offering their legacy types.
    const current = !available.includes(value)
      ? `<option value="${esc(value)}" selected disabled hidden>${esc(types.find(([key]) => key === value)?.[1] || value)}</option>`
      : "";
    return current + options(available.map((key) => types.find(([type]) => type === key)), value);
  }
  function typePicker(field) {
    const value = field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio"
      ? "DROPDOWN" : field.field_type === "DOCUMENT" ? "FILE" : field.field_type;
    const label = types.find(([key]) => key === value)?.[1] || value;
    const symbol = (key) => `<span class="material-symbols-outlined" aria-hidden="true">${questionTypeIcons[key] || "help_outline"}</span>`;
    const available = ["SHORT_TEXT", "LONG_TEXT", "SINGLE_CHOICE", "MULTIPLE_CHOICE", "DROPDOWN", "FILE", "LINEAR_SCALE", "RATING", "GRID_SINGLE", "GRID_MULTIPLE", "DATE", "TIME"];
    const menuId = `type-menu-${field.id}`;
    return `<div class="question-type-picker"><select data-prop="field_type" hidden aria-label="Tipo de pregunta">${typeOptions(field)}</select><button type="button" class="question-type" data-action="toggle-type-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="${esc(menuId)}" aria-label="Tipo de pregunta: ${esc(label)}">${symbol(value)}<span class="question-type-label">${esc(label)}</span><span class="material-symbols-outlined" aria-hidden="true">expand_more</span></button><div id="${esc(menuId)}" class="question-type-menu" popover="manual" role="menu" aria-label="Tipo de pregunta">${available.map((key) => `<button type="button" role="menuitemradio" aria-checked="${key === value}" tabindex="-1" data-action="choose-question-type" data-type="${key}">${symbol(key)}<span>${esc(types.find(([type]) => type === key)?.[1] || key)}</span></button>`).join("")}</div></div>`;
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
  function settingsFor(field) {
    const config = field.configuration;
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
  function questionPreview(field) {
    let answer = "";
    if (choices.has(field.field_type)) {
      const entries = field.options.filter((option) => option.is_active);
      if (field.field_type === "SINGLE_CHOICE" && field.configuration.widget !== "radio") {
        answer = '<span class="preview-dropdown">Selecciona una opción <span aria-hidden="true">⌄</span></span>';
      } else {
        answer = `<span class="preview-options">${entries.slice(0, 4).map((option) => `<span class="preview-option"><span class="option-marker ${field.field_type === "MULTIPLE_CHOICE" ? "square" : ""}" aria-hidden="true"></span><span>${esc(option.label)}</span></span>`).join("")}${entries.length > 4 ? `<span class="preview-more">+ ${entries.length - 4} opciones</span>` : ""}</span>`;
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
    return `<span class="preview-title">${esc(field.label || "Pregunta sin título")}${field.required ? '<span class="preview-required" aria-label="Obligatoria"> *</span>' : ""}</span>${field.help_text ? `<span class="preview-help">${esc(field.help_text)}</span>` : ""}${field.image_url ? `<img class="preview-image" src="${esc(field.image_url)}" alt="">` : ""}${answer}`;
  }
  function selectCard(id) {
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
  }
  function question(field, section) {
    let body = "";
    if (choices.has(field.field_type)) {
      body = `<div class="option-list">${field.options.map((o, i) => `<div class="option-row"><span class="option-marker ${field.field_type === "MULTIPLE_CHOICE" ? "square" : ""}" aria-hidden="true"></span><input data-option="${i}" maxlength="240" aria-label="Opción ${i + 1}" value="${esc(o.label)}">${icon("remove-option", "close", "Quitar opción", `data-option="${i}"`)}</div>`).join("")}<button type="button" class="text-button" data-action="add-option">＋ Añadir opción</button></div>`;
    } else if (grids.has(field.field_type) || files.has(field.field_type) || ["LINEAR_SCALE", "RATING"].includes(field.field_type))
      body = settingsFor(field);
    else if (!display.has(field.field_type))
      body = `<div class="answer-placeholder">${esc({ BOOLEAN: "Sí / No", NUMBER: "Respuesta numérica", DATE: "Día / mes / año", TIME: "Hora : minutos", LONG_TEXT: "Texto de respuesta larga" }[field.field_type] || "Texto de respuesta corta")}</div>`;
    if (field.image_url)
      body += `<img class="question-image" src="${esc(field.image_url)}" alt="${esc(field.label)}"><button type="button" class="text-button" data-action="remove-image">Quitar imagen</button>`;
    else if (field.field_type === "IMAGE")
      body +=
        '<div class="image-empty"><button type="button" class="text-button" data-action="upload-image">Seleccionar imagen</button><p>PNG, JPG o WebP · Hasta 5 MB</p></div>';
    return `<article class="question-card ${active === field.id ? "active" : ""}" data-field="${esc(field.id)}"><button type="button" class="question-preview" data-action="activate-question" aria-label="Editar: ${esc(field.label || "Pregunta sin título")}" ${active === field.id ? "hidden" : ""}>${questionPreview(field)}</button><div class="question-editor" ${active === field.id ? "" : "hidden"}><span class="question-grip" aria-hidden="true">⠿</span><div class="question-top"><input class="question-title" data-prop="label" maxlength="240" aria-label="Título de la pregunta" value="${esc(field.label)}">${typePicker(field)}</div><input class="question-help" data-prop="help_text" maxlength="10000" aria-label="Descripción de la pregunta" placeholder="Descripción (opcional)" value="${esc(field.help_text)}">${body}<footer class="question-footer"><div class="question-logic">${canBranch(field) ? `<button type="button" class="text-button" data-action="toggle-branches">Mostrar según respuesta${state.rules.some((r) => simpleBranch(r, field)) ? " •" : ""}</button>` : ""}</div><div class="question-actions">${icon("upload-image", "image", "Añadir o cambiar imagen")}${icon("duplicate-question", "content_copy", "Duplicar pregunta")}${icon("up-question", "arrow_upward", "Subir pregunta")}${icon("down-question", "arrow_downward", "Bajar pregunta")}${icon("remove-question", "delete", "Eliminar pregunta")}${!display.has(field.field_type) ? `<label class="required-toggle">Obligatorio <input type="checkbox" data-prop="required" ${field.required ? "checked" : ""}></label>` : ""}</div></footer>${answerBranches(field)}</div></article>`;
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
    const heading = hideHeader ? "" : `<div class="section-card"><input class="section-title" data-section-prop="title" maxlength="200" aria-label="Título de la sección" value="${esc(section.title)}"><textarea data-section-prop="description" rows="1" maxlength="10000" aria-label="Descripción de la sección" placeholder="Descripción (opcional)">${esc(section.description)}</textarea></div>`;
    return `<div class="section-toolbar"><div class="section-badge">Sección ${index + 1} de ${state.sections.length}</div><label class="section-header-toggle"><input type="checkbox" data-section-header ${hideHeader ? "" : "checked"}> ${hideHeader ? "Añadir título y descripción" : "Mostrar título y descripción"}</label><div class="section-actions">${icon("up-section", "arrow_upward", "Subir sección")}${icon("down-section", "arrow_downward", "Bajar sección")}${icon("remove-section", "delete", "Eliminar sección")}</div></div>${heading}`;
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
    changed();
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
          `<section class="builder-section" data-section="${esc(section.id)}">${sectionHeader(section, i)}${section.fields.map((f) => question(f, section)).join("")}<button type="button" class="text-button" data-action="add-question">＋ Añadir pregunta aquí</button>${sectionNavigation(section, i)}</section>`,
      )
      .join("");
    if (root.dataset.archived)
      root
        .querySelectorAll("button,input,select,textarea")
        .forEach((el) => {
          if (!el.closest(".builder-tabs, #builder-responses-panel, .builder-sidebar-toggle")) el.disabled = true;
        });
  }
  function focusCard(id) {
    root
      .querySelector(
        `[data-field="${CSS.escape(id)}"], [data-section="${CSS.escape(id)}"]`,
      )
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
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
    card.querySelector(".question-preview").focus();
  });
  root.addEventListener("input", (e) => {
    const el = e.target;
    if (el.dataset.theme) { updateTheme(el); return; }
    if (el.dataset.formSetting) {
      state[el.dataset.formSetting] = el.value;
      if (el.dataset.formSetting === "title") document.getElementById("form-title").value = el.value;
      changed();
      renderWelcome(false);
      return;
    }
    if (el.dataset.welcome) {
      welcomeSettings()[el.dataset.welcome] = el.value;
      changed();
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
      if (el.dataset.config) f.configuration[el.dataset.config] = el.value;
      else if (el.dataset.axis) f.configuration[el.dataset.axis][+el.dataset.axisIndex].label = el.value;
      else if (el.hasAttribute("data-option"))
        f.options[+el.dataset.option].label = el.value;
      else if (el.dataset.prop) f[el.dataset.prop] = el.value;
      else return;
    } else return;
    changed();
  });
  root.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.theme) { updateTheme(el); return; }
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
    if (el.hasAttribute("data-branch-source")) {
      const field = findField(el.dataset.branchSource);
      const index =
        el.dataset.branchRule === "" ? null : Number(el.dataset.branchRule);
      const expected = JSON.parse(el.dataset.branchAnswer);
      if (!el.value) {
        if (index !== null) state.rules.splice(index, 1);
      } else {
        const [kind, id] = el.value.split(":");
        const rule = {
          source: field.id,
          operator:
            field.field_type === "MULTIPLE_CHOICE" ? "CONTAINS" : "EQUALS",
          expected,
          action: "SHOW",
          target_field: kind === "f" ? id : null,
          target_section: kind === "s" ? id : null,
          group_key: null,
          group_operator: "AND",
        };
        if (
          state.rules.some(
            (r, i) =>
              i !== index &&
              simpleBranch(r, field) &&
              r.expected === expected &&
              r.target_field === rule.target_field &&
              r.target_section === rule.target_section,
          )
        ) {
          notify("Este componente ya aparece con esa respuesta.");
          render();
          return;
        }
        if (index === null) state.rules.push(rule);
        else state.rules[index] = rule;
      }
      expandedBranches.set(field.id, true);
      changed();
      render();
      return;
    }
    const card = el.closest("[data-field]");
    if (!card || !el.dataset.prop) return;
    const field = findField(card.dataset.field),
      prop = el.dataset.prop;
    if (prop === "required") field.required = el.checked;
    else if (prop === "field_type") {
      const kind = el.value === "DROPDOWN" ? "SINGLE_CHOICE" : el.value;
      if (kind === "SINGLE_CHOICE" && field.field_type === kind) {
        field.configuration.widget = el.value === "DROPDOWN" ? "select" : "radio";
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
      if (kind === "SINGLE_CHOICE") field.configuration.widget = el.value === "DROPDOWN" ? "select" : "radio";
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
    busy = true;
    notify("");
    status.textContent = publish ? "Publicando…" : "Guardando…";
    const controls = [...root.querySelectorAll("input,textarea,select,button")];
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
      document.getElementById("form-title").value = state.title;
      dirty = false;
      active = null;
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
      controls.forEach((el) => (el.disabled = false));
      renderSettings();
    }
  }
  root.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-action]");
    if (!button && !busy) {
      const card = e.target.closest(".question-card");
      if (card && active !== card.dataset.field) selectCard(card.dataset.field);
      else if (!card && e.target.closest(".builder-canvas")) {
        selectCard(e.target.closest("[data-section]")?.dataset.section || null);
      }
    }
    if (!button || busy) return;
    const action = button.dataset.action;
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
    if (action === "choose-question-type") {
      const picker = button.closest(".question-type-picker");
      const fieldId = picker.closest("[data-field]").dataset.field;
      const select = picker.querySelector("select");
      closeTypeMenu(true);
      if (select.value !== button.dataset.type) {
        select.value = button.dataset.type;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        root.querySelector(`[data-field="${CSS.escape(fieldId)}"] [data-action="toggle-type-menu"]`)?.focus({ preventScroll: true });
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
    } else if (action === "up-question" || action === "down-question") {
      const index = section.fields.indexOf(field),
        to = index + (action === "up-question" ? -1 : 1);
      if (to < 0 || to >= section.fields.length) return;
      [section.fields[index], section.fields[to]] = [
        section.fields[to],
        section.fields[index],
      ];
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
    } else if (action === "upload-image") {
      imageTarget = field.id;
      document.getElementById("image-upload").click();
      return;
    } else if (action === "remove-image") {
      field.image = null;
      field.image_url = "";
    } else if (action === "toggle-branches") {
      const open =
        expandedBranches.get(field.id) ??
        state.rules.some((r) => simpleBranch(r, field));
      expandedBranches.set(field.id, !open);
      render();
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
        const field = findField(target);
        if (target === "welcome") {
          Object.assign(welcomeSettings(), { image: data.id, image_url: data.url });
          changed();
          renderWelcome(false);
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
  window.addEventListener("scroll", positionThemePanel, { passive: true });
  window.addEventListener("scroll", positionTypeMenu, true);
  window.visualViewport?.addEventListener("resize", positionTypeMenu);
  if (!state.sections.length) {
    state.sections.push(newSection());
    state.sections[0].fields.push(newField());
    changed();
  }
  render();
})();
