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
  let frame = 0;

  function linkAtReadingLine(line) {
    if (article.getBoundingClientRect().bottom <= line) return null;

    // A short final section may reach the end of the page before it reaches the line.
    const page = document.scrollingElement;
    const last = sections[sections.length - 1];
    if (page.scrollTop > 0 && page.scrollHeight - page.clientHeight - page.scrollTop <= 1
        && last.heading.getBoundingClientRect().top < page.clientHeight) {
      return last.link;
    }

    let link = null;
    for (const section of sections) {
      if (section.heading.getBoundingClientRect().top > line) break;
      link = section.link;
    }
    return link;
  }

  function update() {
    frame = 0;
    const bounds = toc.getBoundingClientRect();
    // The fixed contents list starts at the same height as a native heading jump.
    const next = bounds.height ? linkAtReadingLine(bounds.top + 1) : null;
    if (current !== next) {
      if (current) current.removeAttribute('aria-current');
      current = next;
      if (current) current.setAttribute('aria-current', 'location');
    }

    // A long contents list can scroll independently of the article.
    if (!current || toc.scrollHeight <= toc.clientHeight) return;
    const row = current.getBoundingClientRect();
    if (row.top < bounds.top || row.height > bounds.height) {
      toc.scrollTop += row.top - bounds.top;
    } else if (row.bottom > bounds.bottom) {
      toc.scrollTop += row.bottom - bounds.bottom;
    }
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }

  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.addEventListener('hashchange', schedule);
  window.addEventListener('pageshow', schedule);
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(schedule);
    observer.observe(article);
    observer.observe(toc);
  }
  schedule();
})();
