
document.addEventListener('DOMContentLoaded', () => {
  initMobileMenu();
  document.querySelectorAll('[data-archive-page]').forEach(initArchive);
  document.querySelectorAll('.detail-page').forEach(initDetailTitle);
  document.querySelectorAll('[data-ihatov-music]').forEach(initIhatovMusic);
});

function initMobileMenu(){
  const shell = document.querySelector('.site-shell');
  const toggle = document.querySelector('.menu-toggle');
  const menu = document.querySelector('.menu-list');
  const overlay = document.querySelector('.menu-overlay');
  if(!shell || !toggle || !menu || !overlay) return;

  function closeMenu(){
    shell.classList.remove('menu-open');
    toggle.setAttribute('aria-expanded','false');
  }

  function openMenu(){
    shell.classList.add('menu-open');
    toggle.setAttribute('aria-expanded','true');
  }

  toggle.addEventListener('click', () => {
    if(shell.classList.contains('menu-open')) closeMenu();
    else openMenu();
  });

  overlay.addEventListener('click', closeMenu);
  menu.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
  window.addEventListener('resize', () => { if(window.innerWidth > 640) closeMenu(); });
}

function initArchive(root){
  const list = root.querySelector('[data-archive-list]');
  if(!list) return;
  const rows = Array.from(list.querySelectorAll('.archive-row'));
  const filterButtons = Array.from(root.querySelectorAll('[data-filter-group] [data-filter]'));
  const sortButtons = Array.from(root.querySelectorAll('.archive-index [data-sort]'));
  const searchInput = root.querySelector('[data-search-input]');
  const countEl = root.querySelector('[data-result-count]');
  const emptyEl = root.querySelector('[data-result-empty]');

  let filter = 'all';
  let sortKey = 'date';
  let sortDir = 'desc';
  let query = '';

  function text(el, selector){
    const node = el.querySelector(selector);
    return node ? node.textContent.trim() : '';
  }

  function haystack(row){
    return [
      row.dataset.title || text(row,'.title'),
      row.dataset.series || text(row,'.series'),
      row.dataset.type || text(row,'.type'),
      row.dataset.date || text(row,'.date'),
      row.dataset.body || ''
    ].join(' ').toLowerCase();
  }

  function compareValues(a, b, key){
    const av = (a.dataset[key] || text(a,'.'+key) || '').toLowerCase();
    const bv = (b.dataset[key] || text(b,'.'+key) || '').toLowerCase();
    if(key === 'date'){
      return av.localeCompare(bv);
    }
    return av.localeCompare(bv, undefined, {numeric:true, sensitivity:'base'});
  }

  function apply(){
    let visible = rows.filter(row => {
      const matchesFilter = filter === 'all' || (row.dataset.type || '').toLowerCase() === filter.toLowerCase();
      const matchesQuery = !query || haystack(row).includes(query);
      return matchesFilter && matchesQuery;
    });

    const sorted = [...visible].sort((a,b) => {
      const cmp = compareValues(a,b,sortKey);
      return sortDir === 'asc' ? cmp : -cmp;
    });

    rows.forEach(row => row.classList.add('hidden'));
    sorted.forEach(row => {
      row.classList.remove('hidden');
      list.appendChild(row);
    });

    if(countEl) countEl.textContent = String(sorted.length);
    if(emptyEl) emptyEl.style.display = sorted.length ? 'none' : 'block';

    sortButtons.forEach(btn => {
      btn.classList.remove('is-asc','is-desc');
      if(btn.dataset.sort === sortKey){
        btn.classList.add(sortDir === 'asc' ? 'is-asc' : 'is-desc');
      }
    });

    filterButtons.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.filter === filter);
    });
  }

  filterButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      filter = btn.dataset.filter;
      apply();
    });
  });

  sortButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.sort;
      if(sortKey === key){
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        sortKey = key;
        sortDir = key === 'date' ? 'desc' : 'asc';
      }
      apply();
    });
  });

  if(searchInput){
    searchInput.addEventListener('input', () => {
      query = searchInput.value.trim().toLowerCase();
      apply();
    });
  }

  apply();
}


