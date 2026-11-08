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

// Mobile-only progressive enhancement; existing filter listeners stay intact.
(function () {
  const bar = document.querySelector('.filter-bar');
  if (!bar) return;
  const style = document.createElement('style');
  style.textContent = '.mobile-filter-toggle,.mobile-filter-apply{display:none}@media(max-width:720px){.mobile-filter-toggle,.mobile-filter-apply{display:block;width:100%;min-height:44px;margin:0 0 1rem;padding:.75rem 1rem;border:1px solid #666;border-radius:12px;background:#20202b;color:var(--text);font:inherit;text-align:left;cursor:pointer}.mobile-filter-apply{background:var(--accent);color:#111;text-align:center;font-weight:700}.filter-bar.mobile-filter-panel{display:none}.filter-bar.mobile-filter-panel.mobile-filter-open{display:flex;padding-bottom:1rem}.mobile-filter-apply:not(.mobile-filter-open){display:none}.mobile-filter-toggle{display:flex;justify-content:space-between;align-items:center}.mobile-filter-toggle::after{content:"+"}.mobile-filter-toggle[aria-expanded=true]::after{content:"−"}}';
  document.head.append(style);
  bar.id = bar.id || 'mobile-filter-panel';
  bar.classList.add('mobile-filter-panel');
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'mobile-filter-toggle';
  toggle.setAttribute('aria-controls', bar.id);
  const apply = document.createElement('button');
  apply.type = 'button';
  apply.className = 'mobile-filter-apply';
  apply.textContent = 'Apply filters';
  bar.before(toggle);
  bar.after(apply);
  const media = window.matchMedia('(max-width: 720px)');
  let open = false;
  function updatePanel() {
    bar.classList.toggle('mobile-filter-open', open);
    apply.classList.toggle('mobile-filter-open', open);
    toggle.setAttribute('aria-expanded', String(!media.matches || open));
  }
  function updateCount() {
    let count = 0;
    for (const id of ['branch', 'genre']) if (document.getElementById(id)?.value) count++;
    for (const id of ['available-only', 'recent-only', 'starred-only']) if (document.getElementById(id)?.checked) count++;
    const sort = document.getElementById('sort');
    if (sort && sort.value && sort.value !== 'relevance') count++;
    const options = Array.from(bar.querySelectorAll('.language-option'));
    if (options.length) {
      const defaults = typeof DEFAULT_LANGUAGES !== 'undefined' ? DEFAULT_LANGUAGES : ['Engelska', 'Svenska'];
      const selected = options.filter(option => option.checked).map(option => option.value);
      if (selected.length !== defaults.length || defaults.some(value => !selected.includes(value))) count++;
    }
    const label = count ? `Filters (${count} active)` : 'Filters';
    if (toggle.textContent !== label) toggle.textContent = label;
  }
  toggle.addEventListener('click', () => { open = !open; updatePanel(); });
  apply.addEventListener('click', () => {
    open = false;
    updatePanel();
    const menu = document.getElementById('language-menu');
    if (menu) menu.hidden = true;
    document.getElementById('language-toggle')?.setAttribute('aria-expanded', 'false');
    const results = document.getElementById('shelves');
    if (results) {
      results.setAttribute('tabindex', '-1');
      const header = document.querySelector('.site-header');
      results.style.scrollMarginTop = `${(header?.getBoundingClientRect().height || 0) + 16}px`;
      results.focus({ preventScroll: true });
      results.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  });
  bar.addEventListener('change', () => setTimeout(updateCount, 0));
  bar.addEventListener('click', () => setTimeout(updateCount, 0));
  new MutationObserver(updateCount).observe(bar, { childList: true, subtree: true });
  media.addEventListener('change', () => {
    if (media.matches) open = false;
    updatePanel();
  });
  window.addEventListener('popstate', () => setTimeout(updateCount, 0));
  updatePanel();
  updateCount();
})();
