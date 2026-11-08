(function () {
  const controls = document.getElementById('thumbnail-controls');
  if (!controls) return;
  const buttons = Array.from(controls.querySelectorAll('button[data-thumbnail-size]'));
  const stored = localStorage.getItem('thumbnailSize') || 'large';

  function apply(size) {
    document.body.dataset.thumbnailSize = size;
    localStorage.setItem('thumbnailSize', size);
    buttons.forEach(button => {
      button.classList.toggle('active', button.dataset.thumbnailSize === size);
    });
  }

  buttons.forEach(button => {
    button.addEventListener('click', () => apply(button.dataset.thumbnailSize));
  });

  apply(stored);
})();
