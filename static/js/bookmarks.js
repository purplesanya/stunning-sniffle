const BOOKMARKS_KEY = "flibustaBookmarks";
const bookmarkRoot = document.querySelector(".bookmark-root");
const bookmarkList = document.getElementById("bookmarkList");
const bookmarkEmpty = document.getElementById("bookmarkEmpty");
const bookmarkCount = document.getElementById("bookmarkCount");

function bookmarkText(key) {
  return bookmarkRoot?.dataset[key] || "";
}

function readBookmarks() {
  try {
    const parsed = JSON.parse(localStorage.getItem(BOOKMARKS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeBookmarks(bookmarks) {
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
}

function findBookmark(bookId) {
  return readBookmarks().find((bookmark) => bookmark.bookId === bookId);
}

function bookmarkFromButton(button) {
  return {
    bookId: button.dataset.bookId || "",
    title: button.dataset.title || "",
    author: button.dataset.author || "",
    authorId: button.dataset.authorId || "",
    url: button.dataset.url || "",
    savedAt: new Date().toISOString(),
  };
}

function setButtonState(button, isBookmarked) {
  button.classList.toggle("saved", isBookmarked);
  button.setAttribute("aria-pressed", isBookmarked ? "true" : "false");
  button.textContent = isBookmarked ? bookmarkText("bookmarked") : bookmarkText("bookmark");
}

function refreshBookmarkButtons() {
  const savedIds = new Set(readBookmarks().map((bookmark) => bookmark.bookId));
  document.querySelectorAll("[data-bookmark-toggle]").forEach((button) => {
    setButtonState(button, savedIds.has(button.dataset.bookId || ""));
  });
}

function toggleBookmark(button) {
  const bookmark = bookmarkFromButton(button);
  if (!bookmark.bookId || !bookmark.title) return;

  const bookmarks = readBookmarks();
  const existingIndex = bookmarks.findIndex((item) => item.bookId === bookmark.bookId);
  if (existingIndex >= 0) {
    bookmarks.splice(existingIndex, 1);
  } else {
    bookmarks.unshift(bookmark);
  }
  writeBookmarks(bookmarks);
  refreshBookmarkButtons();
  renderBookmarkPage();
}

function buildBookmarkCard(bookmark) {
  const article = document.createElement("article");
  article.className = "book-result recommendation-card";

  const copy = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = bookmark.title;
  copy.appendChild(title);

  if (bookmark.authorId) {
    const author = document.createElement("a");
    author.className = "muted-link";
    author.href = `/books/${encodeURIComponent(bookmark.authorId)}?lang=${document.documentElement.lang || "en"}`;
    author.textContent = bookmark.author || bookmarkText("unknownAuthor");
    copy.appendChild(author);
  } else {
    const author = document.createElement("span");
    author.className = "muted-text";
    author.textContent = bookmark.author || bookmarkText("unknownAuthor");
    copy.appendChild(author);
  }

  const description = document.createElement("p");
  description.className = "book-description";
  description.dataset.bookId = bookmark.bookId;
  description.textContent = bookmarkText("loadingDescription");
  copy.appendChild(description);

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "bookmark-button saved";
  removeButton.textContent = bookmarkText("removeBookmark");
  removeButton.addEventListener("click", () => {
    writeBookmarks(readBookmarks().filter((item) => item.bookId !== bookmark.bookId));
    refreshBookmarkButtons();
    renderBookmarkPage();
  });

  const downloads = document.createElement("div");
  downloads.className = "inline-downloads";
  downloads.dataset.bookId = bookmark.bookId;
  downloads.dataset.title = bookmark.title;
  const loading = document.createElement("span");
  loading.className = "download-loading";
  loading.textContent = bookmarkText("loadingDescription");
  downloads.appendChild(loading);

  actions.append(removeButton, downloads);
  article.append(copy, actions);
  return article;
}

function renderBookmarkPage() {
  if (!bookmarkList) return;

  const bookmarks = readBookmarks();
  bookmarkList.replaceChildren(...bookmarks.map(buildBookmarkCard));
  if (bookmarkCount) bookmarkCount.textContent = String(bookmarks.length);
  if (bookmarkEmpty) bookmarkEmpty.hidden = bookmarks.length !== 0;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-bookmark-toggle]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  toggleBookmark(button);
});

refreshBookmarkButtons();
renderBookmarkPage();
