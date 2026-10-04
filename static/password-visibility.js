document.querySelectorAll('[data-password-visibility]').forEach(toggle => {
  const field = document.getElementById(toggle.dataset.passwordVisibility);
  if (!field) return;
  const update = () => { field.type = toggle.checked ? 'text' : 'password'; };
  toggle.checked = false;
  update();
  toggle.addEventListener('change', update);
  window.addEventListener('pageshow', () => { toggle.checked = false; update(); });
});
