(() => {
  const form = document.querySelector('.response-work-filters');
  if (!form || !HTMLElement.prototype.showPopover) return;

  const fields = [...form.querySelectorAll('.response-select-field')];
  if (!fields.length) return;

  const menu = document.createElement('div');
  menu.id = 'response-select-menu';
  menu.className = 'response-select-menu';
  menu.setAttribute('popover', 'auto');
  menu.innerHTML = '<div class="response-select-menu-heading"></div><div class="response-select-options" role="listbox"></div>';
  document.body.append(menu);

  const heading = menu.querySelector('.response-select-menu-heading');
  const options = menu.querySelector('.response-select-options');
  options.id = 'response-select-options';
  const triggers = new Map();
  let active = null;
  let highlighted = 0;
  let search = '';
  let searchTimer;
  const isOpen = () => menu.matches(':popover-open');
  const label = (select) => select.closest('.response-select-field').querySelector('span').textContent.trim();
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');

  function position() {
    if (!active || !isOpen()) return;
    const rect = triggers.get(active).getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0;
    const top = viewport?.offsetTop || 0;
    const width = viewport?.width || window.innerWidth;
    const height = viewport?.height || window.innerHeight;
    const menuWidth = Math.min(Math.max(rect.width, active.name === 'response_form' ? 310 : 220), width - 24);
    menu.style.width = `${menuWidth}px`;
    menu.style.maxHeight = `${Math.max(160, height - 24)}px`;
    const box = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left + 12, Math.min(rect.left, left + width - box.width - 12))}px`;
    const below = rect.bottom + 7;
    const desiredTop = below + box.height <= top + height - 12 ? below : rect.top - box.height - 7;
    menu.style.top = `${Math.max(top + 12, Math.min(desiredTop, top + height - box.height - 12))}px`;
  }

  function highlight(index, scroll = true) {
    const items = [...options.children];
    if (!items.length) return;
    highlighted = (index + items.length) % items.length;
    for (const [itemIndex, item] of items.entries()) item.classList.toggle('is-highlighted', itemIndex === highlighted);
    triggers.get(active).setAttribute('aria-activedescendant', items[highlighted].id);
    if (scroll) items[highlighted].scrollIntoView({ block: 'nearest' });
  }

  function render() {
    const trigger = triggers.get(active);
    for (const other of triggers.values()) {
      other.setAttribute('aria-expanded', 'false');
      other.removeAttribute('aria-activedescendant');
    }
    heading.textContent = label(active);
    options.setAttribute('aria-label', label(active));
    options.replaceChildren();
    for (const [index, choice] of [...active.options].entries()) {
      const item = document.createElement('div');
      item.id = `response-select-option-${index}`;
      item.className = 'response-select-option';
      item.role = 'option';
      item.dataset.index = String(index);
      item.setAttribute('aria-selected', String(index === active.selectedIndex));
      const text = document.createElement('span');
      text.textContent = choice.textContent.trim();
      const icon = document.createElement('span');
      icon.className = 'material-symbols-outlined';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = 'check';
      item.append(text, icon);
      options.append(item);
    }
    highlight(Math.max(0, active.selectedIndex), false);
    trigger.setAttribute('aria-expanded', 'true');
  }

  function close(restoreFocus = false) {
    if (isOpen()) menu.hidePopover();
    if (restoreFocus) triggers.get(active)?.focus({ preventScroll: true });
  }

  function open(select) {
    if (active === select && isOpen()) { close(true); return; }
    active = select;
    search = '';
    render();
    if (!isOpen()) menu.showPopover();
    position();
    options.children[highlighted]?.scrollIntoView({ block: 'nearest' });
  }

  function sync(select) {
    const trigger = triggers.get(select);
    const value = select.selectedOptions[0]?.textContent.trim() || '';
    trigger.querySelector('.response-select-value').textContent = value;
    trigger.setAttribute('aria-label', `${label(select)}: ${value}`);
  }

  function choose(index) {
    active.selectedIndex = index;
    active.dispatchEvent(new Event('change', { bubbles: true }));
    sync(active);
    close(true);
  }

  for (const field of fields) {
    const select = field.querySelector('select');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'response-select-trigger';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-controls', options.id);
    trigger.setAttribute('aria-expanded', 'false');
    trigger.innerHTML = '<span class="response-select-value"></span><span class="material-symbols-outlined" aria-hidden="true">keyboard_arrow_down</span>';
    select.hidden = true;
    select.after(trigger);
    triggers.set(select, trigger);
    sync(select);
    select.addEventListener('change', () => sync(select));
    let pointerWasOpen = false;
    trigger.addEventListener('pointerdown', () => { pointerWasOpen = active === select && isOpen(); });
    trigger.addEventListener('click', () => {
      if (pointerWasOpen) close(true);
      else open(select);
      pointerWasOpen = false;
    });
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'Tab') { if (isOpen() && active === select) close(); return; }
      if (event.key === 'Escape' && isOpen() && active === select) { event.preventDefault(); close(true); return; }
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (isOpen() && active === select) choose(highlighted);
        else open(select);
        return;
      }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        if (!isOpen() || active !== select) { open(select); return; }
        const last = options.children.length - 1;
        highlight(event.key === 'Home' ? 0 : event.key === 'End' ? last : highlighted + (event.key === 'ArrowDown' ? 1 : -1));
        return;
      }
      if (event.key.length !== 1 || event.altKey || event.ctrlKey || event.metaKey) return;
      if (!isOpen() || active !== select) open(select);
      search += normalize(event.key);
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { search = ''; }, 650);
      const match = [...select.options].findIndex((choice) => normalize(choice.textContent.trim()).startsWith(search));
      if (match >= 0) highlight(match);
    });
  }

  menu.addEventListener('click', (event) => {
    const option = event.target.closest('[data-index]');
    if (option && active) choose(Number(option.dataset.index));
  });
  menu.addEventListener('pointermove', (event) => {
    const option = event.target.closest('[data-index]');
    if (option && active && Number(option.dataset.index) !== highlighted) highlight(Number(option.dataset.index), false);
  });
  menu.addEventListener('toggle', () => {
    if (!isOpen()) {
      for (const trigger of triggers.values()) {
        trigger.setAttribute('aria-expanded', 'false');
        trigger.removeAttribute('aria-activedescendant');
      }
    }
  });
  window.addEventListener('resize', position);
  document.addEventListener('scroll', position, true);
  window.visualViewport?.addEventListener('resize', position);
})();
