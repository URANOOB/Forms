(() => {
  const root = document.getElementById("builder");
  const dialog = document.getElementById("catalog-import");
  if (!root || !dialog) return;
  const el = (name) => document.getElementById(`catalog-${name}`);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
  let result = null, proposal = null, definitions = [], pending = false, requestId = 0;
  let selectedFile = null, activeRequest = null;
  const status = (text, error = false) => { el("status").textContent = text; el("status").dataset.error = String(error); };
  const options = (items, selected) => items.map(([value, label]) => `<option value="${esc(value)}" ${String(value) === String(selected) ? "selected" : ""}>${esc(label)}</option>`).join("");
  const setOptions = (select, items, selected = "") => { select.innerHTML = options(items, selected); select.value = String(selected ?? ""); };
  const list = (name, items) => { el(name).innerHTML = items.map((item) => `<li>${esc(item)}</li>`).join(""); el(name).hidden = !items.length; };
  const columnOptions = (selected) => options(result.headers.map((header, i) => [i, `${i + 1}. ${header}`]), selected);
  const parentOptions = (index) => [["", "Sin dependencia"], ...definitions.slice(0, index).map((field, i) => [field.id, `${i + 1}. ${field.label || "Sin título"}`])];

  function invalidate() {
    proposal = null;
    el("apply").disabled = true;
    el("apply").textContent = "Añadir campos";
    el("preview-controls").hidden = true;
    el("preview-controls").replaceChildren();
    el("summary").textContent = definitions.length ? "Propuesta pendiente de actualizar" : "Sin campos configurados";
    el("explanation").textContent = definitions.length ? "Pulsa Actualizar propuesta para comprobar los campos y sus relaciones." : "Añade un campo para preparar una nueva propuesta.";
    list("issues", []); list("warnings", []);
    status(definitions.length ? "Actualiza la propuesta para probar tus cambios." : "Puedes empezar desde cero. El archivo y las columnas siguen disponibles.");
  }
  function renderFields() {
    el("fields").innerHTML = definitions.map((field, index) => `<fieldset class="catalog-field" data-field-index="${index}">
      <legend>Campo ${index + 1}</legend>
      <button type="button" class="catalog-remove" data-remove-field aria-label="Quitar campo ${index + 1}">Quitar campo</button>
      <label>Nombre del campo<input data-prop="label" maxlength="240" value="${esc(field.label)}"></label>
      <label>Columna del valor guardado<select data-prop="value_column">${columnOptions(field.value_column)}</select></label>
      <fieldset class="catalog-label-columns"><legend>Texto visible de las opciones</legend>
        <p class="catalog-hint">Combina columnas en el orden que quieras. Se separan con « — ».</p>
        ${field.label_columns.map((column, i) => `<div class="catalog-column-row"><select data-label-column="${i}" aria-label="Columna ${i + 1} del texto visible del campo ${index + 1}">${columnOptions(column)}</select><button type="button" data-remove-column="${i}" aria-label="Quitar columna ${i + 1} del texto visible" ${field.label_columns.length === 1 ? "disabled" : ""}>×</button></div>`).join("")}
        <button type="button" data-add-column class="catalog-column-add" ${field.label_columns.length >= result.headers.length ? "disabled" : ""}>+ Añadir columna al texto</button>
      </fieldset>
      <label>Componente<select data-prop="searchable">${options([[true, "Desplegable con búsqueda"], [false, "Desplegable"]], field.searchable)}</select></label>
      <label>Filtrar opciones según<select data-prop="parent">${options(parentOptions(index), field.parent)}</select></label>
      <label class="catalog-check"><input data-prop="required" type="checkbox" ${field.required ? "checked" : ""}> Campo obligatorio</label>
    </fieldset>`).join("");
    el("add-field").disabled = !result.headers.length || definitions.length >= 20;
    el("clear-fields").disabled = !definitions.length;
    el("empty").hidden = definitions.length > 0 || !result.headers.length;
    el("analyze").disabled = !definitions.length;
  }
  function refreshParentNames() {
    el("fields").querySelectorAll('[data-prop="parent"]').forEach((select, index) => setOptions(select, parentOptions(index), definitions[index].parent));
  }
  function previewItems() {
    if (!proposal) return;
    const values = {};
    for (const [index, field] of proposal.fields.entries()) {
      const select = el(`preview-${index}`), search = el(`search-${index}`);
      const relation = field.configuration.option_filter;
      const source = relation && proposal.fields.find((item) => item.stable_key === relation.source);
      const parentValue = relation ? values[relation.source] : "";
      const available = field.options.filter((option) => !relation || relation.values[option.value]?.includes(parentValue));
      const previous = select.value;
      const selected = available.some((option) => option.value === previous) ? previous : "";
      const enabled = !relation || Boolean(parentValue);
      setOptions(select, [["", enabled ? "Selecciona una opción" : `Selecciona primero ${source.label}`], ...available.map((option) => [option.value, option.label])], selected);
      values[field.stable_key] = selected;
      select.disabled = search.disabled = !enabled;
      const query = normalize(search.value.trim());
      let matches = 0;
      for (const option of select.options) {
        option.hidden = Boolean(option.value) && !normalize(option.textContent).includes(query);
        if (option.value && !option.hidden) matches++;
      }
      el(`count-${index}`).textContent = enabled ? `${matches} de ${available.length} opciones` : `Selecciona primero ${source.label}.`;
      el(`value-${index}`).textContent = selected ? `Valor que se guardará: ${selected}` : "";
    }
  }
  function renderPreview() {
    el("preview-controls").innerHTML = proposal.fields.map((field, index) => {
      const relation = field.configuration.option_filter;
      const parent = relation && proposal.fields.find((item) => item.stable_key === relation.source);
      return `<div class="catalog-preview-field">
        ${parent ? `<div class="catalog-relation">Opciones según «${esc(parent.label)}»</div>` : ""}
        <label for="catalog-preview-${index}">${esc(field.label)}${field.required ? " *" : ""}</label>
        <input id="catalog-search-${index}" type="search" placeholder="Buscar opciones…" aria-label="Buscar en ${esc(field.label)}" ${field.configuration.searchable ? "" : "hidden"}>
        <select id="catalog-preview-${index}" data-preview-index="${index}"></select>
        <p id="catalog-count-${index}" role="status"></p><p id="catalog-value-${index}"></p>
      </div>`;
    }).join("");
    previewItems();
  }
  function display(data) {
    result = data; proposal = data.proposal; definitions = data.field_definitions;
    el("configuration").hidden = false;
    setOptions(el("sheet"), data.sheets.map((name) => [name, name]), data.sheet);
    el("header").value = data.header_row;
    renderFields();
    el("sample").innerHTML = `<table><thead><tr>${data.headers.map((name) => `<th>${esc(name)}</th>`).join("")}</tr></thead><tbody>${data.sample.map((row) => `<tr>${row.map((value) => `<td>${esc(value)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    list("issues", [...data.issues, ...(data.issue_count > data.issues.length ? [`Y ${data.issue_count - data.issues.length} incidencias más.`] : [])]);
    list("warnings", data.warnings);
    el("summary").textContent = proposal ? `${proposal.fields.length} ${proposal.fields.length === 1 ? "campo" : "campos"} · ${proposal.option_count} opciones en total` : "Revisa las columnas y las filas indicadas";
    el("explanation").textContent = proposal?.explanation || "Corrige el archivo o ajusta las columnas para continuar.";
    el("preview-controls").hidden = !proposal;
    el("apply").disabled = !proposal;
    el("apply").textContent = proposal ? `Añadir ${proposal.fields.length} ${proposal.fields.length === 1 ? "campo" : "campos"}` : "Añadir campos";
    if (proposal) renderPreview();
    status(`${data.row_count} filas leídas. Solo se usarán las columnas elegidas.`);
  }
  function cancelAnalysis() {
    requestId++;
    if (activeRequest) {
      activeRequest.controller.abort();
      activeRequest.restore();
      activeRequest = null;
    }
    pending = false;
  }
  function resetFileState() {
    result = proposal = null;
    definitions = [];
    el("configuration").hidden = true;
    el("fields").replaceChildren();
    el("header").value = "1";
    invalidate();
    status("");
  }
  async function analyze(reset = false, header = false) {
    const file = selectedFile;
    if (!file || pending || (!reset && !definitions.length)) return;
    if (!/\.(csv|xlsx|xlsm)$/i.test(file.name) || file.size > 5 * 1024 * 1024) { invalidate(); status("Selecciona un .csv, .xlsx o .xlsm de hasta 5 MB.", true); return; }
    pending = true;
    const serial = ++requestId;
    const controls = [...dialog.querySelectorAll("input,select,button")].filter((control) => control !== el("file") && control !== el("choose-file") && !control.hasAttribute("data-catalog-close"));
    const disabled = controls.map((control) => control.disabled);
    const controller = new AbortController();
    const restore = () => controls.forEach((control, index) => { control.disabled = disabled[index]; });
    activeRequest = { controller, restore };
    controls.forEach((control) => { control.disabled = true; });
    status("Analizando las columnas y sus relaciones…");
    const data = new FormData();
    data.append("file", file);
    if (result) data.append("sheet", el("sheet").value);
    if (!reset || header) data.append("header_row", el("header").value);
    if (!reset) data.append("fields", JSON.stringify(definitions));
    try {
      const response = await fetch(root.dataset.catalogUrl, { method: "POST", headers: { "X-CSRFToken": root.querySelector("[name=csrfmiddlewaretoken]").value }, body: data, signal: controller.signal });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No se pudo analizar el archivo.");
      if (serial !== requestId) return;
      restore();
      display(payload);
    } catch (error) {
      if (serial !== requestId) return;
      restore();
      invalidate();
      status(error.message || "No se pudo analizar el archivo.", true);
      list("issues", [error.message || "No se pudo analizar el archivo."]);
    } finally {
      if (serial === requestId) {
        pending = false;
        activeRequest = null;
      }
    }
  }
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-catalog]");
    if (!button || button.disabled || root.dataset.archived === "true") return;
    root.dispatchEvent(new CustomEvent("builder:close-menus"));
    dialog.showModal();
  });
  dialog.querySelectorAll("[data-catalog-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => { if (pending) { cancelAnalysis(); resetFileState(); } });
  el("choose-file").addEventListener("click", () => el("file").click());
  el("file").addEventListener("change", () => {
    const file = el("file").files[0];
    if (!file) return;
    cancelAnalysis();
    selectedFile = file;
    // Retain the File separately so selecting it again still emits change.
    el("file").value = "";
    el("filename").textContent = file.name;
    el("choose-file").textContent = "Cambiar archivo";
    resetFileState();
    analyze(true);
  });
  el("sheet").addEventListener("change", () => analyze(true));
  el("header").addEventListener("change", () => analyze(true, true));
  el("fields").addEventListener("input", (event) => {
    const control = event.target, card = control.closest("[data-field-index]");
    if (!card || pending) return;
    const field = definitions[Number(card.dataset.fieldIndex)];
    const property = control.dataset.prop;
    if (property) {
      field[property] = property === "required" ? control.checked : property === "searchable" ? control.value === "true" : property === "value_column" ? Number(control.value) : control.value;
      if (property === "label") refreshParentNames();
    } else if (control.hasAttribute("data-label-column")) field.label_columns[Number(control.dataset.labelColumn)] = Number(control.value);
    invalidate();
  });
  el("fields").addEventListener("click", (event) => {
    const button = event.target.closest("button"), card = button?.closest("[data-field-index]");
    if (!card || button.disabled || pending) return;
    const index = Number(card.dataset.fieldIndex), field = definitions[index];
    let message = "", focusSelector;
    if (button.hasAttribute("data-remove-field")) {
      const affected = definitions.filter((item) => item.parent === field.id);
      affected.forEach((item) => { item.parent = ""; });
      if (affected.length) message = `Se quitó «${field.label}». ${affected.map((item) => `«${item.label}»`).join(", ")} ${affected.length === 1 ? "queda" : "quedan"} sin dependencia; revisa sus filtros antes de actualizar.`;
      definitions.splice(index, 1);
      focusSelector = `[data-field-index="${Math.min(index, definitions.length - 1)}"] [data-prop="label"]`;
    } else if (button.hasAttribute("data-add-column")) {
      field.label_columns.push(result.headers.findIndex((_, i) => !field.label_columns.includes(i)));
      focusSelector = `[data-field-index="${index}"] [data-label-column="${field.label_columns.length - 1}"]`;
    } else if (button.hasAttribute("data-remove-column")) {
      field.label_columns.splice(Number(button.dataset.removeColumn), 1);
      focusSelector = `[data-field-index="${index}"] [data-add-column]`;
    } else return;
    invalidate(); renderFields();
    if (definitions.length) el("fields").querySelector(focusSelector)?.focus();
    else el("add-field").focus();
    if (message) status(message);
  });
  el("clear-fields").addEventListener("click", () => {
    if (pending || !definitions.length) return;
    definitions = [];
    invalidate(); renderFields();
    el("add-field").focus();
  });
  el("add-field").addEventListener("click", () => {
    if (pending || !result?.headers.length || definitions.length >= 20) return;
    const unused = result.headers.findIndex((_, i) => !definitions.some((field) => field.value_column === i));
    const column = unused === -1 ? 0 : unused;
    definitions.push({ id: `field_${crypto.randomUUID()}`, label: result.headers[column], value_column: column, label_columns: [column], parent: "", searchable: true, required: false });
    invalidate(); renderFields();
    el("fields").querySelector(`[data-field-index="${definitions.length - 1}"] [data-prop="label"]`).focus();
  });
  el("analyze").addEventListener("click", () => analyze());
  el("preview-controls").addEventListener("input", (event) => { if (event.target.type === "search") previewItems(); });
  el("preview-controls").addEventListener("change", (event) => {
    if (!event.target.matches("select")) return;
    const changed = new Set([proposal.fields[Number(event.target.dataset.previewIndex)].stable_key]);
    proposal.fields.forEach((field, index) => {
      if (changed.has(field.configuration.option_filter?.source)) { changed.add(field.stable_key); el(`search-${index}`).value = ""; }
    });
    previewItems();
  });
  el("apply").addEventListener("click", () => {
    if (!proposal || pending) return;
    const request = { fields: structuredClone(proposal.fields), error: "" };
    root.dispatchEvent(new CustomEvent("builder:import-catalog", { detail: request }));
    if (request.error) { status(request.error, true); return; }
    dialog.close();
    selectedFile = null;
    el("file").value = "";
    el("filename").textContent = "Ningún archivo seleccionado";
    el("choose-file").textContent = "Seleccionar archivo";
    resetFileState();
  });
})();
