(() => {
  // Keep the native date input and ISO value for validation, conditions and submission.
  if (!HTMLElement.prototype.showPopover) return;
  const form = document.getElementById("public-form");
  const inputs = [...(form?.querySelectorAll('input[type="date"]') || [])];
  if (!inputs.length) return;
  const months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
  const weekdays = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
  const date = (year, month, day) => {
    const result = new Date(0);
    result.setHours(12, 0, 0, 0);
    result.setFullYear(year, month, day);
    return result;
  };
  const iso = (value) => `${String(value.getFullYear()).padStart(4, "0")}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  const parse = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return null;
    const result = date(+match[1], +match[2] - 1, +match[3]);
    return iso(result) === value ? result : null;
  };
  const today = () => { const now = new Date(); return date(now.getFullYear(), now.getMonth(), now.getDate()); };
  const fullDate = new Intl.DateTimeFormat("es-CO", { dateStyle: "full" });
  const calendar = document.createElement("div");
  calendar.className = "form-calendar";
  calendar.id = "form-date-calendar";
  calendar.setAttribute("popover", "auto");
  calendar.setAttribute("role", "dialog");
  calendar.setAttribute("aria-label", "Seleccionar fecha");
  calendar.innerHTML = `
    <div class="calendar-heading"><span>Seleccionar fecha</span><button type="button" class="calendar-close" aria-label="Cerrar calendario">×</button></div>
    <div class="calendar-navigation">
      <button type="button" data-month-step="-1" aria-label="Mes anterior">‹</button>
      <select class="calendar-month" aria-label="Mes">${months.map((month, index) => `<option value="${index}">${month}</option>`).join("")}</select>
      <input class="calendar-year" type="number" inputmode="numeric" min="1" max="9999" step="1" aria-label="Año">
      <button type="button" data-month-step="1" aria-label="Mes siguiente">›</button>
    </div>
    <p class="visually-hidden" id="calendar-month-label" aria-live="polite"></p>
    <table class="calendar-grid" role="grid" aria-labelledby="calendar-month-label"><thead><tr>${weekdays.map((day) => `<th scope="col" abbr="${day}">${day.slice(0, 1)}</th>`).join("")}</tr></thead><tbody></tbody></table>
    <div class="calendar-footer"><button type="button" data-calendar-today>Hoy</button><button type="button" data-calendar-clear>Borrar fecha</button></div>
    <p class="calendar-hint">Puede escribir el año para localizar una fecha.</p>`;
  document.body.append(calendar);
  const monthInput = calendar.querySelector(".calendar-month");
  const yearInput = calendar.querySelector(".calendar-year");
  const grid = calendar.querySelector("tbody");
  const triggers = new Map();
  let active = null;
  let cursor = today();
  const minimum = () => parse(active?.min || "") || date(1, 0, 1);
  const maximum = () => parse(active?.max || "") || date(9999, 11, 31);
  const allowed = (value) => value >= minimum() && value <= maximum();
  const clamp = (value) => value < minimum() ? minimum() : value > maximum() ? maximum() : value;
  const isOpen = () => calendar.matches(":popover-open");

  function position() {
    if (!active || !isOpen()) return;
    const rect = active.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || window.innerHeight;
    calendar.style.maxWidth = `${width - 24}px`;
    calendar.style.maxHeight = `${height - 24}px`;
    const size = calendar.getBoundingClientRect();
    calendar.style.left = `${Math.max(left + 12, Math.min(rect.left, left + width - size.width - 12))}px`;
    const below = rect.bottom + 8;
    const target = below + size.height <= top + height - 12 ? below : rect.top - size.height - 8;
    calendar.style.top = `${Math.max(top + 12, Math.min(target, top + height - size.height - 12))}px`;
  }
  function render(focusDay = false) {
    const year = cursor.getFullYear(), month = cursor.getMonth();
    monthInput.value = String(month);
    yearInput.value = String(year);
    yearInput.min = minimum().getFullYear();
    yearInput.max = maximum().getFullYear();
    calendar.querySelector("#calendar-month-label").textContent = `${months[month]} de ${year}`;
    for (const option of monthInput.options) {
      option.disabled = date(year, +option.value + 1, 0) < minimum() || date(year, +option.value, 1) > maximum();
    }
    calendar.querySelector('[data-month-step="-1"]').disabled = date(year, month, 1) <= minimum();
    calendar.querySelector('[data-month-step="1"]').disabled = date(year, month + 1, 1) > maximum();
    calendar.querySelector("[data-calendar-today]").disabled = !allowed(today());
    calendar.querySelector("[data-calendar-clear]").disabled = !active.value;
    const first = date(year, month, 1);
    const start = 1 - (first.getDay() + 6) % 7;
    const selected = active.value, currentDay = iso(today());
    grid.replaceChildren();
    for (let week = 0; week < 6; week++) {
      const row = document.createElement("tr");
      for (let day = 0; day < 7; day++) {
        const value = date(year, month, start + week * 7 + day);
        const cell = document.createElement("td");
        const button = document.createElement("button");
        const key = iso(value);
        cell.setAttribute("role", "gridcell");
        cell.setAttribute("aria-selected", String(key === selected));
        button.type = "button";
        button.textContent = value.getDate();
        button.dataset.date = key;
        button.setAttribute("aria-label", fullDate.format(value));
        button.tabIndex = key === iso(cursor) ? 0 : -1;
        button.disabled = !allowed(value);
        if (value.getMonth() !== month) button.classList.add("outside-month");
        if (key === selected) button.classList.add("selected-day");
        if (key === currentDay) button.setAttribute("aria-current", "date");
        cell.append(button);
        row.append(cell);
      }
      grid.append(row);
    }
    position();
    if (focusDay) grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
  }
  function close(restoreFocus = false) {
    if (!isOpen()) return;
    calendar.hidePopover();
    if (restoreFocus && active && !active.disabled && !active.closest("[hidden]")) active.focus({ preventScroll: true });
  }
  function open(input) {
    if (input.disabled || input.readOnly) return;
    if (active && active !== input) triggers.get(active)?.setAttribute("aria-expanded", "false");
    active = input;
    cursor = clamp(parse(input.value) || today());
    render();
    if (!isOpen()) calendar.showPopover();
    triggers.get(input).setAttribute("aria-expanded", "true");
    position();
    grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
  }
  function choose(value) {
    active.value = value;
    active.dispatchEvent(new Event("input", { bubbles: true }));
    active.dispatchEvent(new Event("change", { bubbles: true }));
    close(true);
  }
  function moveMonth(offset, focusDay = false) {
    const first = date(cursor.getFullYear(), cursor.getMonth() + offset, 1);
    cursor = clamp(date(first.getFullYear(), first.getMonth(), Math.min(cursor.getDate(), date(first.getFullYear(), first.getMonth() + 1, 0).getDate())));
    render(focusDay);
  }
  for (const input of inputs) {
    const wrapper = document.createElement("div");
    wrapper.className = "form-date-control";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "form-date-trigger";
    const label = input.labels?.[0]?.textContent.replace(/\s+/g, " ").trim() || "Fecha";
    trigger.setAttribute("aria-label", `Abrir calendario: ${label}`);
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", calendar.id);
    trigger.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2m-8 3h2"/></svg>';
    input.before(wrapper);
    wrapper.append(input, trigger);
    triggers.set(input, trigger);
    let openOnPointerDown = false;
    trigger.addEventListener("pointerdown", () => { openOnPointerDown = active === input && isOpen(); });
    trigger.addEventListener("click", () => {
      if (openOnPointerDown || (active === input && isOpen())) {
        close(true);
        input.focus({ preventScroll: true });
      } else open(input);
      openOnPointerDown = false;
    });
    input.addEventListener("keydown", (event) => {
      if ((event.altKey && event.key === "ArrowDown") || event.key === "F4") {
        event.preventDefault();
        open(input);
      }
    });
  }
  calendar.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    if (button.dataset.date) choose(button.dataset.date);
    else if (button.dataset.monthStep) moveMonth(+button.dataset.monthStep);
    else if (button.hasAttribute("data-calendar-today")) choose(iso(today()));
    else if (button.hasAttribute("data-calendar-clear")) choose("");
    else if (button.classList.contains("calendar-close")) close(true);
  });
  monthInput.addEventListener("change", () => moveMonth(+monthInput.value - cursor.getMonth()));
  yearInput.addEventListener("change", () => {
    if (!yearInput.value || !yearInput.checkValidity()) { yearInput.value = cursor.getFullYear(); return; }
    const year = +yearInput.value, month = cursor.getMonth();
    cursor = clamp(date(year, month, Math.min(cursor.getDate(), date(year, month + 1, 0).getDate())));
    render();
  });
  calendar.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(true); return; }
    if (event.key === "Tab") {
      const stops = [...calendar.querySelectorAll('button:not(:disabled), select, input')].filter((el) => el.tabIndex >= 0);
      if ((event.shiftKey && event.target === stops[0]) || (!event.shiftKey && event.target === stops.at(-1))) {
        event.preventDefault();
        close(true);
      }
      return;
    }
    const day = event.target.closest("[data-date]");
    if (!day) return;
    cursor = parse(day.dataset.date);
    const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -(cursor.getDay() + 6) % 7, End: 6 - (cursor.getDay() + 6) % 7 };
    if (Object.hasOwn(steps, event.key)) {
      event.preventDefault();
      cursor = clamp(date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + steps[event.key]));
      render(true);
    } else if (["PageUp", "PageDown"].includes(event.key)) {
      event.preventDefault();
      moveMonth((event.key === "PageUp" ? -1 : 1) * (event.shiftKey ? 12 : 1), true);
    }
  });
  calendar.addEventListener("toggle", () => {
    if (!isOpen() && active) triggers.get(active)?.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("focusin", (event) => {
    if (isOpen() && !calendar.contains(event.target) && !active?.parentElement.contains(event.target)) close();
  });
  const sync = () => {
    for (const [input, trigger] of triggers) {
      const disabled = input.disabled || input.readOnly;
      if (trigger.disabled !== disabled) trigger.disabled = disabled;
    }
    if (active && (active.disabled || active.closest("[hidden]"))) close();
  };
  new MutationObserver(sync).observe(form, { attributes: true, subtree: true, attributeFilter: ["disabled", "readonly", "hidden"] });
  sync();
  window.addEventListener("resize", position);
  document.addEventListener("scroll", position, true);
  window.visualViewport?.addEventListener("resize", position);
  window.visualViewport?.addEventListener("scroll", position);
})();
