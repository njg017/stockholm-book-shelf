(function () {
  const controls = document.getElementById('thumbnail-controls');
  if (!controls) return;
  const buttons = Array.from(controls.querySelectorAll('button[data-thumbnail-size]'));
  const sizes = ['small', 'medium', 'large'];
  let stored = 'small';
  try { stored = localStorage.getItem('thumbnailSize') || 'small'; } catch (_) {}
  controls.setAttribute('role', 'group');
  controls.setAttribute('aria-label', 'Book card size');
  function apply(size, persist) {
    if (!sizes.includes(size)) size = 'small';
    document.body.dataset.thumbnailSize = size;
    if (persist) { try { localStorage.setItem('thumbnailSize', size); } catch (_) {} }
    buttons.forEach(button => {
      const active = button.dataset.thumbnailSize === size;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }
  buttons.forEach(button => button.addEventListener('click', () => apply(button.dataset.thumbnailSize, true)));
  const modal = document.getElementById('book-modal');
  if (modal) {
    const sync = () => { controls.hidden = !modal.hidden; };
    new MutationObserver(sync).observe(modal, { attributes: true, attributeFilter: ['hidden'] });
    sync();
  }
  apply(stored, false);
})();