function initDetailTitle(root){
  const title = root.querySelector('.detail-title');
  const floating = root.querySelector('.detail-floating-title');
  if(!title || !floating) return;

  function update(){
    const rect = title.getBoundingClientRect();
    const threshold = window.innerWidth <= 640 ? 42 : 46;
    floating.classList.toggle('is-visible', rect.bottom < threshold);
  }

  update();
  window.addEventListener('scroll', update, {passive:true});
  window.addEventListener('resize', update);
}

function specSort(items){
  const chrom = [], grey = [];
  items.forEach(d => { (d.hsv[1] >= 20 && d.hsv[2] >= 14 ? chrom : grey).push(d); });
  chrom.sort((a, b) => (a.hsv[0] - b.hsv[0]) || (b.hsv[2] - a.hsv[2]) || a.id.localeCompare(b.id));
  grey.sort((a, b) => (b.hsv[2] - a.hsv[2]) || a.id.localeCompare(b.id));
  return chrom.concat(grey);
}

function specSize(n, W, maxH){
  let s = 28;
  while (s > 4 && Math.ceil(n / Math.max(1, Math.floor(W / s))) * s > maxH) s--;
  return s;
}

function specLayout(sorted, W, size){
  const cols = Math.max(1, Math.floor(W / size));
  const rows = Math.ceil(sorted.length / cols);
  const pos = {};
  sorted.forEach((d, i) => {
    pos[d.id] = { x: (i % cols) * size, y: Math.floor(i / cols) * size };
  });
  return { pos, w: cols * size, h: rows * size };
}

function scaledSpecSize(n, W, maxH, scale){
  const base = specSize(n, W, maxH);
  const wanted = Math.max(1, base * scale);
  return Math.min(wanted, W);
}

async function loadArchive(root){
  const [archive, sprite] = await Promise.all([
    fetch(root.dataset.archiveUrl).then(res => {
      if(!res.ok) throw new Error('archive');
      return res.json();
    }),
    fetch(root.dataset.spriteJsonUrl).then(res => {
      if(!res.ok) throw new Error('sprite.json');
      return res.json();
    })
  ]);

  const slotById = new Map(sprite.ids.map((id, slot) => [id, slot]));
  const items = archive.items
    .map(item => {
      const slot = slotById.get(item.id);
      if(slot === undefined) return null;
      return {
        ...item,
        cover: item.cover || '',
        slot,
        hsv: sprite.hsv[item.id] || [0,0,100]
      };
    })
    .filter(Boolean);

  return {
    items,
    cols: sprite.cols,
    spriteUrl: root.dataset.spriteImageUrl
  };
}

