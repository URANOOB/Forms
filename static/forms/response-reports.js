(() => {
  const table = document.querySelector('.reports-responses-grid');
  const menu = document.querySelector('.reports-columns-menu');
  if (!table || !menu) return;

  const storageKey = 'logicforms.report.columns';
  const toggles = [...menu.querySelectorAll('[data-column-toggle]')];
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(storageKey) || '{}') || {};
  } catch (_) {
    saved = {};
  }

  const apply = () => {
    toggles.forEach((toggle) => {
      const key = toggle.dataset.columnToggle;
      table.querySelectorAll('[data-report-column]').forEach((cell) => {
        if (cell.dataset.reportColumn === key) cell.hidden = !toggle.checked;
      });
    });
  };

  toggles.forEach((toggle) => {
    if (Object.prototype.hasOwnProperty.call(saved, toggle.dataset.columnToggle)) {
      toggle.checked = saved[toggle.dataset.columnToggle];
    }
    toggle.addEventListener('change', () => {
      saved[toggle.dataset.columnToggle] = toggle.checked;
      try { localStorage.setItem(storageKey, JSON.stringify(saved)); } catch (_) {}
      apply();
    });
  });

  menu.querySelector('[data-columns-reset]')?.addEventListener('click', () => {
    saved = {};
    toggles.forEach((toggle) => { toggle.checked = true; });
    try { localStorage.removeItem(storageKey); } catch (_) {}
    apply();
  });
  apply();
})();
