(() => {
  const page = document.querySelector('.users-page');
  if (!page) return;
  const all = page.querySelector('#users-select-all');
  const rows = [...page.querySelectorAll('#users-list-form input[type="checkbox"][name="_selected_action"]')];
  const status = page.querySelector('#users-selection-status');
  const sync = () => {
    const count = rows.filter((input) => input.checked).length;
    if (all) {
      all.checked = rows.length > 0 && count === rows.length;
      all.indeterminate = count > 0 && count < rows.length;
      all.disabled = !rows.length;
    }
    if (status) status.textContent = count ? `${count} usuario${count === 1 ? '' : 's'} seleccionado${count === 1 ? '' : 's'} en esta página` : 'Selecciona usuarios para aplicar una acción.';
    for (const input of rows) input.closest('tr').classList.toggle('is-selected', input.checked);
  };
  all?.addEventListener('change', () => { rows.forEach((input) => { input.checked = all.checked; }); sync(); });
  rows.forEach((input) => input.addEventListener('change', sync));
  sync();
  window.addEventListener('pageshow', sync);
  const errors = page.querySelector('.users-errors');
  if (errors) errors.focus();
})();
