(() => {
  const shell = document.querySelector('.dashboard-shell');
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.querySelector('.sidebar-toggle');
  const closeMenu = () => {
    sidebar?.classList.remove('open');
    shell?.classList.remove('menu-open');
    toggle?.setAttribute('aria-expanded', 'false');
  };
  toggle?.addEventListener('click', () => {
    const open = !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', open);
    shell.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  });
  shell?.addEventListener('click', event => {
    if (event.target === shell && shell.classList.contains('menu-open')) closeMenu();
  });
  document.querySelectorAll('a[href$="#create"]').forEach(link => link.addEventListener('click', event => {
    const target = document.getElementById('create');
    if (!target) return;
    event.preventDefault();
    if (window.location.hash !== '#create') history.replaceState(null, '', '#create');
    target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    target.classList.remove('create-highlight');
    requestAnimationFrame(() => target.classList.add('create-highlight'));
  }));
  document.querySelectorAll('[data-coming]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    window.alert('Этот раздел подключим следующим этапом. Сейчас уже работают регистрация, вход и профиль.');
    closeMenu();
  }));
  const themeButton = document.querySelector('.dash-theme-toggle');
  // Server-rendered theme is the source of truth. localStorage must not overwrite account settings.
  let theme = document.documentElement.dataset.theme || 'light';
  try { localStorage.setItem('monstroart-theme', theme); } catch (_) {}
  const paintTheme = () => { if (themeButton) themeButton.textContent = theme === 'dark' ? '☀' : '☾'; };
  paintTheme();
  themeButton?.addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('monstroart-theme', theme); } catch (_) {}
    paintTheme();
  });
})();
