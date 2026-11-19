(() => {
  const toc = document.querySelector('.article-toc');
  const article = document.querySelector('.detail-page article');
  if (!toc || !article) return;

  const sections = Array.from(toc.querySelectorAll('a[href^="#"]'), link => ({
    link,
    heading: document.getElementById(decodeURIComponent(link.hash.slice(1)))
  })).filter(({ heading }) => heading && article.contains(heading));
  if (!sections.length) return;

  let current = null;
  let approaching = null;
  let lastBlend = 0;
  let lastScrollY = window.scrollY;
  let jumping = true;
  let frame = 0;
  let press = null;
  let glide = null;
  let suppressPointerClick = false;

  function sectionFor(element) {
    const link = element?.closest('a');
    return sections.find(section => section.link === link);
  }

  function selectUnderPointer() {
    const hit = sectionFor(document.elementFromPoint(press.x, press.y));
    const section = hit || press.selected || press.origin;
    if (section === press.selected) return;
    // Save the starting scroll position once. Release finalizes the fragment for this drag.
    if (!press.historyAdded && location.hash !== section.link.hash) {
      history.pushState(history.state, '', section.link.hash);
      press.historyAdded = true;
    }
    press.selected = section;
    glide = {
      heading: section.heading,
      margin: parseFloat(getComputedStyle(section.heading).scrollMarginTop) || 0,
      from: window.scrollY,
      start: performance.now()
    };
  }

  function advanceGlide(now) {
    const { heading, margin, from, start } = glide;
    const page = document.scrollingElement;
    const target = Math.max(0, Math.min(page.scrollHeight - page.clientHeight,
      window.scrollY + heading.getBoundingClientRect().top - margin));
    const t = Math.max(0, Math.min(1, (now - start) / 500));
    window.scrollTo({ top: from + (target - from) * t * t * (3 - 2 * t), behavior: 'instant' });
    if (t < 1) schedule();
    else glide = null;
  }

  function scrollMenuAtEdge(now, bounds) {
    const elapsed = Math.max(0, Math.min(32, now - press.tick));
    press.tick = now;
    if (toc.scrollHeight <= toc.clientHeight || press.x < bounds.left || press.x >= bounds.right
        || press.y < bounds.top || press.y >= bounds.bottom) return;
    const edge = Math.min(24, bounds.height / 3);
    const speed = Math.min(0, press.y - bounds.top - edge)
      + Math.max(0, press.y - bounds.bottom + edge);
    if ((speed < 0 && toc.scrollTop > 0)
        || (speed > 0 && Math.ceil(toc.scrollTop + toc.clientHeight) < toc.scrollHeight)) {
      toc.scrollTop += Math.sign(speed) * Math.max(1, Math.abs(speed) * elapsed / 48);
      selectUnderPointer();
      schedule();
    }
  }

  function movePress(event) {
    if (!press || event.pointerId !== press.id) return;
    press.x = event.clientX;
    press.y = event.clientY;
    if (!press.dragging && Math.hypot(press.x - press.startX, press.y - press.startY) < 6) return;
    press.dragging = true;
    selectUnderPointer();
    schedule();
  }

  function finishPress(commitFragment = true) {
    if (!press) return;
    const { id, origin, selected } = press;
    press = null;
    if (selected) {
      suppressPointerClick = true;
      if (commitFragment && selected.link.hash !== location.hash) {
        history.replaceState(history.state, '', selected.link.hash);
      }
    }
    if (origin.link.hasPointerCapture(id)) origin.link.releasePointerCapture(id);
    schedule();
  }

  function stopGlide() {
    glide = null;
  }

  function cancelGesture() {
    stopGlide();
    finishPress();
  }

  function readingPosition(line, reach) {
    let link = null;
    let previousTop = -Infinity;
    if (article.getBoundingClientRect().bottom <= line) return { link };

    // A short last section can be visible without ever reaching the reading line.
    const page = document.scrollingElement;
    const last = sections[sections.length - 1];
    if (page.scrollTop > 0 && page.scrollHeight - page.clientHeight - page.scrollTop <= 1
        && last.heading.getBoundingClientRect().top < page.clientHeight) {
      return { link: last.link };
    }

    for (const section of sections) {
      const top = section.heading.getBoundingClientRect().top;
      if (top > line) {
        // Keep nearby parent/child headings distinct, including native anchor landings.
        const distance = Math.min(reach, top - previousTop);
        const t = Math.max(0, 1 - (top - line) / distance);
        return { link, next: t > 0 ? section.link : null, blend: t * t * (3 - 2 * t) };
      }
      link = section.link;
      previousTop = top;
    }
    return { link };
  }

  function update(now) {
    frame = 0;
    const bounds = toc.getBoundingClientRect();
    if (!bounds.height && (press || glide)) cancelGesture();
    if (press?.dragging) scrollMenuAtEdge(now, bounds);
    if (glide) advanceGlide(now);
    const reach = Math.min(200, document.documentElement.clientHeight / 4);
    const { link, next = null, blend = 0 } = bounds.height
      ? readingPosition(bounds.top + 1, reach) : { link: null };
    const y = window.scrollY;
    if (jumping || y !== lastScrollY) {
      toc.toggleAttribute('data-tracking-scroll', !jumping && Math.abs(y - lastScrollY) < reach);
      lastScrollY = y;
      jumping = false;
    }

    if (current !== link) {
      if (current) current.removeAttribute('aria-current');
      current = link;
      if (current) current.setAttribute('aria-current', 'location');
    }
    if (approaching !== next) {
      if (approaching) approaching.removeAttribute('data-approaching');
      approaching = next;
      if (approaching) approaching.setAttribute('data-approaching', '');
    }
    const percent = Math.round(blend * 1000) / 10;
    if (percent !== lastBlend) {
      toc.style.setProperty('--toc-blend', percent + '%');
      lastBlend = percent;
    }

    // Follow the more prominent row inside a long menu without scrolling the article.
    const visibleLink = blend >= 0.5 ? approaching : current;
    if (press || glide || !visibleLink || toc.scrollHeight <= toc.clientHeight) return;
    const row = visibleLink.getBoundingClientRect();
    if (row.top < bounds.top || row.height > bounds.height) {
      toc.scrollTop += row.top - bounds.top;
    } else if (row.bottom > bounds.bottom) {
      toc.scrollTop += row.bottom - bounds.bottom;
    }
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }

  function onJump() {
    stopGlide();
    finishPress(false);
    jumping = true;
    schedule();
  }

  if ('PointerEvent' in window) toc.setAttribute('data-drag-navigation', '');
  toc.addEventListener('pointerdown', event => {
    if (!event.isPrimary || press) return;
    suppressPointerClick = false;
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const origin = sectionFor(event.target);
    if (!origin) return;
    const { pointerId: id, clientX: x, clientY: y } = event;
    origin.link.setPointerCapture(id);
    press = {
      id, origin, startX: x, startY: y, x, y, tick: performance.now(),
      dragging: false, selected: null, historyAdded: false
    };
  });
  toc.addEventListener('pointermove', movePress);
  toc.addEventListener('pointerup', event => {
    if (!press || press.id !== event.pointerId) return;
    movePress(event);
    finishPress();
  });
  for (const type of ['pointercancel', 'lostpointercapture']) {
    toc.addEventListener(type, event => {
      if (press?.id === event.pointerId) cancelGesture();
    });
  }
  toc.addEventListener('click', event => {
    if (suppressPointerClick && event.detail > 0) {
      suppressPointerClick = false;
      event.preventDefault();
      return;
    }
    onJump();
  });
  window.addEventListener('pointerdown', stopGlide, { capture: true, passive: true });
  window.addEventListener('wheel', stopGlide, { passive: true });
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') cancelGesture();
    else stopGlide();
  });
  window.addEventListener('blur', cancelGesture);
  window.addEventListener('pagehide', onJump);
  window.addEventListener('popstate', onJump);
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.addEventListener('hashchange', onJump);
  window.addEventListener('pageshow', onJump);
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(schedule);
    observer.observe(article);
    observer.observe(toc);
  }
  schedule();
})();
