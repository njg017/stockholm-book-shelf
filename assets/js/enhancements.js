(() => {
  const baseFiltered = filtered;
  const normalize = value => String(value || '').toLocaleLowerCase().trim();
  function score(book, term) {
    const title = normalize(book.title), author = normalize(book.author);
    const isbns = [book.isbn, ...list(book.isbns)].map(normalize);
    if (isbns.includes(term)) return 120;
    if (title === term) return 110;
    if (author === term) return 100;
    if (title.startsWith(term)) return 90;
    if (title.includes(term)) return 80;
    if (author.includes(term)) return 70;
    return 10;
  }
  filtered = function() {
    const result = baseFiltered();
    const term = normalize($('search').value);
    if (term && $('sort').value === 'relevance') result.sort((a,b) => score(b,term)-score(a,term));
    return result;
  };
  function sync() {
    const url = new URL(location.href);
    for (const [key,id] of [['q','search'],['branch','branch'],['genre','genre'],['sort','sort']]) {
      const value = $(id).value;
      if (value && !(key === 'sort' && value === 'relevance')) url.searchParams.set(key,value);
      else url.searchParams.delete(key);
    }
    url.searchParams.delete('languages');
    const languages = selectedLanguages();
    if (!languages.length) url.searchParams.set('languages','');
    else for (const language of languages) url.searchParams.append('languages',language);
    for (const [key,id] of [['available','available-only'],['recent','recent-only'],['starred','starred-only']]) {
      if ($(id).checked) url.searchParams.set(key,'1'); else url.searchParams.delete(key);
    }
    history.replaceState(null,'',url);
  }
  function restore() {
    const params = new URLSearchParams(location.search);
    for (const [key,id,fallback] of [['q','search',''],['branch','branch',''],['genre','genre',''],['sort','sort','relevance']]) {
      const element = $(id), value = params.get(key) || fallback;
      element.value = value;
      if (element.tagName === 'SELECT' && element.selectedIndex < 0) element.value = fallback;
    }
    const languages = params.has('languages') ? params.getAll('languages') : DEFAULT_LANGUAGES;
    document.querySelectorAll('.language-option').forEach(option => option.checked = languages.includes(option.value));
    for (const [key,id] of [['available','available-only'],['recent','recent-only'],['starred','starred-only']]) $(id).checked = params.get(key) === '1';
    updateLanguageLabel(); render();
  }
  let timer;
  $('search').addEventListener('input', event => {
    event.stopImmediatePropagation(); clearTimeout(timer);
    timer = setTimeout(() => { sync(); render(); },250);
  },true);
  document.querySelector('.filter-bar').addEventListener('change',sync);
  window.addEventListener('popstate',() => { clearTimeout(timer); restore(); });
  const link = document.createElement('a'); link.href = 'dashboard.html'; link.className = 'button subtle'; link.textContent = 'Dashboard';
  document.querySelector('.header-inner').append(link);
  async function chunks() {
    try {
      const response = await fetch('data/catalogue/index.json',{cache:'no-cache'});
      if (!response.ok) return;
      const index = await response.json();
      if (!Array.isArray(index.items)) return;
      const records = new Map(books.map(book => [String(book.title_id),book]));
      for (const item of index.items) if (!records.has(String(item.title_id))) records.set(String(item.title_id),item);
      books = [...records.values()]; render();
      for (let n=0; n<index.chunk_count; n++) {
        const part = await fetch('data/catalogue/chunks/chunk-'+String(n).padStart(4,'0')+'.json',{cache:'no-cache'});
        if (!part.ok) break;
        const data = await part.json();
        if (!Array.isArray(data)) break;
        for (const book of data) records.set(String(book.title_id),book);
        books = [...records.values()]; render();
      }
    } catch { /* Existing catalogue remains usable. */ }
  }
  let attempts = 0;
  const ready = setInterval(() => {
    if (document.querySelector('.language-option')) { clearInterval(ready); restore(); chunks(); }
    else if (++attempts >= 300) clearInterval(ready);
  },100);
})();