(function () {
  const STORAGE_KEY = 'prismawelt-theme';
  const root = document.documentElement;
  const themeColor = document.querySelector('meta[name="theme-color"]');

  const labels = {
    ko: {
      dark: '다크 모드로 전환',
      light: '라이트 모드로 전환'
    },
    ja: {
      dark: 'ダークモードに切り替え',
      light: 'ライトモードに切り替え'
    },
    en: {
      dark: 'Switch to dark mode',
      light: 'Switch to light mode'
    }
  };

  function pageLanguage() {
    const language = (root.lang || 'en').toLowerCase().split('-')[0];
    return labels[language] ? language : 'en';
  }

  function updateControls(theme) {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    const label = labels[pageLanguage()][nextTheme];

    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
      button.setAttribute('aria-pressed', String(theme === 'dark'));
    });
  }

  function applyTheme(theme, persist) {
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;

    if (themeColor) {
      themeColor.setAttribute('content', theme === 'dark' ? '#1e1e1e' : '#ffffff');
    }

    updateControls(theme);

    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch (error) {
        // The theme still applies for this page when storage is unavailable.
      }
    }
  }

  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const currentTheme = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      applyTheme(currentTheme === 'dark' ? 'light' : 'dark', true);
    });
  });

  window.addEventListener('storage', (event) => {
    if (event.key !== STORAGE_KEY) return;
    const theme = event.newValue === 'dark' || event.newValue === 'light'
      ? event.newValue
      : 'light';
    applyTheme(theme, false);
  });

  applyTheme(
    root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light',
    false
  );
}());
