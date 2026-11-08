const sizeButtons = document.querySelectorAll('[data-thumbnail-size]');
const grid = document.getElementById('book-grid');
const savedSize = localStorage.getItem('thumbnailSize') || 'large';
let currentSize = savedSize;

function applySize(size) {
  currentSize = size;
  localStorage.setItem('thumbnailSize', size);
  grid.classList.remove('thumb-small', 'thumb-medium', 'thumb-large');
  grid.classList.add(`thumb-${size}`);
  sizeButtons.forEach(button => {
    button.classList.toggle('active', button.dataset.thumbnailSize === size);
  });
  document.querySelectorAll('.book-cover img').forEach(img => {
    const base = img.dataset.coverUrl;
    if (!base) return;
    const suffix = size === 'small' ? '_S' : size === 'medium' ? '_M' : '_L';
    const stem = base.replace(/_(S|M|L)(\.[a-zA-Z0-9]+)?$/, '$2');
    img.src = stem.includes('.') ? `${stem.replace(/\.[a-zA-Z0-9]+$/, '')}${suffix}.${stem.split('.').pop()}` : `${base}${suffix}`;
  });
}

sizeButtons.forEach(button => {
  button.addEventListener('click', () => applySize(button.dataset.thumbnailSize));
});

applySize(currentSize);
