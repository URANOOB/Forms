(() => {
  const schema = JSON.parse(document.getElementById("form-schema").textContent);
  const form = document.getElementById("public-form");
  const welcome = document.getElementById("welcome-screen");
  const content = document.getElementById("form-content");
  const page = document.querySelector("main.page");
  document.getElementById("welcome-start")?.addEventListener("click", () => {
    welcome.hidden = true;
    content.hidden = false;
    page.classList.remove("showing-welcome");
    const heading = content.querySelector("h1");
    heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
    page.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("welcome-back")?.addEventListener("click", () => {
    content.hidden = true;
    welcome.hidden = false;
    page.classList.add("showing-welcome");
    document.getElementById("welcome-start").focus({ preventScroll: true });
    page.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  const empty = (value) =>
    value == null || value === "" || (typeof value === "object" && !Object.keys(value).length);
  const grids = new Set(["GRID_SINGLE", "GRID_MULTIPLE"]);
  const uploads = new Set(["FILE", "DOCUMENT"]);
  const groupsByField = Object.fromEntries(schema.order.map((key) => [key, []]));
  for (const group of schema.groups) {
    for (const target of group.targets) groupsByField[target].push(group);
  }
  const keysBySection = Object.fromEntries(schema.sections.map((key) => [key, []]));
  for (const key of schema.order) keysBySection[schema.fields[key].section].push(key);
  const retainedFiles = (container) => [...container.querySelectorAll("[data-stored-file]")].filter((input) => !input.checked);
  const compare = (value, operator, expected) => {
    switch (operator) {
      case "IS_EMPTY":
        return empty(value);
      case "IS_NOT_EMPTY":
        return !empty(value);
      case "EQUALS":
        return JSON.stringify(value) === JSON.stringify(expected);
      case "NOT_EQUALS":
        return JSON.stringify(value) !== JSON.stringify(expected);
      case "CONTAINS":
        return (
          (typeof value === "string" || Array.isArray(value)) &&
          value.includes(expected)
        );
      case "GREATER_THAN":
        return !empty(value) && value > expected;
      case "LESS_THAN":
        return !empty(value) && value < expected;
      default:
        return false;
    }
  };
  const containers = Object.fromEntries(
    schema.order.map((key) => [
      key,
      document.querySelector(`[data-field="${key}"]`),
    ]),
  );
  function valueFor(key) {
    const field = schema.fields[key];
    const inputs = [
      ...containers[key].querySelectorAll("input,select,textarea"),
    ];
    if (!inputs.length) return null;
    if (grids.has(field.type)) {
      const value = {};
      for (const row of containers[key].querySelectorAll("[data-grid-row]")) {
        const selected = [...row.querySelectorAll("input:checked")].map((input) => input.value);
        if (selected.length) value[row.dataset.gridRow] = field.type === "GRID_MULTIPLE" ? selected : selected[0];
      }
      return value;
    }
    if (uploads.has(field.type)) return [...inputs[0].files, ...retainedFiles(containers[key])];
    if (["LINEAR_SCALE", "RATING"].includes(field.type)) {
      const value = inputs.find((input) => input.checked)?.value;
      return value === undefined ? null : Number(value);
    }
    if (field.type === "MULTIPLE_CHOICE")
      return inputs
        .filter((input) => input.checked)
        .map((input) => input.value);
    if (field.type === "SINGLE_CHOICE" && inputs[0].type === "radio")
      return inputs.find((input) => input.checked)?.value || "";
    const value = inputs[0].value.trim();
    // La obligatoriedad se evalúa después; las demás restricciones invalidan fuentes erróneas.
    const validity = inputs[0].validity;
    if (
      validity.typeMismatch ||
      validity.badInput ||
      validity.rangeOverflow ||
      validity.rangeUnderflow ||
      validity.tooLong ||
      validity.tooShort
    )
      return null;
    if (field.type === "BOOLEAN") return value === "" ? null : value === "true";
    if (field.type === "TIME") return value.length === 5 ? `${value}:00` : value;
    if (
      field.type === "PHONE" &&
      value &&
      !/^[0-9]{6,25}$/.test(value)
    )
      return null;
    if (field.type === "NUMBER" && value) {
      if (!/^[0-9]+$/.test(value)) return null;
      if (inputs[0].hasAttribute("min") && Number(value) < Number(inputs[0].min)) return null;
      if (inputs[0].hasAttribute("max") && Number(value) > Number(inputs[0].max)) return null;
    }
    if (field.type === "NUMBER")
      return value === "" || !Number.isSafeInteger(Number(value))
        ? null
        : Number(value);
    return value;
  }
  const sectionElements = Object.fromEntries(
    [...form.querySelectorAll("[data-section]")].map((section) => [section.dataset.section, section]),
  );
  const button = document.getElementById("submit-button");
  const nextButton = document.getElementById("next-button");
  const backButton = document.getElementById("back-button");
  const progress = document.getElementById("section-progress");
  const status = document.getElementById("submit-status");
  let current = null;
  let route = [];
  let states = {};

  function evaluate(values, allowed) {
    values = { ...values };
    const states = {};
    for (const key of schema.order) {
      const groups = groupsByField[key];
      const visibility = Object.fromEntries(
        ["field", "section"].map((scope) => [
          scope,
          !groups.some(
            (group) => group.action === "SHOW" && group.scope === scope,
          ),
        ]),
      );
      let required = schema.fields[key].required;
      for (const group of groups) {
        const results = group.conditions.map(
          (condition) =>
            states[condition.source].visible &&
            compare(
              values[condition.source],
              condition.operator,
              condition.expected,
            ),
        );
        if (
          group.operator === "AND"
            ? results.every(Boolean)
            : results.some(Boolean)
        ) {
          if (group.action === "SHOW") visibility[group.scope] = true;
          if (group.action === "HIDE") visibility[group.scope] = false;
          if (group.action === "REQUIRE") required = true;
          if (group.action === "OPTIONAL") required = false;
        }
      }
      const visible = visibility.field && visibility.section && allowed.has(schema.fields[key].section);
      const relation = schema.fields[key].option_filter;
      let available = true;
      if (relation) {
        const parent = values[relation.source];
        available = states[relation.source].visible && !empty(parent);
        if (!available || !relation.values[values[key]]?.includes(parent)) values[key] = null;
      }
      states[key] = { visible, required: visible && available && required, available };
    }
    return states;
  }

  function update() {
    const values = Object.fromEntries(schema.order.map((key) => [key, valueFor(key)]));
    const previousRoute = route;
    route = [];
    let candidate = schema.sections[0];
    while (candidate) {
      const candidateStates = evaluate(values, new Set([...route, candidate]));
      const keys = keysBySection[candidate];
      const visible = !keys.length || keys.some((key) => candidateStates[key].visible);
      if (visible) route.push(candidate);
      candidate = schema.navigation[candidate][visible ? "next" : "following"];
    }
    states = evaluate(values, new Set(route));
    if (!route.includes(current)) {
      const previousIndex = previousRoute.indexOf(current);
      current = previousRoute.slice(0, previousIndex).reverse().find((id) => route.includes(id)) || route[0];
    }
    for (const key of schema.order) {
      const { visible, required, available } = states[key];
      const container = containers[key];
      container.hidden = !visible;
      const relation = schema.fields[key].option_filter;
      if (relation) {
        const select = container.querySelector("select");
        const parent = values[relation.source];
        const signature = JSON.stringify([parent, available]);
        if (select.dataset.catalogParent !== signature) {
          select.dataset.catalogParent = signature;
          for (const option of select.options) {
            if (!option.value) {
              option.textContent = available ? "Seleccione una opción" : "Seleccione primero el agrupador";
              continue;
            }
            option.hidden = option.disabled = !available || !relation.values[option.value]?.includes(parent);
          }
          if (!available || !relation.values[select.value]?.includes(parent)) {
            select.value = "";
            values[key] = "";
          }
          select.dispatchEvent(new CustomEvent("catalog:options-updated", { bubbles: true }));
        }
      }
      const inputs = [...container.querySelectorAll("input,select,textarea")];
      for (const input of inputs) {
        if (input.hasAttribute("data-additional-text")) {
          const config = schema.fields[key].additional_text;
          const selected = config?.values.includes(values[key]);
          const needed = visible && selected;
          input.closest("[data-additional-container]").hidden = !needed;
          input.disabled = !needed;
          input.required = Boolean(needed);
          if (!selected) input.value = "";
          let error = "";
          if (needed) {
            if (input.validity.badInput) error = "Ingrese un número válido.";
            else if (!input.value.trim()) error = "Complete este campo adicional.";
            else if (config.type === "number" && !/^[0-9]+$/.test(input.value)) error = "Este campo solo admite números del 0 al 9.";
            else if (config.type === "number" && !Number.isFinite(Number(input.value))) error = "Ingrese un número finito.";
            else if (input.validity.typeMismatch) error = "Ingrese un correo electrónico válido.";
            else if (input.value.length > 500) error = "El campo adicional admite hasta 500 caracteres.";
          }
          input.setCustomValidity(error);
          continue;
        }
        input.disabled = !visible || !available;
        input.required =
          required && !input.hasAttribute("data-stored-file")
          && !(uploads.has(schema.fields[key].type) && retainedFiles(container).length)
          && !["MULTIPLE_CHOICE", "GRID_MULTIPLE"].includes(schema.fields[key].type);
        let error = "";
        if (visible && input.hasAttribute("data-digits-only") && input.value) {
          if (!/^[0-9]+$/.test(input.value)) error = "Este campo solo admite números del 0 al 9.";
          else if (schema.fields[key].type === "PHONE" && !/^[0-9]{6,25}$/.test(input.value)) error = "Ingrese un teléfono de 6 a 25 dígitos.";
          else if (schema.fields[key].type === "NUMBER") {
            const number = Number(input.value);
            if (!Number.isSafeInteger(number)) error = "El número máximo admitido es 9007199254740991. Para identificadores más largos, utiliza un campo de texto.";
            else if (input.hasAttribute("min") && number < Number(input.min)) error = `El valor mínimo permitido es ${input.min}.`;
            else if (input.hasAttribute("max") && number > Number(input.max)) error = `El valor máximo permitido es ${input.max}.`;
          }
        }
        input.setCustomValidity(error);
      }
      if (
        visible &&
        required &&
        schema.fields[key].type === "MULTIPLE_CHOICE" &&
        !inputs.some((input) => input.checked)
      ) {
        inputs[0]?.setCustomValidity("Seleccione al menos una opción.");
      }
      if (visible && required && schema.fields[key].type === "GRID_MULTIPLE") {
        for (const row of container.querySelectorAll("[data-grid-row]")) {
          if (!row.querySelector("input:checked")) row.querySelector("input")?.setCustomValidity("Seleccione al menos una opción en esta fila.");
        }
      }
      if (visible && uploads.has(schema.fields[key].type)) {
        const input = inputs[0], files = [...input.files];
        const extensions = input.accept.split(",").map((value) => value.trim().toLowerCase());
        let error = "";
        if (Number(input.dataset.uploadPending) > 0) error = "Revise y confirme los archivos seleccionados antes de continuar.";
        else if (files.length + retainedFiles(container).length > Number(input.dataset.maxFiles)) error = `Puede conservar hasta ${input.dataset.maxFiles} archivo(s), incluidos los nuevos.`;
        else if (files.some((file) => file.size > Number(input.dataset.maxBytes))) error = "Un archivo supera el tamaño máximo permitido.";
        else if (files.some((file) => !extensions.some((extension) => file.name.toLowerCase().endsWith(extension)))) error = "Uno de los archivos tiene un formato no permitido.";
        input.setCustomValidity(error);
      }
      const marker = container.querySelector("[data-required]");
      if (marker) marker.hidden = !required;
    }
    for (const [id, section] of Object.entries(sectionElements)) {
      section.hidden = id !== current;
    }
    const index = route.indexOf(current);
    backButton.hidden = index <= 0;
    nextButton.hidden = index < 0 || index === route.length - 1;
    button.hidden = !nextButton.hidden;
    progress.hidden = !current;
    progress.textContent = current ? `Sección ${index + 1} de ${route.length}` : "";
    if (form.dataset.preview) button.textContent = "Finalizar vista previa";
  }

  function goTo(id, focus = true) {
    current = id;
    status.textContent = "";
    update();
    if (!focus) return;
    const heading = sectionElements[current]?.querySelector("h2") || sectionElements[current];
    heading?.focus({ preventScroll: true });
    (sectionElements[current] || form).scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function validateSection(id) {
    const invalid = [...sectionElements[id].querySelectorAll("input,select,textarea")]
      .find((input) => !input.disabled && !input.checkValidity());
    if (!invalid) return true;
    goTo(id, false);
    invalid.reportValidity();
    invalid.focus();
    return false;
  }
  form.addEventListener("beforeinput", (event) => {
    if (event.target.hasAttribute("data-digits-only") && event.inputType === "insertText" && event.data && /[^0-9]/.test(event.data)) event.preventDefault();
  });
  form.addEventListener("input", (event) => {
    const input = event.target;
    if (input.hasAttribute("data-digits-only")) {
      const original = input.value;
      const cleaned = original.replace(/[^0-9]/g, "");
      if (original !== cleaned) {
        const position = original.slice(0, input.selectionStart ?? original.length).replace(/[^0-9]/g, "").length;
        input.value = cleaned;
        input.setSelectionRange(position, position);
      }
    }
    update();
  });
  form.addEventListener("change", update);
  nextButton.addEventListener("click", () => {
    update();
    if (current && validateSection(current)) goTo(route[route.indexOf(current) + 1]);
  });
  backButton.addEventListener("click", () => {
    update();
    goTo(route[route.indexOf(current) - 1]);
  });
  form.addEventListener("submit", (event) => {
    update();
    if (!nextButton.hidden) {
      event.preventDefault();
      nextButton.click();
      return;
    }
    for (const id of route) {
      if (!validateSection(id)) {
        event.preventDefault();
        return;
      }
    }
    if (schema.max_submission_bytes) {
      const encoder = new TextEncoder();
      let size = 0;
      for (const [name, value] of new FormData(form)) {
        size += encoder.encode(name).length + 1024 +
          (value instanceof File ? value.size + encoder.encode(value.name).length : encoder.encode(value).length);
      }
      if (size > schema.max_submission_bytes) {
        event.preventDefault();
        status.textContent = `La respuesta completa, incluidos los archivos, admite hasta ${schema.max_submission_bytes / 1000000} MB. Reduce el tamaño de los adjuntos.`;
        return;
      }
    }
    if (form.dataset.preview) {
      event.preventDefault();
      status.textContent = "Vista previa completada. No se ha guardado ninguna respuesta.";
      return;
    }
    if (button.disabled) {
      event.preventDefault();
      return;
    }
    button.disabled = true;
    status.textContent = form.dataset.edit ? "Guardando cambios…" : "Enviando respuesta…";
  });
  window.addEventListener("pageshow", () => {
    button.disabled = false;
    status.textContent = "";
    update();
  });
  update();
  const firstError = form.querySelector("[data-field] .errorlist");
  if (firstError) goTo(firstError.closest("[data-section]").dataset.section, false);
  document.getElementById("error-summary")?.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    const target = link && document.getElementById(link.hash.slice(1));
    const section = target?.closest("[data-section]");
    if (section && route.includes(section.dataset.section)) {
      event.preventDefault();
      goTo(section.dataset.section, false);
      (target.matches("input,select,textarea") ? target : target.querySelector("input,select,textarea") || target).focus();
      target.scrollIntoView({ block: "center" });
    }
  });
  document.getElementById("error-summary")?.focus();
})();
