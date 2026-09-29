(() => {
  const host = document.getElementById('response-panel-host');
  let controller;

  const items = document.querySelector('.response-work-items');
  const visibleItems = items ? [...items.querySelectorAll('.response-work-item')].slice(0, 5) : [];
  if (items && items.querySelectorAll('.response-work-item').length > 5) {
    items.setAttribute('tabindex', '0');
    items.setAttribute('role', 'region');
    items.setAttribute('aria-label', 'Lista de respuestas');
    const resizeList = () => {
      // Measure complete rows so wrapped titles and responsive widths still show five.
      const first = visibleItems[0].getBoundingClientRect();
      const fifth = visibleItems[4].getBoundingClientRect();
      items.style.maxHeight = `${Math.ceil(fifth.bottom - first.top)}px`;
    };
    const observer = new ResizeObserver(resizeList);
    visibleItems.forEach((item) => observer.observe(item));
    observer.observe(items);
    resizeList();
  }

  document.addEventListener('click', async (event) => {
    const tab = event.target.closest('[data-case-tab]');
    if (tab) {
      const current = tab.closest('.response-case');
      current.querySelectorAll('[data-case-tab]').forEach((button) => {
        button.setAttribute('aria-selected', button === tab ? 'true' : 'false');
      });
      current.querySelectorAll('[data-case-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.casePanel !== tab.dataset.caseTab;
      });
      return;
    }
    const link = event.target.closest('[data-panel-url]');
    if (!host || !link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    controller?.abort();
    const pending = new AbortController();
    controller = pending;
    host.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(link.dataset.panelUrl, { signal: pending.signal, headers: { Accept: 'text/html' } });
      if (!response.ok || response.redirected || !response.headers.get('content-type')?.includes('text/html')) throw new Error('No se pudo cargar la respuesta.');
      const html = await response.text();
      if (pending.signal.aborted) return;
      host.innerHTML = html;
      document.querySelectorAll('.response-work-item').forEach((item) => {
        item.classList.toggle('is-selected', item.contains(link));
      });
      const url = new URL(location.href);
      url.searchParams.set('selected', link.closest('[data-response-id]').dataset.responseId);
      history.replaceState(null, '', url);
      if (matchMedia('(max-width: 900px)').matches) host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      if (!pending.signal.aborted && error.name !== 'AbortError') location.href = link.href;
    } finally {
      if (controller === pending) host.removeAttribute('aria-busy');
    }
  });
  document.addEventListener('submit', (event) => {
    if (!event.target.matches('.response-note-form')) return;
    const next = new URL(location.href);
    next.hash = 'response-notes';
    event.target.elements.next.value = next.toString();
  });
  if (location.hash === '#response-notes') {
    document.querySelector('[data-case-tab="notes"]')?.click();
  }
})();
