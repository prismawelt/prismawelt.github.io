
document.addEventListener('DOMContentLoaded', () => {
  initMobileMenu();
  document.querySelectorAll('[data-archive-page]').forEach(initArchive);
  document.querySelectorAll('.detail-page').forEach(initDetailTitle);
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
