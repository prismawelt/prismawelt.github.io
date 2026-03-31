document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.detail-body, .home-after-text').forEach(enhanceFigures);
});

function enhanceFigures(container){
  const paragraphs = Array.from(container.querySelectorAll(':scope > p'));
  paragraphs.forEach((p) => {
    const onlyChild = p.children.length === 1 ? p.children[0] : null;
    const hasSingleImage = onlyChild && (
      onlyChild.tagName === 'IMG' ||
      (onlyChild.tagName === 'A' && onlyChild.children.length === 1 && onlyChild.querySelector('img'))
    );
    if (!hasSingleImage) return;

    const next = p.nextElementSibling;
    if (!next || next.tagName !== 'P') return;
    if (next.children.length !== 1) return;
    const captionEl = next.children[0];
    if (!(captionEl.tagName === 'EM' || captionEl.tagName === 'I')) return;

    const caption = next.textContent.trim();
    if (!caption) return;

    const figure = document.createElement('figure');
    figure.className = 'md-figure';
    figure.innerHTML = p.innerHTML;

    const figcaption = document.createElement('figcaption');
    figcaption.textContent = caption;
    figure.appendChild(figcaption);

    p.replaceWith(figure);
    next.remove();
  });
}
