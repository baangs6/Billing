const workspaceNavigation = document.querySelector('#workspace-navigation');
if (workspaceNavigation) {
  const mobile = window.matchMedia('(max-width: 768px)');
  const toggle = workspaceNavigation.querySelector('button');
  const sidebar = workspaceNavigation.querySelector('aside');
  const setExpanded = expanded => {
    sidebar.hidden = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
  };
  const syncNavigation = () => setExpanded(!mobile.matches);
  syncNavigation();
  mobile.addEventListener('change', syncNavigation);
  toggle.addEventListener('click', () => setExpanded(sidebar.hidden));
  workspaceNavigation.addEventListener('keydown', event => {
    if (event.key === 'Escape' && mobile.matches && !sidebar.hidden) {
      setExpanded(false);
      toggle.focus();
    }
  });
}
