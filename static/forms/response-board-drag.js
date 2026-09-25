(() => {
  const board = document.querySelector('.response-board');
  if (!board) return;

  const columns = [...board.querySelectorAll('.response-column')];
  let dragging = null;
  const canDrop = (column) => dragging?.dataset.allowedStatuses.split(' ').includes(column.dataset.status);

  function clearDrag() {
    dragging?.classList.remove('is-dragging');
    columns.forEach((column) => column.classList.remove('is-drop-allowed', 'is-drop-target'));
    dragging = null;
  }

  board.querySelectorAll('.response-card[draggable="true"] a').forEach((link) => { link.draggable = false; });

  board.addEventListener('dragstart', (event) => {
    const card = event.target.closest('.response-card[draggable="true"]');
    if (!card || event.target.closest('button')) { event.preventDefault(); return; }
    dragging = card;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', card.dataset.responseId);
    columns.forEach((column) => column.classList.toggle('is-drop-allowed', canDrop(column)));
    requestAnimationFrame(() => { if (dragging === card) card.classList.add('is-dragging'); });
  });

  board.addEventListener('dragover', (event) => {
    if (!dragging) return;
    event.preventDefault();
    const column = event.target.closest('.response-column');
    columns.forEach((item) => item.classList.toggle('is-drop-target', item === column && canDrop(item)));
    event.dataTransfer.dropEffect = column && canDrop(column) ? 'move' : 'none';
    const bounds = board.getBoundingClientRect();
    if (event.clientX < bounds.left + 55) board.scrollLeft -= 18;
    else if (event.clientX > bounds.right - 55) board.scrollLeft += 18;
  });

  board.addEventListener('dragleave', (event) => {
    if (!board.contains(event.relatedTarget)) columns.forEach((column) => column.classList.remove('is-drop-target'));
  });

  board.addEventListener('drop', (event) => {
    if (!dragging) return;
    event.preventDefault();
    const column = event.target.closest('.response-column');
    if (!column || !canDrop(column) || event.dataTransfer.getData('text/plain') !== dragging.dataset.responseId) { clearDrag(); return; }
    const action = [...dragging.querySelectorAll('[data-review-target]')]
      .find((button) => button.dataset.reviewTarget === column.dataset.status);
    clearDrag();
    if (action) {
      action.click();
      document.getElementById('board-review-note')?.focus();
    }
  });

  board.addEventListener('dragend', clearDrag);
})();
