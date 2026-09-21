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
      !/^\+?[0-9().\-\s]{6,25}$/.test(value)
    )
      return null;
    if (field.type === "NUMBER")
      return value === "" || !Number.isFinite(Number(value))
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
    const states = {};
    for (const key of schema.order) {
      const groups = schema.groups.filter((group) =>
        group.targets.includes(key),
      );
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
      states[key] = { visible, required: visible && required };
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
      const keys = schema.order.filter((key) => schema.fields[key].section === candidate);
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
      const { visible, required } = states[key];
      const container = containers[key];
      container.hidden = !visible;
      const inputs = [...container.querySelectorAll("input,select,textarea")];
      for (const input of inputs) {
        input.disabled = !visible;
        input.required =
          required && !input.hasAttribute("data-stored-file")
          && !(uploads.has(schema.fields[key].type) && retainedFiles(container).length)
          && !["MULTIPLE_CHOICE", "GRID_MULTIPLE"].includes(schema.fields[key].type);
        input.setCustomValidity("");
      }
      if (
        visible &&
        required &&
        schema.fields[key].type === "MULTIPLE_CHOICE" &&
        !inputs.some((input) => input.checked)
      ) {
        inputs[0]?.setCustomValidity("Selecciona al menos una opción.");
      }
      if (visible && required && schema.fields[key].type === "GRID_MULTIPLE") {
        for (const row of container.querySelectorAll("[data-grid-row]")) {
          if (!row.querySelector("input:checked")) row.querySelector("input")?.setCustomValidity("Selecciona al menos una opción en esta fila.");
        }
      }
      if (visible && uploads.has(schema.fields[key].type)) {
        const input = inputs[0], files = [...input.files];
        const extensions = input.accept.split(",").map((value) => value.trim().toLowerCase());
        let error = "";
        if (files.length + retainedFiles(container).length > Number(input.dataset.maxFiles)) error = `Puedes conservar hasta ${input.dataset.maxFiles} archivo(s), contando los nuevos.`;
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
    progress.textContent = current ? `Sección ${schema.sections.indexOf(current) + 1} de ${schema.sections.length}` : "";
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
  form.addEventListener("input", update);
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
    status.textContent = form.dataset.edit ? "Guardando cambios…" : "Enviando tu respuesta…";
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
      target.focus();
      target.scrollIntoView({ block: "center" });
    }
  });
  document.getElementById("error-summary")?.focus();
})();
