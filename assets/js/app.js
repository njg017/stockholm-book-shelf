const SHELF_TITLES = {
  "new": "Nya på biblioteket",
  "popular": "Populära just nu",
  "english-fiction": "Engelsk skönlitteratur",
  "swedish-fiction": "Svensk skönlitteratur",
  "crime": "Crime & thriller",
  "scifi-fantasy": "Sci-fi & fantasy",
  "children": "För barn & familjen"
};

let books = [];

function createCard(book) {
  const card = document.createElement("a");
  card.className = "book-card";
  card.href = book.library?.reservation_url || "#";
  card.target = "_blank";
  card.rel = "noopener";

  const image = document.createElement("img");
  image.src = book.cover_url || "";
  image.alt = `Cover of ${book.title}`;
  image.loading = "lazy";

  const caption = document.createElement("figcaption");
  caption.innerHTML = `<strong></strong><span></span>`;
  caption.querySelector("strong").textContent = book.title;
  caption.querySelector("span").textContent = book.author || "";

  card.append(image, caption);
  return card;
}

function renderShelf(shelfId, shelfBooks) {
  if (!shelfBooks.length) return;

  const section = document.createElement("section");
  section.className = "shelf";

  const heading = document.createElement("h2");
  heading.textContent = SHELF_TITLES[shelfId] || shelfId;

  const row = document.createElement("div");
  row.className = "shelf-row";
  shelfBooks.forEach((book) => row.append(createCard(book)));

  section.append(heading, row);
  document.getElementById("shelves").append(section);
}

function render(booksToShow) {
  const shelvesElement = document.getElementById("shelves");
  const emptyState = document.getElementById("empty-state");
  shelvesElement.replaceChildren();

  const grouped = {};
  booksToShow.forEach((book) => {
    (book.shelves || []).forEach((shelf) => {
      grouped[shelf] ||= [];
      grouped[shelf].push(book);
    });
  });

  Object.keys(SHELF_TITLES).forEach((shelfId) => renderShelf(shelfId, grouped[shelfId] || []));
  emptyState.hidden = booksToShow.length > 0;
}

function filterBooks(query) {
  const term = query.trim().toLowerCase();
  if (!term) return books;

  return books.filter((book) =>
    [book.title, book.author, ...(book.subjects || [])]
      .join(" ")
      .toLowerCase()
      .includes(term)
  );
}

async function loadBooks() {
  try {
    const response = await fetch("data/books.sample.json");
    books = await response.json();
    render(books);
  } catch {
    document.getElementById("empty-state").hidden = false;
  }
}

document.getElementById("search").addEventListener("input", (event) => {
  render(filterBooks(event.target.value));
});

loadBooks();
