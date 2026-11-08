const $ = id => document.getElementById(id);
let books = [], previousFocus = null, starred = new Set();
const list = value => Array.isArray(value) ? value : [];
const count = value => Number.isInteger(value) && value >= 0;
const STAR_KEY = 'bokhyllan-starred-books';
function safeUrl(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null; } catch { return null; }
}
function loadStars() {
  try { starred = new Set(JSON.parse(localStorage.getItem(STAR_KEY) || '[]')); } catch { starred = new Set(); }
}
function saveStars() { localStorage.setItem(STAR_KEY, JSON.stringify([...starred])); }
function image(book) {
  const wrap = document.createElement('div'); wrap.className = 'cover-wrap';
  const fallback = () => { wrap.replaceChildren(); const text = document.createElement('span'); text.className = 'cover-fallback'; text.textContent = book.title + ' — cover unavailable'; wrap.append(text); };
  const url = safeUrl(book.cover_url);
  if (!url) { fallback(); return wrap; }
  const img = document.createElement('img'); img.src = url; img.alt = 'Cover of ' + book.title; img.loading = 'lazy'; img.onerror = fallback; wrap.append(img); return wrap;
}
function availability(book) {
  if ($('branch').value) {
    const holding = list(book.holdings).find(h => h.branch === $('branch').value);
    return holding && count(holding.available_copies) ? holding.available_copies : null;
  }
  return count(book.available_copies) ? book.available_copies : null;
}
function rating(book) {
  const average = Number(book.openlibrary_rating_average);
  const reviews = Number(book.openlibrary_rating_count);
  return Number.isFinite(average) && average > 0 && Number.isFinite(reviews) && reviews > 0 ? { average, reviews } : null;
}
function similarity(candidate, starredBook) {
  if (!starredBook || candidate.title_id === starredBook.title_id) return { score: 0, reasons: [] };
  const reasons = [];
  let score = 0;
  const candidateGenres = new Set(list(candidate.genres).map(v => v.toLocaleLowerCase()));
  const starredGenres = new Set(list(starredBook.genres).map(v => v.toLocaleLowerCase()));
  const sharedGenres = [...candidateGenres].filter(value => starredGenres.has(value));
  if (sharedGenres.length) { score += 2 * sharedGenres.length; reasons.push(sharedGenres.join(', ') + ' genres'); }
  const candidateSubjects = new Set(list(candidate.subjects).map(v => v.toLocaleLowerCase()));
  const starredSubjects = new Set(list(starredBook.subjects).map(v => v.toLocaleLowerCase()));
  const sharedSubjects = [...candidateSubjects].filter(value => starredSubjects.has(value));
  if (sharedSubjects.length) { score += 1.5 * Math.min(sharedSubjects.length, 4); reasons.push(sharedSubjects.slice(0, 3).join(', ')); }
  if (candidate.author && candidate.author === starredBook.author) { score += 1; reasons.push('same author'); }
  if (candidate.language && candidate.language === starredBook.language) { score += 0.75; reasons.push(candidate.language + ' language'); }
  const candidateYear = Number(candidate.published_year), starredYear = Number(starredBook.published_year);
  if (Number.isFinite(candidateYear) && Number.isFinite(starredYear)) {
    const distance = Math.abs(candidateYear - starredYear);
    if (distance <= 10) { score += 0.5; reasons.push('similar publication era'); }
  }
  const candidateRating = rating(candidate), starredRating = rating(starredBook);
  if (candidateRating && starredRating && candidateRating.average >= 4 && starredRating.average >= 4) { score += 0.25; reasons.push('highly rated'); }
  return { score, reasons: [...new Set(reasons)].slice(0, 3) };
}
function recommendations(limit = 12) {
  const seeds = books.filter(book => starred.has(String(book.title_id)));
  if (!seeds.length) return [];
  const scores = new Map();
  for (const candidate of books) {
    if (starred.has(String(candidate.title_id))) continue;
    let total = 0;
    const reasons = [];
    for (const seed of seeds) {
      const result = similarity(candidate, seed);
      total += result.score;
      reasons.push(...result.reasons);
    }
    if (total > 0) scores.set(candidate.title_id, { book: candidate, score: total, reasons: [...new Set(reasons)].slice(0, 3) });
  }
  return [...scores.values()].sort((a,b) => b.score - a.score || (rating(b.book)?.average || 0) - (rating(a.book)?.average || 0)).slice(0, limit);
}
function filtered() {
  const term = $('search').value.trim().toLocaleLowerCase();
  const result = books.filter(b => {
    const text = [b.title,b.author,b.isbn,...list(b.isbns),b.description,...list(b.subjects),...list(b.genres)].join(' ').toLocaleLowerCase();
    return (!term || text.includes(term)) && (!$('branch').value || list(b.holdings).some(h => h.branch === $('branch').value)) && (!$('language').value || b.language === $('language').value) && (!$('genre').value || list(b.genres).includes($('genre').value)) && (!$('available-only').checked || availability(b) > 0) && (!$('recent-only').checked || b.is_recent_release === true) && (!$('starred-only').checked || starred.has(String(b.title_id)));
  });
  const sort = $('sort').value;
  if (sort === 'rating') result.sort((a,b) => (rating(b)?.average || 0) - (rating(a)?.average || 0) || (rating(b)?.reviews || 0) - (rating(a)?.reviews || 0));
  if (sort === 'recent') result.sort((a,b) => (b.published_year || 0) - (a.published_year || 0));
  return result;
}
function starButton(book) {
  const id = String(book.title_id);
  const button = document.createElement('button'); button.type = 'button'; button.className = 'star-toggle' + (starred.has(id) ? ' active' : '');
  button.setAttribute('aria-pressed', String(starred.has(id)));
  button.setAttribute('aria-label', (starred.has(id) ? 'Remove star from ' : 'Star ') + book.title);
  button.textContent = starred.has(id) ? '★' : '☆';
  button.onclick = event => { event.stopPropagation(); toggleStar(book); };
  return button;
}
function toggleStar(book) {
  const id = String(book.title_id);
  starred.has(id) ? starred.delete(id) : starred.add(id);
  saveStars(); render();
  if (!$('book-modal').hidden && currentModalBook?.title_id === book.title_id) updateModalStar(book);
}
let currentModalBook = null;
function card(book) {
  const button = document.createElement('button'); button.className = 'book-card'; button.type = 'button'; button.setAttribute('aria-label','Details for ' + book.title);
  const cover = image(book), n = availability(book), badge = document.createElement('span');
  badge.className = 'badge ' + (n === null ? 'unknown' : n > 0 ? 'available' : 'waiting');
  badge.textContent = n === null ? 'Availability unknown' : n > 0 ? n + ' available' : 'None available'; cover.append(badge);
  if (book.is_recent_release) { const recent = document.createElement('span'); recent.className = 'badge recent'; recent.textContent = 'New release'; cover.append(recent); }
  cover.append(starButton(book));
  const meta = document.createElement('div'); meta.className = 'book-meta';
  const title = document.createElement('h3'); title.className = 'book-title'; title.textContent = book.title;
  const author = document.createElement('span'); author.className = 'book-author'; author.textContent = [book.author,book.language,book.published_year].filter(Boolean).join(' · ');
  meta.append(title,author);
  const score = rating(book);
  if (score) { const ratingLine = document.createElement('span'); ratingLine.className = 'rating'; ratingLine.textContent = '★ ' + score.average.toFixed(1) + ' · ' + score.reviews.toLocaleString('en-US') + ' Open Library ratings'; meta.append(ratingLine); }
  button.append(cover,meta); button.onclick = () => openModal(book); return button;
}
function recommendationCard(item) {
  const card = card(item.book); card.classList.add('recommendation');
  if (item.reasons.length) { const reason = document.createElement('span'); reason.className = 'recommendation-reason'; reason.textContent = 'Because: ' + item.reasons.join(' · '); card.querySelector('.book-meta').append(reason); }
  return card;
}
function render() {
  const found = filtered(); $('shelves').replaceChildren(); $('empty-state').hidden = found.length > 0;
  const groups = [['Available in this selection',found.filter(b => availability(b) > 0)],['All matching books',found]];
  for (const [name,items] of groups) {
    if (!items.length) continue;
    const section = document.createElement('section'); section.className = 'shelf';
    const heading = document.createElement('h2'); heading.textContent = name + ' (' + items.length + ')';
    const row = document.createElement('div'); row.className = 'shelf-row'; items.forEach(b => row.append(card(b))); section.append(heading,row); $('shelves').append(section);
  }
  const suggestions = recommendations();
  const recommendationArea = $('recommendations'); recommendationArea.replaceChildren();
  if (suggestions.length) {
    const section = document.createElement('section'); section.className = 'shelf recommendations-shelf';
    const heading = document.createElement('h2'); heading.textContent = 'Because you starred… (' + suggestions.length + ')';
    const row = document.createElement('div'); row.className = 'shelf-row'; suggestions.forEach(item => row.append(recommendationCard(item))); section.append(heading,row); recommendationArea.append(section);
  }
}
function fillSelect(id, values) {
  [...new Set(values.filter(v => typeof v === 'string' && v))].sort((a,b) => a.localeCompare(b)).forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = value; $(id).append(option); });
}
function date(value) { const d = new Date(value); return value && !Number.isNaN(d.valueOf()) ? d.toLocaleString() : 'Not recorded'; }
function updateModalStar(book) {
  const id = String(book.title_id), active = starred.has(id);
  $('modal-star').classList.toggle('active', active);
  $('modal-star').textContent = active ? '★ Starred' : '☆ Star this book';
  $('modal-star').setAttribute('aria-pressed', String(active));
}
function openModal(book) {
  currentModalBook = book; previousFocus = document.activeElement; $('modal-media').replaceChildren(image(book));
  $('modal-title').textContent = book.title; $('modal-author').textContent = book.author || '';
  $('modal-genre').textContent = list(book.genres).join(' · ');
  $('modal-meta').textContent = [book.language,book.format_label,book.published_year,book.isbn && 'ISBN ' + book.isbn,book.page_count,book.first_published_year && 'First published ' + book.first_published_year].filter(Boolean).join(' · ');
  $('modal-description').textContent = book.description || 'No description supplied.';
  const quality = $('modal-quality'); quality.replaceChildren();
  const score = rating(book);
  if (score) { const item = document.createElement('span'); item.className = 'quality-item'; item.textContent = '★ ' + score.average.toFixed(1) + '/5 · ' + score.reviews.toLocaleString('en-US') + ' Open Library ratings'; quality.append(item); }
  if (book.is_recent_release) { const item = document.createElement('span'); item.className = 'quality-item recent'; item.textContent = 'Recent release'; quality.append(item); }
  if (!quality.children.length) quality.hidden = true; else quality.hidden = false;
  const area = $('modal-availability'); area.replaceChildren();
  for (const h of list(book.holdings)) { const tag = document.createElement('span'); tag.className = count(h.available_copies) && h.available_copies > 0 ? 'yes' : 'no'; tag.textContent = h.branch + ': ' + (count(h.available_copies) ? h.available_copies + ' available' : 'availability unknown') + (count(h.total_copies) ? ' / ' + h.total_copies + ' copies' : ''); area.append(tag); }
  if (!list(book.holdings).length) area.textContent = 'Branch availability not supplied.';
  $('modal-updated').textContent = 'Availability checked: ' + date(book.availability_checked_at) + (count(book.reservation_count) ? ' · Reservations: ' + book.reservation_count : '');
  const url = safeUrl(book.reservation_url); $('modal-reserve').hidden = !url; if (url) $('modal-reserve').href = url;
  updateModalStar(book);
  $('book-modal').hidden = false; document.body.style.overflow = 'hidden'; $('book-modal').querySelector('.modal-close').focus();
}
function closeModal() { $('book-modal').hidden = true; document.body.style.overflow = ''; if (previousFocus && previousFocus.isConnected) previousFocus.focus(); }
document.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click',closeModal));
document.addEventListener('keydown',event => {
  if ($('book-modal').hidden) return;
  if (event.key === 'Escape') closeModal();
  if (event.key === 'Tab') {
    const items = [...$('book-modal').querySelectorAll('button,a[href]')].filter(el => !el.hidden);
    const first = items[0], last = items[items.length-1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
$('modal-star').addEventListener('click',() => currentModalBook && toggleStar(currentModalBook));
$('clear-stars').addEventListener('click',() => { starred.clear(); saveStars(); render(); });
$('search').addEventListener('input',render);
['branch','language','genre','sort','available-only','recent-only','starred-only'].forEach(id => $(id).addEventListener('change',render));
async function load() {
  try {
    const response = await fetch('data/books.json',{cache:'no-cache'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    if (!Array.isArray(data) || !data.every(b => b && typeof b.title === 'string' && b.title_id)) throw new Error('Invalid books.json schema');
    books = data;
    loadStars();
    fillSelect('branch',books.flatMap(b => list(b.holdings).map(h => h.branch)));
    fillSelect('language',books.map(b => b.language)); fillSelect('genre',books.flatMap(b => list(b.genres)));
    const timestamps = books.map(b => b.availability_checked_at || b.updated_at).filter(Boolean).sort();
    const rated = books.filter(b => rating(b)).length;
    const recent = books.filter(b => b.is_recent_release).length;
    $('data-status').textContent = books.length + ' imported catalogue records · ' + rated + ' with Open Library ratings · ' + recent + ' recent releases · Latest record check: ' + date(timestamps[timestamps.length-1]);
    render();
  } catch (error) {
    $('data-status').textContent = 'Catalogue data unavailable. Run Update library data with publish enabled to create data/books.json. No mock data is being displayed.';
    $('empty-state').textContent = 'Could not load catalogue: ' + error.message; $('empty-state').hidden = false;
  }
}
load();