function initIhatovMusic(root){
  const board = root.querySelector('#spectrum');
  const readout = root.querySelector('#readout');
  const ratingButtons = Array.from(root.querySelectorAll('[data-rating-filter]'));
  const ratingStars = root.querySelector('[data-rating-stars]');
  const preview = root.querySelector('[data-cover-preview]');
  const status = root.querySelector('[data-ihatov-music-status]');
  if(!board) return;

  let archive = null;
  let ratingFilter = 'all';
  let ratingDrag = false;
  let activeItem = null;
  let copyPopup = null;
  let copyPopupTimer = 0;
  let previewHideTimer = 0;
  let renderedItems = new Map();
  let renderedCovers = [];
  let touchSelectActive = false;
  let touchSelectMoved = false;
  let touchSelectPointerId = null;
  let touchSelectStart = { x: 0, y: 0 };
  let touchSelectedCover = null;
  let suppressNextCoverClick = false;
  let touchFallbackActive = false;
  let lastTouchInteractionAt = 0;
  const recentTouchThreshold = 1000;

  function albumLabel(item){
    const artist = item.artist || item.artist_latin || '';
    const year = item.year ? ` (${item.year})` : '';
    return `${artist} - ${item.title}${year}`;
  }

  function updateReadout(item){
    if(!readout) return;
    activeItem = item;
    const existingPopup = copyPopup && copyPopup.parentNode === readout ? copyPopup : null;
    readout.textContent = '';
    readout.appendChild(readoutLine(item.artist || item.artist_latin || '', 'artist'));
    const title = item.year ? `${item.title || ''} (${item.year})` : item.title || '';
    readout.appendChild(readoutLine(title, 'album'));
    readout.appendChild(readoutRatingLine(item));
    if(existingPopup) readout.appendChild(existingPopup);
    requestAnimationFrame(syncReadoutMarquee);
  }

  function ratingImageUrl(rating){
    const value = Math.max(0, Math.min(10, Number(rating) || 0));
    return `${root.dataset.ratingImageBase}${value}m.png`;
  }

  function readoutLine(textValue, kind){
    const line = document.createElement('div');
    line.className = `readout-line readout-${kind}`;

    const track = document.createElement('span');
    track.className = 'readout-track';

    const text = document.createElement('span');
    text.className = 'readout-text';
    text.textContent = textValue;

    const copy = document.createElement('span');
    copy.className = 'readout-copy';
    copy.setAttribute('aria-hidden', 'true');
    copy.textContent = textValue;

    track.append(text, copy);
    line.appendChild(track);
    return line;
  }

  function readoutRatingLine(item){
    const line = document.createElement('div');
    line.className = 'readout-rating';

    const stars = document.createElement('span');
    stars.className = 'readout-rating-stars';
    stars.style.backgroundImage = `url(${ratingImageUrl(item.rating)})`;
    stars.setAttribute('role', 'img');
    stars.setAttribute('aria-label', `${Number(item.rating) / 2} stars`);

    line.appendChild(stars);
    return line;
  }

  function syncReadoutMarquee(){
    if(!readout) return;
    readout.querySelectorAll('.readout-line').forEach(line => {
      const text = line.querySelector('.readout-text');
      if(!text) return;
      line.classList.toggle('is-marquee', text.scrollWidth > line.clientWidth);
      const duration = Math.max(8, Math.min(28, text.scrollWidth / 34));
      line.style.setProperty('--marquee-duration', `${duration}s`);
    });
  }

  function fallbackCopyText(value){
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.select();
    let copied = false;
    try{
      copied = document.execCommand('copy');
    } catch(_error){
      copied = false;
    }
    textarea.remove();
    return copied;
  }

  async function copyText(value){
    if(navigator.clipboard && navigator.clipboard.writeText){
      try{
        await navigator.clipboard.writeText(value);
        return true;
      } catch(_error){
        return fallbackCopyText(value);
      }
    }
    return fallbackCopyText(value);
  }

  function ensureCopyPopup(){
    if(copyPopup) return copyPopup;
    copyPopup = document.createElement('div');
    copyPopup.className = 'copy-popup';
    copyPopup.setAttribute('role', 'status');
    copyPopup.setAttribute('aria-live', 'polite');
    copyPopup.hidden = true;
    if(readout) readout.appendChild(copyPopup);
    else root.appendChild(copyPopup);
    return copyPopup;
  }

  function showCopyPopup(value, copied){
    const popup = ensureCopyPopup();
    popup.textContent = copied ? 'COPIED' : 'FAILED';
    popup.hidden = false;
    popup.classList.remove('is-visible');
    if(readout) readout.classList.add('has-copy-popup');
    window.clearTimeout(copyPopupTimer);
    requestAnimationFrame(() => popup.classList.add('is-visible'));

    copyPopupTimer = window.setTimeout(() => {
      popup.classList.remove('is-visible');
      window.setTimeout(() => {
        if(!popup.classList.contains('is-visible')){
          popup.hidden = true;
          if(readout) readout.classList.remove('has-copy-popup');
        }
      }, 180);
    }, 1200);
  }

  function copyAlbumLabel(item){
    const value = albumLabel(item);
    copyText(value).then(copied => showCopyPopup(value, copied));
  }

  function eventPoint(event){
    const touch =
      event.touches && event.touches[0] ? event.touches[0] :
      event.changedTouches && event.changedTouches[0] ? event.changedTouches[0] :
      event;
    if(typeof touch.clientX !== 'number' || typeof touch.clientY !== 'number') return null;
    return { x: touch.clientX, y: touch.clientY };
  }

  function isTouchLike(event){
    return event.pointerType === 'touch' || Boolean(event.touches || event.changedTouches);
  }

  function hasRecentTouchInteraction(){
    return Date.now() - lastTouchInteractionAt < recentTouchThreshold;
  }

  function coverAtPoint(event){
    const point = eventPoint(event);
    if(!point) return null;
    const rect = board.getBoundingClientRect();
    const x = point.x - rect.left;
    const y = point.y - rect.top;
    for(let i = renderedCovers.length - 1; i >= 0; i -= 1){
      const cover = renderedCovers[i];
      if(x >= cover.x && x < cover.x + cover.size && y >= cover.y && y < cover.y + cover.size){
        return cover.el;
      }
    }

    const el = document.elementFromPoint(point.x, point.y);
    if(!el || !el.closest) return null;
    const cover = el.closest('.ihatov-cover');
    if(!cover || !board.contains(cover)) return null;
    return cover;
  }

  function selectCover(cover, event, forceTouchPreview){
    if(!cover) return;
    if(touchSelectedCover && touchSelectedCover !== cover){
      touchSelectedCover.classList.remove('is-selected');
    }
    touchSelectedCover = cover;
    cover.classList.add('is-selected');
    const item = renderedItems.get(cover.dataset.itemId);
    if(item){
      updateReadout(item);
      if(event) showPreview(item, event, forceTouchPreview);
    }
  }

  function beginTouchSelect(event){
    if(event.pointerType === 'mouse') return;
    const cover = coverAtPoint(event);
    if(!cover) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    touchFallbackActive = false;
    touchSelectActive = true;
    touchSelectMoved = false;
    touchSelectPointerId = event.pointerId;
    touchSelectStart = eventPoint(event);
    try{
      board.setPointerCapture(event.pointerId);
    } catch(_error){
      // Some mobile browsers expose pointer events without reliable capture.
    }
    selectCover(cover, event, true);
  }

  function moveTouchSelect(event){
    if(!touchSelectActive || event.pointerId !== touchSelectPointerId) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    const point = eventPoint(event);
    if(point && touchSelectStart){
      const dx = point.x - touchSelectStart.x;
      const dy = point.y - touchSelectStart.y;
      if(Math.hypot(dx, dy) > 8) touchSelectMoved = true;
    }
    selectCover(coverAtPoint(event), event, true);
  }

  function endTouchSelect(event, copyOnTap){
    if(!touchSelectActive || event.pointerId !== touchSelectPointerId) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    const selectedCover = touchSelectedCover;
    const moved = touchSelectMoved;
    touchSelectActive = false;
    touchSelectPointerId = null;
    try{
      board.releasePointerCapture(event.pointerId);
    } catch(_error){
      // Pointer capture may already be gone after browser cancellation.
    }

    suppressNextCoverClick = true;
    window.setTimeout(() => {
      suppressNextCoverClick = false;
    }, 250);

    if(copyOnTap && !moved && selectedCover){
      const item = renderedItems.get(selectedCover.dataset.itemId);
      if(item) copyAlbumLabel(item);
    }

    window.clearTimeout(previewHideTimer);
    previewHideTimer = window.setTimeout(hidePreview, 120);
  }

  function beginTouchFallback(event){
    if(touchSelectActive){
      event.preventDefault();
      lastTouchInteractionAt = Date.now();
      touchFallbackActive = true;
      return;
    }
    const cover = coverAtPoint(event);
    if(!cover) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    touchFallbackActive = true;
    touchSelectActive = true;
    touchSelectMoved = false;
    touchSelectPointerId = null;
    touchSelectStart = eventPoint(event);
    selectCover(cover, event, true);
  }

  function moveTouchFallback(event){
    if(!touchSelectActive) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    touchFallbackActive = true;
    const point = eventPoint(event);
    if(point && touchSelectStart){
      const dx = point.x - touchSelectStart.x;
      const dy = point.y - touchSelectStart.y;
      if(Math.hypot(dx, dy) > 8) touchSelectMoved = true;
    }
    selectCover(coverAtPoint(event), event, true);
  }

  function endTouchFallback(event, copyOnTap){
    if(!touchSelectActive) return;
    event.preventDefault();
    lastTouchInteractionAt = Date.now();
    const selectedCover = touchSelectedCover;
    const moved = touchSelectMoved;
    touchFallbackActive = false;
    touchSelectActive = false;
    touchSelectPointerId = null;

    suppressNextCoverClick = true;
    window.setTimeout(() => {
      suppressNextCoverClick = false;
    }, 250);

    if(copyOnTap && !moved && selectedCover){
      const item = renderedItems.get(selectedCover.dataset.itemId);
      if(item) copyAlbumLabel(item);
    }

    window.clearTimeout(previewHideTimer);
    previewHideTimer = window.setTimeout(hidePreview, 120);
  }

  function filteredItems(){
    if(!archive) return [];
    if(ratingFilter === 'all') return archive.items;
    const rating = Number(ratingFilter);
    return archive.items.filter(item => Number(item.rating) === rating);
  }

  function updateRatingStars(){
    const rating = ratingFilter === 'all' ? 0 : Number(ratingFilter);
    if(ratingStars){
      ratingStars.style.backgroundImage = `url(${ratingImageUrl(rating)})`;
    }
  }

  function ratingFromPointer(event){
    if(!ratingStars) return 'all';
    const rect = ratingStars.getBoundingClientRect();
    if(event.clientX <= rect.left + 4) return 'all';
    const x = Math.max(0, Math.min(rect.width - 0.001, event.clientX - rect.left));
    return String(Math.max(1, Math.min(10, Math.floor((x / rect.width) * 10) + 1)));
  }

  function setRatingFilter(next){
    hidePreview();
    ratingFilter = ratingFilter === next ? 'all' : next;
    updateRatingStars();
    render();
  }

  function scrubRating(event){
    if(!ratingStars) return;
    hidePreview();
    ratingFilter = ratingFromPointer(event);
    updateRatingStars();
    render();
  }

  function blockNativeSelection(event){
    event.preventDefault();
  }

  function movePreview(event, forceTouchPreview){
    if(!preview || preview.hidden) return;
    const point = eventPoint(event);
    if(!point) return;
    const rect = preview.getBoundingClientRect();
    const gap = 14;
    const touchPreview = forceTouchPreview || isTouchLike(event) || hasRecentTouchInteraction();
    let x = point.x + gap;
    let y = point.y + gap;
    if(touchPreview){
      x = point.x - (rect.width / 2);
      y = point.y - rect.height - 24;
    }
    x = Math.min(x, window.innerWidth - rect.width - gap);
    preview.style.left = `${Math.max(gap, x)}px`;
    preview.style.top = touchPreview
      ? `${y}px`
      : `${Math.max(gap, Math.min(y, window.innerHeight - rect.height - gap))}px`;
  }

  function showPreview(item, event, forceTouchPreview){
    if(!preview || !archive) return;
    window.clearTimeout(previewHideTimer);
    const touchPreview = forceTouchPreview || isTouchLike(event) || hasRecentTouchInteraction();
    const point = eventPoint(event);
    const touchBaseSize = Math.round(Math.max(84, Math.min(112, window.innerWidth * 0.24)));
    const touchAvailableAbove = point ? point.y - 38 : touchBaseSize;
    const previewSize = touchPreview
      ? Math.round(touchAvailableAbove > 0 ? Math.min(touchBaseSize, Math.max(32, touchAvailableAbove)) : touchBaseSize)
      : Math.round(Math.max(112, Math.min(190, window.innerWidth * 0.16)) / 2);
    preview.hidden = false;
    preview.style.width = `${previewSize}px`;
    preview.style.height = `${previewSize}px`;
    preview.style.backgroundImage = `url(${archive.spriteUrl})`;
    preview.style.backgroundSize = `${archive.cols * previewSize}px auto`;
    preview.style.backgroundPosition =
      `${-(item.slot % archive.cols) * previewSize}px ${-Math.floor(item.slot / archive.cols) * previewSize}px`;
    movePreview(event, touchPreview);
  }

  function hidePreview(){
    window.clearTimeout(previewHideTimer);
    previewHideTimer = 0;
    if(preview) preview.hidden = true;
  }

  function render(){
    if(!archive) return;
    hidePreview();
    const rootStyle = window.getComputedStyle(root);
    const rootPadding =
      Number.parseFloat(rootStyle.paddingLeft || '0') +
      Number.parseFloat(rootStyle.paddingRight || '0');
    const W = Math.max(1, Math.min(1040, Math.floor(root.clientWidth - rootPadding)));
    const maxH = 460;
    const sorted = specSort(filteredItems());
    const currentSize = Math.round(scaledSpecSize(archive.items.length, W, maxH, 1.5) / 1.5);
    const size = Math.max(1, Math.min(W, Math.round(currentSize * 1.3)));
    const lay = specLayout(sorted, W, size);
    const fragment = document.createDocumentFragment();

    board.style.width = `${lay.w}px`;
    board.style.height = `${lay.h}px`;
    board.textContent = '';
    renderedItems = new Map(sorted.map(item => [item.id, item]));
    renderedCovers = [];
    touchSelectedCover = null;

    sorted.forEach(item => {
      const p = lay.pos[item.id];
      const cover = document.createElement('div');
      cover.className = 'cover ihatov-cover';
      cover.dataset.itemId = item.id;
      cover.setAttribute('role','img');
      cover.setAttribute('aria-label', albumLabel(item));
      cover.style.width = `${size}px`;
      cover.style.height = `${size}px`;
      cover.style.left = `${p.x}px`;
      cover.style.top = `${p.y}px`;
      cover.style.backgroundImage = `url(${archive.spriteUrl})`;
      cover.style.backgroundSize = `${archive.cols * size}px auto`;
      cover.style.backgroundPosition =
        `${-(item.slot % archive.cols) * size}px ${-Math.floor(item.slot / archive.cols) * size}px`;
      cover.addEventListener('mouseenter', () => {
        updateReadout(item);
      });
      cover.addEventListener('mousemove', event => {
        if(hasRecentTouchInteraction()) return;
        showPreview(item, event);
      });
      cover.addEventListener('click', event => {
        if(suppressNextCoverClick || hasRecentTouchInteraction()){
          event.preventDefault();
          return;
        }
        copyAlbumLabel(item);
      });
      cover.addEventListener('mouseleave', hidePreview);
      fragment.appendChild(cover);
      renderedCovers.push({ el: cover, x: p.x, y: p.y, size });
    });

    board.appendChild(fragment);
  }

  loadArchive(root)
    .then(data => {
      archive = data;
      if(status) status.hidden = true;
      updateRatingStars();
      render();
    })
    .catch(() => {
      if(status) status.textContent = 'ERROR';
    });

  ratingButtons.forEach(button => {
    button.setAttribute('draggable', 'false');
    button.addEventListener('click', event => {
      event.preventDefault();
    });
    button.addEventListener('contextmenu', blockNativeSelection);
    button.addEventListener('dragstart', blockNativeSelection);
    button.addEventListener('selectstart', blockNativeSelection);
  });

  if(ratingStars){
    ratingStars.setAttribute('draggable', 'false');
    ratingStars.addEventListener('contextmenu', blockNativeSelection);
    ratingStars.addEventListener('dragstart', blockNativeSelection);
    ratingStars.addEventListener('selectstart', blockNativeSelection);
    ratingStars.addEventListener('touchstart', hidePreview, { passive:true });
    ratingStars.addEventListener('pointerdown', event => {
      event.preventDefault();
      hidePreview();
      ratingDrag = true;
      ratingStars.setPointerCapture(event.pointerId);
      setRatingFilter(ratingFromPointer(event));
    });
    ratingStars.addEventListener('pointermove', event => {
      if(ratingDrag){
        event.preventDefault();
        scrubRating(event);
      }
    });
    ratingStars.addEventListener('pointerup', event => {
      event.preventDefault();
      ratingDrag = false;
      ratingStars.releasePointerCapture(event.pointerId);
    });
    ratingStars.addEventListener('pointercancel', () => {
      ratingDrag = false;
    });
  }

  board.addEventListener('pointerdown', beginTouchSelect);
  board.addEventListener('pointermove', moveTouchSelect);
  board.addEventListener('pointerup', event => endTouchSelect(event, true));
  board.addEventListener('pointercancel', event => endTouchSelect(event, false));
  board.addEventListener('touchstart', beginTouchFallback, { passive:false });
  board.addEventListener('touchmove', moveTouchFallback, { passive:false });
  board.addEventListener('touchend', event => endTouchFallback(event, true), { passive:false });
  board.addEventListener('touchcancel', event => endTouchFallback(event, false), { passive:false });

  window.addEventListener('resize', () => {
    render();
    if(activeItem) syncReadoutMarquee();
  });
  window.addEventListener('pagehide', hidePreview);
  window.addEventListener('beforeunload', hidePreview);
  document.addEventListener('visibilitychange', () => {
    if(document.hidden) hidePreview();
  });
}
