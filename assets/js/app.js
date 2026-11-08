const SHELVES = [
  { id: "available-now", title: "Available now" },
  { id: "new", title: "New & noteworthy" },
  { id: "fiction", title: "Fiction to get lost in" },
  { id: "crime", title: "Crime & thrillers" },
  { id: "scifi", title: "Sci-fi & fantasy" },
  { id: "children", title: "For younger readers" },
  { id: "nonfiction", title: "Ideas & real life" }
];

const GENRE_LABELS = {
  fiction: "Fiction",
  crime: "Crime",
  scifi: "Sci-fi & fantasy",
  children: "Children",
  nonfiction: "Non-fiction"
};

let books = [];
let activeGenre = "all";
let activeBranch = "all";
let activeShelf = "all";

const shelfElement = document.getElementById("shelves");
const emptyState = document.getElementById("empty-state");
const searchInput = document.getElementById("search");

function coverUrl(isbn) {
  return `https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg`;
}

function availabilityFor(book, branch) {
  const branches = book.branches || [];
  if (branch === "all") {
    return branches.some((item) => item.available);
  }
  return branches.some((item) => item.name === branch && item.available);
}

function matchesFilters(book) {
  const genreMatch = activeGenre === "all" || book.genres.includes(activeGenre);
  const branchMatch = activeBranch === "all" || book.branches.some((item) => item.name === activeBranch);
  const shelfMatch = activeShelf === "all" || book.shelves.includes(activeShelf);
  return genreMatch && branchMatch && shelfMatch;
}

function matchesSearch(book, term) {
  if (!term) return true;
  const haystack = [
    book.title,
    book.author,
    book.description,
    ...book.genres,
    ...book.subjects
  ].join(" ").toLowerCase();
  return haystack.includes(term);
}

function createBookCard(book) {
  const button = document.createElement("button");
  button.className = "book-card";
  button.type = "button";
  button.setAttribute("aria-label", `Show details for ${book.title}`);

  const available = availabilityFor(book, activeBranch);
  const cover = document.createElement("div");
  cover.className = "cover-wrap";

  const image = document.createElement("img");
  image.src = coverUrl(book.isbn);
  image.alt = `Cover of ${book.title}`;
  image.loading = "lazy";

  const badge = document.createElement("span");
  badge.className = `badge ${available ? "available" : "waiting"}`;
  badge.textContent = available ? "Available" : "Reserve";

  const meta = document.createElement("div");
  meta.className = "book-meta";
  meta.innerHTML = `<h3 class="book-title"></h3><span class="book-author"></span>`;
  meta.querySelector(".book-title").textContent = book.title;
  meta.querySelector(".book-author").textContent = book.author;

  cover.append(image, badge);
  button.append(cover, meta);
  button.addEventListener("click", () => openModal(book));
  return button;
}

function renderShelf(shelf) {
  const shelfBooks = books
    .filter((book) => book.shelves.includes(shelf.id))
    .filter(matchesFilters)
    .filter((book) => matchesSearch(book, searchInput.value.trim().toLowerCase()));

  if (!shelfBooks.length) return;

  const section = document.createElement("section");
  section.className = "shelf";

  const head = document.createElement("div");
  head.className = "shelf-head";
  head.innerHTML = `<h2></h2><span class="shelf-count"></span>`;
  head.querySelector("h2").textContent = shelf.title;
  head.querySelector(".shelf-count").textContent = `${shelfBooks.length} books`;

  const row = document.createElement("div");
  row.className = "shelf-row";
  shelfBooks.forEach((book) => row.append(createBookCard(book)));

  section.append(head, row);
  shelfElement.append(section);
}

function render() {
  shelfElement.replaceChildren();
  SHELVES.forEach(renderShelf);
  emptyState.hidden = shelfElement.children.length > 0;
}

function openModal(book) {
  document.getElementById("modal-cover").src = coverUrl(book.isbn);
  document.getElementById("modal-cover").alt = `Cover of ${book.title}`;
  document.getElementById("modal-title").textContent = book.title;
  document.getElementById("modal-author").textContent = book.author;
  document.getElementById("modal-genre").textContent = GENRE_LABELS[book.genres[0]] || "Book";
  document.getElementById("modal-rating").textContent = `★ ${book.rating.toFixed(1)}`;
  document.getElementById("modal-year").textContent = book.year;
  document.getElementById("modal-description").textContent = book.description;

  const availability = document.getElementById("modal-availability");
  availability.replaceChildren();

  book.branches.forEach((branch) => {
    const tag = document.createElement("span");
    tag.className = branch.available ? "yes" : "no";
    tag.textContent = branch.available
      ? `Available · ${branch.name.replace(" bibliotek", "")}`
      : `Waitlist · ${branch.name.replace(" bibliotek", "")}`;
    availability.append(tag);
  });

  const reserve = document.getElementById("modal-reserve");
  reserve.href = book.reservation_url;
  document.getElementById("book-modal").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeModal() {
  document.getElementById("book-modal").hidden = true;
  document.body.style.overflow = "";
}

function bindChips(selector, callback) {
  document.querySelectorAll(selector).forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(selector).forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      callback(chip.dataset);
      render();
    });
  });
}

async function loadMockBooks() {
  const response = await fetch("data/mock-books.json");
  books = await response.json();
  render();
}

bindChips("[data-genre]", (dataset) => {
  activeGenre = dataset.genre;
});

bindChips("[data-branch]", (dataset) => {
  activeBranch = dataset.branch;
});

searchInput.addEventListener("input", render);

document.querySelectorAll("[data-close]").forEach((element) => {
  element.addEventListener("click", closeModal);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

loadMockBooks();
