document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.detail-body, .home-after-text').forEach(enhanceFigures);
});

const VIDEO_EXTS = /\.(mp4|webm|ogg|mov)(\?.*)?$/i;
const YT_RE = /^https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?(?:.*&)?v=|youtu\.be\/)([A-Za-z0-9_-]{11})/;

function extractYoutubeId(url){
  const m = url.match(YT_RE);
  return m ? m[1] : null;
}

function enhanceFigures(container){
  const paragraphs = Array.from(container.querySelectorAll(':scope > p'));
  paragraphs.forEach((p) => {
    const onlyChild = p.children.length === 1 ? p.children[0] : null;

    // --- image or video file ---
    const hasSingleImage = onlyChild && (
      onlyChild.tagName === 'IMG' ||
      (onlyChild.tagName === 'A' && onlyChild.children.length === 1 && onlyChild.querySelector('img'))
    );

    if (hasSingleImage) {
      const img = onlyChild.tagName === 'IMG' ? onlyChild : onlyChild.querySelector('img');
      const src = img.getAttribute('src') || '';

      let media;
      if (VIDEO_EXTS.test(src)) {
        media = document.createElement('video');
        media.setAttribute('controls', '');
        media.setAttribute('src', src);
      } else {
        media = onlyChild;
      }

      wrapFigure(p, media);
      return;
    }

    // --- bare YouTube URL ---
    if (p.children.length === 0 && p.childNodes.length === 1) {
      const text = p.textContent.trim();
      const ytId = extractYoutubeId(text);
      if (ytId) {
        const embed = document.createElement('div');
        embed.className = 'md-embed';
        const iframe = document.createElement('iframe');
        iframe.src = `https://www.youtube.com/embed/${ytId}`;
        iframe.setAttribute('allowfullscreen', '');
        embed.appendChild(iframe);
        wrapFigure(p, embed);
        return;
      }
    }

    // --- YouTube link (<a> wrapping text that is a YT URL) ---
    if (onlyChild && onlyChild.tagName === 'A') {
      const href = onlyChild.getAttribute('href') || '';
      const ytId = extractYoutubeId(href);
      if (ytId) {
        const embed = document.createElement('div');
        embed.className = 'md-embed';
        const iframe = document.createElement('iframe');
        iframe.src = `https://www.youtube.com/embed/${ytId}`;
        iframe.setAttribute('allowfullscreen', '');
        embed.appendChild(iframe);
        wrapFigure(p, embed);
        return;
      }
    }
  });
}

function wrapFigure(p, media) {
  const next = p.nextElementSibling;
  let caption = null;

  if (next && next.tagName === 'P' && next.children.length === 1) {
    const captionEl = next.children[0];
    if (captionEl.tagName === 'EM' || captionEl.tagName === 'I') {
      caption = next.textContent.trim();
    }
  }

  const figure = document.createElement('figure');
  figure.className = 'md-figure';
  figure.appendChild(media.cloneNode ? media.cloneNode(true) : media);

  if (caption) {
    const figcaption = document.createElement('figcaption');
    figcaption.textContent = caption;
    figure.appendChild(figcaption);
    next.remove();
  }

  p.replaceWith(figure);
}
