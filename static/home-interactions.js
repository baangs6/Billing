// Theme toggle implementation with persistence and system sync
    const themeToggleBtn = document.getElementById('themeToggle');

    function applyTheme(isDark) {
      if (isDark) {
        document.documentElement.classList.add('dark');
        themeToggleBtn.setAttribute('aria-label', 'Switch to light mode');
      } else {
        document.documentElement.classList.remove('dark');
        themeToggleBtn.setAttribute('aria-label', 'Switch to dark mode');
      }
    }

    // Determine initial theme state
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialDark = savedTheme === 'dark' || (!savedTheme && prefersDark);
    applyTheme(initialDark);

    // Toggle event listener
    if (themeToggleBtn) {
      themeToggleBtn.addEventListener('click', () => {
        const isDark = document.documentElement.classList.contains('dark');
        applyTheme(!isDark);
        localStorage.setItem('theme', !isDark ? 'dark' : 'light');
      });
    }

    // Subtle 3D cursor perspective tilt for the macOS workspace mockup
    const mockupContainer = document.querySelector('.mockup-container');
    const mockupWindow = document.querySelector('.mockup-window');

    if (mockupContainer && mockupWindow && window.matchMedia('(prefers-reduced-motion: no-preference)').matches) {
      mockupContainer.addEventListener('mousemove', (e) => {
        const rect = mockupContainer.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        const rotateX = (-y / rect.height) * 4;
        const rotateY = (x / rect.width) * 4;
        mockupWindow.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
      });

      mockupContainer.addEventListener('mouseleave', () => {
        mockupWindow.style.transform = '';
      });
    }
