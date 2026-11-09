(function () {
  'use strict';

  const section = document.querySelector('[data-comments]');
  if (!section) return;

  const root = document.documentElement;
  const container = section.querySelector('.giscus');
  const script = document.createElement('script');
  const origin = section.dataset.server || 'https://giscus.app';

  function theme() {
    return root.getAttribute('data-theme') === 'dark'
      ? section.dataset.themeDark
      : section.dataset.themeLight;
  }

  function syncTheme() {
    script.setAttribute('data-theme', theme());
    const frame = container.querySelector('iframe.giscus-frame');
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ giscus: { setConfig: { theme: theme() } } }, origin);
    }
  }

  const attributes = {
    'data-repo': section.dataset.repo,
    'data-repo-id': section.dataset.repoId,
    'data-category': section.dataset.category,
    'data-category-id': section.dataset.categoryId,
    // All translations use the Korean original's stable path.
    'data-mapping': 'specific',
    'data-term': section.dataset.term,
    'data-strict': '1',
    'data-reactions-enabled': '0',
    'data-emit-metadata': '0',
    'data-input-position': 'top',
    'data-theme': theme(),
    'data-lang': section.dataset.language,
    'data-loading': 'lazy'
  };

  Object.entries(attributes).forEach(([name, value]) => script.setAttribute(name, value));
  script.src = origin + '/client.js';
  script.async = true;
  script.crossOrigin = 'anonymous';

  // A theme change before the lazily loaded frame is ready must also be applied.
  section.addEventListener('load', (event) => {
    if (event.target.matches && event.target.matches('iframe.giscus-frame')) syncTheme();
  }, true);
  new MutationObserver(syncTheme).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  container.appendChild(script);
}());
