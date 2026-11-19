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

  function update() {
    frame = 0;
    const bounds = toc.getBoundingClientRect();
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
    if (!visibleLink || toc.scrollHeight <= toc.clientHeight) return;
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
    jumping = true;
    schedule();
  }

  toc.addEventListener('click', onJump);
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
