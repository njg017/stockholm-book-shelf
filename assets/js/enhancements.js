// Load after app.js. Existing catalogue remains the compatibility fallback.
const PAGE_SIZE = 48;
let visibleLimit = PAGE_SIZE;
const filterIds = ['search','branch','language','genre','sort','available-only','recent-only','starred-only'];
const params = new URLSearchParams(location.search);
function rememberedBranch() { try { return localStorage.getItem('bokhyllan-branch') || ''; } catch { return ''; } }
function restoreFilters() {
  for (const id of filterIds) {
    const el = $(id), value = params.get(id);
    if (el.type === 'checkbox') el.checked = value === '1';
    else if (value !== null) el.value = value;
  }
  if (!params.has('branch')) $('branch').value = rememberedBranch();
}
function storeFilters() {
  const url = new URL(location.href);
  for (const id of filterIds) {
    const el = $(id), value = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
    if (value && !(id === 'sort' && value === 'relevance')) url.searchParams.set(id,value);
    else url.searchParams.delete(id);
  }
  history.replaceState(null,'',url);
  try { localStorage.setItem('bokhyllan-branch',$('branch').value); } catch {}
}
// Replace the original function, whose local variable shadows card().
recommendationCard = function(item) {
  const element = card(item.book);
  element.classList.add('recommendation');
  const reason = document.createElement('span');
  reason.className = 'recommendation-reason';
  reason.textContent = 'Because: ' + item.reasons.join(' · ');
  element.querySelector('.book-meta').append(reason);
  return element;
};
const originalSaveStars = saveStars;
saveStars = function() { try { originalSaveStars(); } catch { freshness.textContent = 'Browser storage unavailable: stars will last only for this visit.'; } };
const freshness = document.createElement('p');
freshness.id = 'data-freshness'; freshness.className = 'status'; freshness.setAttribute('role','status');
$('data-status').after(freshness);
const more = document.createElement('button');
more.type = 'button'; more.className = 'button'; more.textContent = 'Show more books';
$('shelves').after(more);
more.onclick = () => { visibleLimit += PAGE_SIZE; render(); };
const originalFiltered = filtered;
filtered = function() { return originalFiltered().slice(0,visibleLimit); };
const originalRender = render;
let restored = false;
render = function() {
  if (!restored && books.length) { restored = true; restoreFilters(); refreshSnapshot(); }
  originalRender();
  const total = originalFiltered().length;
  more.hidden = visibleLimit >= total;
  more.textContent = 'Show more books (' + Math.min(visibleLimit,total) + ' of ' + total + ')';
  // Recommendations must obey active search/availability filters, but not starred-only.
  const eligible = new Set(originalFiltered().map(b => String(b.title_id)));
  if ($('starred-only').checked) $('recommendations').replaceChildren();
  else {
    const candidates = recommendations().filter(item => eligible.has(String(item.book.title_id)));
    $('recommendations').replaceChildren();
    if (candidates.length) {
      const heading = document.createElement('h2'); heading.textContent = 'Because you starred…';
      const row = document.createElement('div'); row.className = 'shelf-row';
      candidates.forEach(item => row.append(recommendationCard(item)));
      $('recommendations').append(heading,row);
    }
  }
};
for (const id of filterIds) {
  $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { visibleLimit = PAGE_SIZE; storeFilters(); render(); });
}
async function refreshSnapshot() {
  try {
    const response = await fetch('data/availability.json',{cache:'no-cache'});
    if (!response.ok) throw new Error('Snapshot unavailable');
    const snapshot = await response.json();
    for (const book of books) {
      const value = snapshot[String(book.title_id)];
      if (value && typeof value === 'object' && value.availability_checked_at && (!book.availability_checked_at || Date.parse(value.availability_checked_at) >= Date.parse(book.availability_checked_at))) Object.assign(book,value);
    }
    const now = Date.now();
    const checked = books.filter(b => Number.isFinite(Date.parse(b.availability_checked_at)));
    const fresh = checked.filter(b => now - Date.parse(b.availability_checked_at) <= 86400000).length;
    freshness.textContent = books.length + ' catalogue records · ' + checked.length + ' with availability timestamps · ' + fresh + ' checked within 24 hours. Availability is a snapshot, not live stock.';
    render();
  } catch { freshness.textContent = 'Separate availability snapshot unavailable. Showing the timestamps in the catalogue records.'; }
}
