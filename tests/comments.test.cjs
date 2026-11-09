const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('assets/js/comments.js', 'utf8');

function setup({ language = 'ko', theme = 'light', hasComments = true } = {}) {
  let activeTheme = theme;
  let frame = null;
  let onMutation;
  let onLoad;
  const sent = [];
  const script = {
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; }
  };
  const container = {
    querySelector() { return frame; },
    appendChild(element) { assert.equal(element, script); }
  };
  const section = {
    dataset: {
      repo: 'prismawelt/prismawelt.github.io',
      repoId: 'R_kgDOR1tSCQ',
      category: 'Announcements',
      categoryId: 'DIC_kwDOR1tSCc4DKuik',
      term: '/ko/nichijou/mono/',
      themeLight: 'https://prismawelt.github.io/assets/css/giscus-light.css?v=3',
      themeDark: 'https://prismawelt.github.io/assets/css/giscus-dark.css?v=3',
      language
    },
    querySelector() { return container; },
    addEventListener(type, callback, capture) {
      assert.equal(type, 'load');
      assert.equal(capture, true);
      onLoad = callback;
    }
  };
  const root = { getAttribute() { return activeTheme; } };
  vm.runInNewContext(source, {
    document: {
      documentElement: root,
      querySelector() { return hasComments ? section : null; },
      createElement(tag) { assert.equal(tag, 'script'); return script; }
    },
    MutationObserver: class {
      constructor(callback) { onMutation = callback; }
      observe(element, options) {
        assert.equal(element, root);
        assert.equal(options.attributeFilter[0], 'data-theme');
      }
    }
  });
  return {
    script, sent,
    toggle(value) { activeTheme = value; onMutation(); },
    loadFrame() {
      frame = { contentWindow: { postMessage(data, origin) { sent.push({ data, origin }); } } };
      onLoad({ target: { matches() { return true; } } });
    }
  };
}

test('all languages share one discussion with localized UI and strict matching', () => {
  for (const language of ['ko', 'en', 'ja']) {
    const { script } = setup({ language, theme: 'dark' });
    assert.equal(script.src, 'https://giscus.app/client.js');
    assert.equal(script.attributes['data-term'], '/ko/nichijou/mono/');
    assert.equal(script.attributes['data-lang'], language);
    assert.equal(script.attributes['data-strict'], '1');
    assert.equal(script.attributes['data-theme'], 'https://prismawelt.github.io/assets/css/giscus-dark.css?v=3');
    assert.equal(script.attributes['data-reactions-enabled'], '0');
    assert.equal(script.attributes['data-loading'], 'lazy');
    assert.equal(script.crossOrigin, 'anonymous');
  }
});

test('theme changes survive delayed iframe loading and target only giscus', () => {
  const app = setup();
  app.toggle('dark');
  assert.equal(app.sent.length, 0);
  app.loadFrame();
  assert.equal(app.sent[0].data.giscus.setConfig.theme, 'https://prismawelt.github.io/assets/css/giscus-dark.css?v=3');
  app.toggle('light');
  assert.equal(app.sent[1].data.giscus.setConfig.theme, 'https://prismawelt.github.io/assets/css/giscus-light.css?v=3');
  assert.ok(app.sent.every(message => message.origin === 'https://giscus.app'));
});

test('non-article pages do not load an external comment script', () => {
  const app = setup({ hasComments: false });
  assert.equal(app.script.src, undefined);
});
