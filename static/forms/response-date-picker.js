(() => {
  const form = document.querySelector('.response-work-filters');
  if (!form || !HTMLElement.prototype.showPopover) return;

  const from = form.elements.response_from;
  const to = form.elements.response_to;
  if (!from || !to) return;

  const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
  const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
  const makeDate = (year, month, day) => {
    const result = new Date(0);
    result.setHours(12, 0, 0, 0);
    result.setFullYear(year, month, day);
    return result;
  };
  const iso = (value) => `${String(value.getFullYear()).padStart(4, '0')}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
  const parse = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!match) return null;
    const result = makeDate(+match[1], +match[2] - 1, +match[3]);
    return iso(result) === value ? result : null;
  };
  const today = () => {
    const now = new Date();
    return makeDate(now.getFullYear(), now.getMonth(), now.getDate());
  };
  const display = (value) => value ? `${value.slice(8, 10)}/${value.slice(5, 7)}/${value.slice(0, 4)}` : 'dd/mm/aaaa';
  const fullDate = new Intl.DateTimeFormat('es-CO', { dateStyle: 'full' });

  const calendar = document.createElement('div');
  calendar.className = 'response-date-calendar';
  calendar.id = 'response-date-calendar';
  calendar.setAttribute('popover', 'auto');
  calendar.setAttribute('role', 'dialog');
  calendar.setAttribute('aria-labelledby', 'response-date-calendar-title');
  calendar.innerHTML = `
    <header><div><small>FILTROS DE RESPUESTAS</small><h2 id="response-date-calendar-title">Seleccionar fecha</h2></div><button type="button" class="response-calendar-close" aria-label="Cerrar calendario"><span class="material-symbols-outlined" aria-hidden="true">close</span></button></header>
    <div class="response-calendar-navigation"><button type="button" data-month-step="-1" aria-label="Mes anterior"><span class="material-symbols-outlined" aria-hidden="true">chevron_left</span></button><select aria-label="Mes">${months.map((month, index) => `<option value="${index}">${month}</option>`).join('')}</select><input type="number" min="1" max="9999" step="1" inputmode="numeric" aria-label="Año"><button type="button" data-month-step="1" aria-label="Mes siguiente"><span class="material-symbols-outlined" aria-hidden="true">chevron_right</span></button></div>
    <p class="sr-only" id="response-calendar-month-label" aria-live="polite"></p>
    <table role="grid" aria-labelledby="response-calendar-month-label"><thead><tr>${weekdays.map((day) => `<th scope="col" abbr="${day}">${day.slice(0, 2)}</th>`).join('')}</tr></thead><tbody></tbody></table>
    <footer><button type="button" data-calendar-clear>Limpiar fecha</button><button type="button" data-calendar-today>Hoy</button></footer>`;
  document.body.append(calendar);

  const monthInput = calendar.querySelector('select');
  const yearInput = calendar.querySelector('input');
  const grid = calendar.querySelector('tbody');
  const title = calendar.querySelector('h2');
  const triggers = new Map();
  let active = null;
  let cursor = today();
  const isOpen = () => calendar.matches(':popover-open');
  const allowed = (value) => {
    if (value.getFullYear() < 1 || value.getFullYear() > 9999) return false;
    const key = iso(value);
    return !(active === from && parse(to.value) && key > to.value)
      && !(active === to && parse(from.value) && key < from.value);
  };
  const clamp = (value) => {
    if (value.getFullYear() < 1) return makeDate(1, 0, 1);
    if (value.getFullYear() > 9999) return makeDate(9999, 11, 31);
    const limit = parse(active === from ? to.value : from.value);
    if (!limit) return value;
    if (active === from && value > limit) return limit;
    if (active === to && value < limit) return limit;
    return value;
  };

  function position() {
    if (!active || !isOpen()) return;
    const rect = triggers.get(active).getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0;
    const top = viewport?.offsetTop || 0;
    const width = viewport?.width || window.innerWidth;
    const height = viewport?.height || window.innerHeight;
    calendar.style.maxWidth = `${Math.max(160, width - 24)}px`;
    calendar.style.maxHeight = `${Math.max(180, height - 24)}px`;
    const box = calendar.getBoundingClientRect();
    calendar.style.left = `${Math.max(left + 12, Math.min(rect.left, left + width - box.width - 12))}px`;
    const below = rect.bottom + 8;
    const desiredTop = below + box.height <= top + height - 12 ? below : rect.top - box.height - 8;
    calendar.style.top = `${Math.max(top + 12, Math.min(desiredTop, top + height - box.height - 12))}px`;
  }

  function render(focusDay = false) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    monthInput.value = String(month);
    yearInput.value = String(year);
    yearInput.min = active === to && parse(from.value) ? String(parse(from.value).getFullYear()) : '1';
    yearInput.max = active === from && parse(to.value) ? String(parse(to.value).getFullYear()) : '9999';
    const monthAvailable = (candidateYear, candidateMonth) => {
      const firstDay = makeDate(candidateYear, candidateMonth, 1);
      const lastDay = makeDate(candidateYear, candidateMonth + 1, 0);
      return allowed(firstDay) || allowed(lastDay);
    };
    for (const option of monthInput.options) {
      option.disabled = !monthAvailable(year, Number(option.value));
    }
    calendar.querySelector('[data-month-step="-1"]').disabled = !monthAvailable(year, month - 1);
    calendar.querySelector('[data-month-step="1"]').disabled = !monthAvailable(year, month + 1);
    title.textContent = active === from ? 'Fecha desde' : 'Fecha hasta';
    calendar.querySelector('#response-calendar-month-label').textContent = `${months[month]} de ${year}`;
    const first = makeDate(year, month, 1);
    const offset = (first.getDay() + 6) % 7;
    const start = parse(from.value) ? from.value : '';
    const end = parse(to.value) ? to.value : '';
    const current = iso(today());
    grid.replaceChildren();
    for (let week = 0; week < 6; week++) {
      const row = document.createElement('tr');
      for (let day = 0; day < 7; day++) {
        const value = makeDate(year, month, 1 - offset + week * 7 + day);
        const key = iso(value);
        const cell = document.createElement('td');
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.date = key;
        button.textContent = String(value.getDate());
        button.setAttribute('aria-label', fullDate.format(value));
        button.setAttribute('aria-selected', String(key === active.value));
        button.tabIndex = key === iso(cursor) ? 0 : -1;
        button.disabled = !allowed(value);
        if (value.getMonth() !== month) button.classList.add('outside-month');
        if (key === active.value) button.classList.add('selected-day');
        if (start && end && key > start && key < end) button.classList.add('in-range');
        if (key === current) button.setAttribute('aria-current', 'date');
        cell.append(button);
        row.append(cell);
      }
      grid.append(row);
    }
    calendar.querySelector('[data-calendar-today]').disabled = !allowed(today());
    calendar.querySelector('[data-calendar-clear]').disabled = !active.value;
    position();
    if (focusDay) grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
  }

  function close(restoreFocus = false) {
    if (isOpen()) calendar.hidePopover();
    if (restoreFocus) triggers.get(active)?.focus({ preventScroll: true });
  }

  function open(input) {
    if (active === input && isOpen()) { close(true); return; }
    active = input;
    cursor = parse(input.value) || parse(input === from ? to.value : from.value) || today();
    if (!allowed(cursor)) cursor = parse(input === from ? to.value : from.value) || today();
    render();
    if (!isOpen()) calendar.showPopover();
    for (const [field, trigger] of triggers) trigger.setAttribute('aria-expanded', String(field === active));
    position();
    grid.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
  }

  function choose(value) {
    active.value = value;
    active.dispatchEvent(new Event('change', { bubbles: true }));
    syncTriggers();
    close(true);
  }

  function syncTriggers() {
    for (const [input, trigger] of triggers) {
      const label = input === from ? 'Desde' : 'Hasta';
      trigger.querySelector('.response-date-value').textContent = display(input.value);
      trigger.classList.toggle('has-date', Boolean(input.value));
      trigger.setAttribute('aria-label', `${label}: ${input.value ? display(input.value) : 'sin fecha'}. Abrir calendario`);
    }
  }

  for (const input of [from, to]) {
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'response-date-trigger';
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-controls', calendar.id);
    trigger.setAttribute('aria-expanded', 'false');
    trigger.innerHTML = '<span class="response-date-value"></span><span class="material-symbols-outlined" aria-hidden="true">calendar_month</span>';
    input.type = 'hidden';
    input.after(trigger);
    triggers.set(input, trigger);
    trigger.addEventListener('click', () => open(input));
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); open(input); }
    });
  }
  syncTriggers();

  calendar.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.date) choose(button.dataset.date);
    else if (button.dataset.monthStep) {
      cursor = clamp(makeDate(cursor.getFullYear(), cursor.getMonth() + Number(button.dataset.monthStep), 1));
      render();
    } else if (button.hasAttribute('data-calendar-today')) choose(iso(today()));
    else if (button.hasAttribute('data-calendar-clear')) choose('');
    else if (button.classList.contains('response-calendar-close')) close(true);
  });
  monthInput.addEventListener('change', () => {
    cursor = clamp(makeDate(cursor.getFullYear(), Number(monthInput.value), 1));
    render();
  });
  yearInput.addEventListener('change', () => {
    if (!yearInput.checkValidity() || !yearInput.value) { yearInput.value = cursor.getFullYear(); return; }
    cursor = clamp(makeDate(Number(yearInput.value), cursor.getMonth(), 1));
    render();
  });
  calendar.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(true); return; }
    const day = event.target.closest('[data-date]');
    if (!day) return;
    const date = parse(day.dataset.date);
    const weekday = (date.getDay() + 6) % 7;
    const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -weekday, End: 6 - weekday };
    if (Object.hasOwn(steps, event.key)) {
      event.preventDefault();
      const next = makeDate(date.getFullYear(), date.getMonth(), date.getDate() + steps[event.key]);
      if (allowed(next)) { cursor = next; render(true); }
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      cursor = clamp(makeDate(date.getFullYear(), date.getMonth() + (event.key === 'PageUp' ? -1 : 1) * (event.shiftKey ? 12 : 1), 1));
      render(true);
    }
  });
  calendar.addEventListener('toggle', () => {
    if (!isOpen()) for (const trigger of triggers.values()) trigger.setAttribute('aria-expanded', 'false');
  });
  window.addEventListener('resize', position);
  document.addEventListener('scroll', position, true);
  window.visualViewport?.addEventListener('resize', position);
})();
