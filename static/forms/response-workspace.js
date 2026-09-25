(() => {
  const host = document.getElementById('response-panel-host');
  let controller;

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
    controller = new AbortController();
    host.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(link.dataset.panelUrl, { signal: controller.signal, headers: { Accept: 'text/html' } });
      if (!response.ok) throw new Error('No se pudo cargar la respuesta.');
      host.innerHTML = await response.text();
      document.querySelectorAll('.response-work-item').forEach((item) => {
        item.classList.toggle('is-selected', item.contains(link));
      });
      const url = new URL(location.href);
      url.searchParams.set('selected', link.closest('[data-response-id]').dataset.responseId);
      history.replaceState(null, '', url);
      if (matchMedia('(max-width: 900px)').matches) host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      if (error.name !== 'AbortError') location.href = link.href;
    } finally {
      host.removeAttribute('aria-busy');
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
