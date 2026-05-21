const detailRoot = document.querySelector(".book-detail-root");
const detailCache = new Map();
const formatOrder = ["epub", "fb2", "mobi", "pdf", "docx"];

function detailText(key) {
  return detailRoot?.dataset[key] || "";
}

function escapedBookId(bookId) {
  return window.CSS?.escape ? CSS.escape(bookId) : String(bookId).replace(/"/g, '\\"');
}

async function fetchBookDetails(bookId) {
  if (detailCache.has(bookId)) return detailCache.get(bookId);

  const promise = fetch(`/book-details/${encodeURIComponent(bookId)}`)
    .then((response) => {
      if (!response.ok) throw new Error("Details unavailable");
      return response.json();
    })
    .catch(() => ({
      book_id: bookId,
      description: "",
      links: {},
      error: true,
    }));

  detailCache.set(bookId, promise);
  return promise;
}

function updateDescriptions(bookId, details) {
  const description = details.description || detailText("noBookDescription") || detailText("detailsFailed");
  document.querySelectorAll(`.book-description[data-book-id="${escapedBookId(bookId)}"]`).forEach((node) => {
    node.dataset.fullDescription = description;
    node.textContent = node.dataset.modalOnly === "true" ? compactPreview(description) : description;
    node.classList.toggle("muted-empty", !details.description);
    if (node.dataset.modalOnly !== "true") {
      prepareExpandable(node, true);
    }
  });
}

function compactPreview(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= 180) return normalized;
  return `${normalized.slice(0, 180).trim()}...`;
}

function buildDownloadLink(bookId, title, format) {
  const link = document.createElement("a");
  link.className = "format-link";
  link.href = `/download-book/${encodeURIComponent(bookId)}/${encodeURIComponent(format)}?${new URLSearchParams({ title })}`;
  link.textContent = format.toUpperCase();
  return link;
}

function updateDownloads(bookId, details) {
  document.querySelectorAll(`.inline-downloads[data-book-id="${escapedBookId(bookId)}"]`).forEach((node) => {
    const title = node.dataset.title || details.title || "book";
    const links = details.links || {};
    const formats = formatOrder.filter((format) => links[format]);
    node.replaceChildren();

    if (!formats.length) {
      const empty = document.createElement("span");
      empty.className = "download-loading";
      empty.textContent = details.error ? detailText("detailsFailed") : detailText("detailsFailed");
      node.appendChild(empty);
      return;
    }

    const label = document.createElement("span");
    label.className = "download-label";
    label.textContent = detailText("downloadFormats");
    node.append(label, ...formats.map((format) => buildDownloadLink(bookId, title, format)));
  });
}

async function hydrateBook(bookId) {
  const details = await fetchBookDetails(bookId);
  updateDescriptions(bookId, details);
  updateDownloads(bookId, details);
}

function ensureModal() {
  let modal = document.getElementById("bookDetailModal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "bookDetailModal";
  modal.className = "modal-backdrop";
  modal.hidden = true;
  modal.innerHTML = `
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="bookDetailTitle">
      <div class="detail-modal-header">
        <div>
          <p class="eyebrow">${detailText("bookDescription")}</p>
          <h2 id="bookDetailTitle"></h2>
        </div>
        <button type="button" class="modal-close" data-modal-close>${detailText("close")}</button>
      </div>
      <div class="detail-modal-body"></div>
    </section>
  `;
  document.body.appendChild(modal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-modal-close]")) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });
  return modal;
}

function closeModal() {
  const modal = document.getElementById("bookDetailModal");
  if (modal) modal.hidden = true;
  document.body.classList.remove("modal-open");
}

async function openDetails(button) {
  const bookId = button.dataset.bookId;
  if (!bookId) return;

  const modal = ensureModal();
  const title = button.dataset.title || "";
  modal.querySelector("#bookDetailTitle").textContent = title;
  modal.querySelector(".detail-modal-body").textContent = detailText("loadingDescription");
  modal.hidden = false;
  document.body.classList.add("modal-open");

  const details = await fetchBookDetails(bookId);
  const description = details.description || detailText("noBookDescription") || detailText("detailsFailed");
  modal.querySelector("#bookDetailTitle").textContent = details.title || title;
  modal.querySelector(".detail-modal-body").textContent = description;
}

function observeDetails() {
  const targets = [
    ...document.querySelectorAll(".book-description[data-book-id]"),
    ...document.querySelectorAll(".inline-downloads[data-book-id]"),
  ];
  if (!targets.length) return;

  if (!("IntersectionObserver" in window)) {
    [...new Set(targets.map((node) => node.dataset.bookId))].forEach(hydrateBook);
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const bookId = entry.target.dataset.bookId;
        observer.unobserve(entry.target);
        if (bookId) hydrateBook(bookId);
      });
    },
    { rootMargin: "240px 0px" },
  );

  targets.forEach((target) => observer.observe(target));
}

function prepareExpandable(node, force = false) {
  if (!node) return;
  if (force) {
    node.dataset.expandReady = "false";
    node.classList.remove("expanded", "collapsed");
    document.querySelectorAll(`[data-expand-target="${node.dataset.expandId || ""}"]`).forEach((button) => {
      button.remove();
    });
  }
  if (node.dataset.expandReady === "true") return;
  node.dataset.expandReady = "true";
  if (!node.dataset.expandId) {
    node.dataset.expandId = `expand-${Math.random().toString(36).slice(2)}`;
  }
  node.classList.add("collapsed");

  window.requestAnimationFrame(() => {
    if (node.scrollHeight <= node.clientHeight + 4) {
      node.classList.remove("collapsed");
      return;
    }
    if (document.querySelector(`[data-expand-target="${node.dataset.expandId}"]`)) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "expand-toggle";
    button.dataset.expandTarget = node.dataset.expandId;
    button.textContent = detailText("showMore");
    button.addEventListener("click", () => {
      const expanded = node.classList.toggle("expanded");
      node.classList.toggle("collapsed", !expanded);
      button.textContent = expanded ? detailText("showLess") : detailText("showMore");
    });
    node.insertAdjacentElement("afterend", button);
  });
}

document.querySelectorAll("[data-expandable]").forEach((node) => prepareExpandable(node));
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-details-button]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openDetails(button);
});
observeDetails();
