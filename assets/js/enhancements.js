// Progressive catalogue loading: index first, then metadata chunks.
const CHUNK_SIZE = 200;
let chunkCursor = 0, catalogueIndex = null;
async function loadProgressiveCatalogue() {
  try {
    const response = await fetch('data/catalogue/index.json',{cache:'no-cache'});
    if (!response.ok) return;
    catalogueIndex = await response.json();
    if (!catalogueIndex.items?.length) return;
    const existing = new Map(books.map(book => [String(book.title_id), book]));
    for (const item of catalogueIndex.items) {
      const current = existing.get(String(item.title_id));
      if (!current) existing.set(String(item.title_id), item);
    }
    books = [...existing.values()];
    render();
    while (chunkCursor < catalogueIndex.chunk_count) {
      const chunkResponse = await fetch(`data/catalogue/chunks/chunk-${String(chunkCursor).padStart(4,'0')}.json`,{cache:'no-cache'});
      if (!chunkResponse.ok) break;
      const chunk = await chunkResponse.json();
      const byId = new Map(books.map(book => [String(book.title_id), book]));
      for (const book of chunk) {
        const current = byId.get(String(book.title_id));
        if (current && current.description) Object.assign(current, book, {description: current.description});
        else byId.set(String(book.title_id), book);
      }
      books = [...byId.values()];
      chunkCursor++;
      render();
    }
  } catch { /* Keep compatibility fallback loaded from books.json. */ }
}
window.addEventListener('load',() => setTimeout(loadProgressiveCatalogue,100));
