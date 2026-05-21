const formatTabs = Array.from(document.querySelectorAll(".format-tab"));
const selectedFormat = document.getElementById("selectedFormat");
const bookList = document.getElementById("bookList");
const emptyState = document.getElementById("emptyState");
const selectedCount = document.getElementById("selectedCount");
const selectionLabel = document.getElementById("selectionLabel");
const bookFilter = document.getElementById("bookFilter");
const selectAllBtn = document.getElementById("selectAllBtn");
const deselectAllBtn = document.getElementById("deselectAllBtn");
const downloadForm = document.getElementById("downloadForm");
const downloadBtn = document.getElementById("downloadBtn");
const progressContainer = document.getElementById("progressContainer");
const progressText = document.getElementById("progressText");
const progressPercent = document.getElementById("progressPercent");
const progressBar = document.getElementById("progressBar");
const downloadSummary = document.getElementById("downloadSummary");
const formatSummary = document.getElementById("formatSummary");
const toastContainer = document.getElementById("toastContainer");
const libraryPanel = document.querySelector(".library-panel");

function text(key, replacements = {}) {
  const value = libraryPanel?.dataset[key] || "";
  return Object.entries(replacements).reduce(
    (message, [name, replacement]) => message.replace(`{${name}}`, replacement),
    value,
  );
}

function showToast(title, message, type = "success") {
  if (!toastContainer) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icon = document.createElement("div");
  icon.className = "toast-icon";
  icon.textContent = type === "success" ? "OK" : "!";

  const content = document.createElement("div");
  const titleEl = document.createElement("div");
  titleEl.className = "toast-title";
  titleEl.textContent = title;
  const messageEl = document.createElement("div");
  messageEl.className = "toast-message";
  messageEl.textContent = message;

  content.append(titleEl, messageEl);
  toast.append(icon, content);
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 4200);
}

function getCards() {
  return Array.from(bookList?.querySelectorAll(".book-item") || []);
}

function currentFormat() {
  return selectedFormat?.value || "epub";
}

function setFormat(format) {
  if (!selectedFormat) return;
  selectedFormat.value = format;
  formatTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.format === format);
  });
  applyFilters();
}

function isVisibleCard(card) {
  return !card.classList.contains("hidden");
}

function setCardSelected(card, selected) {
  card.classList.toggle("selected", selected);
  card.querySelector(".book-select-button")?.setAttribute("aria-pressed", selected ? "true" : "false");
}

function applyFilters() {
  const query = (bookFilter?.value || "").trim().toLocaleLowerCase();
  const format = currentFormat();
  let visibleCount = 0;

  getCards().forEach((card) => {
    const title = (card.dataset.title || "").toLocaleLowerCase();
    const formats = (card.dataset.formats || "").split(",");
    const visible = title.includes(query) && formats.includes(format);
    card.classList.toggle("hidden", !visible);
    if (!visible) {
      setCardSelected(card, false);
    } else {
      visibleCount += 1;
    }
  });

  if (emptyState) {
    emptyState.hidden = visibleCount !== 0;
  }
  updateCount();
}

function updateCount() {
  const count = getCards().filter((card) => card.classList.contains("selected")).length;
  if (selectedCount) selectedCount.textContent = String(count);
  if (selectionLabel) selectionLabel.textContent = count === 1 ? text("bookSelected") : text("booksSelected");
  if (downloadBtn) downloadBtn.disabled = count === 0;

  const format = currentFormat().toUpperCase();
  if (downloadSummary) {
    downloadSummary.textContent =
      count === 0 ? text("chooseBooks") : text("selectedCount", { count: String(count) });
  }
  if (formatSummary) {
    const output = count <= 1 ? text("singleOutput") : text("zipOutput");
    formatSummary.textContent = `${text("formatSelected", { format })}, ${output}`;
  }
}

function selectedDownloadPayload() {
  const format = currentFormat();
  const payload = {
    format,
    author_name: document.querySelector('input[name="author_name"]')?.value || "",
    book_titles: [],
    book_links: [],
  };

  getCards()
    .filter((card) => card.classList.contains("selected"))
    .forEach((card) => {
      const link = card.getAttribute(`data-link-${format}`);
      if (link) {
        payload.book_titles.push(card.dataset.title || "book");
        payload.book_links.push(link);
      }
    });

  return payload;
}

function setProgress(statusData) {
  const progress = Number(statusData.progress || 0);
  if (progressBar) progressBar.style.width = `${progress}%`;
  if (progressPercent) progressPercent.textContent = `${progress}%`;
  if (progressText) progressText.textContent = localizedStatusMessage(statusData.message);
}

function localizedStatusMessage(message) {
  if (!message) return text("processing");

  let match = message.match(/^Downloaded (\d+)\/(\d+)$/);
  if (match) {
    return text("downloaded", { done: match[1], total: match[2] });
  }

  match = message.match(/^Archiving (\d+)\/(\d+)$/);
  if (match) {
    return text("archiving", { done: match[1], total: match[2] });
  }

  if (message === "Download ready") return text("downloadReadyTitle");
  if (message === "Starting downloads") return text("startingDownload");
  return message;
}

async function pollJob(jobId) {
  const response = await fetch(`/job-status/${jobId}`);
  const statusData = await response.json();
  setProgress(statusData);

  if (statusData.status === "complete") {
    showToast(text("downloadReadyTitle"), text("downloadReadyMessage"));
    window.location.href = `/fetch/${jobId}/${statusData.download_token}`;
    if (downloadBtn) downloadBtn.disabled = false;
    window.setTimeout(() => {
      if (progressContainer) progressContainer.hidden = true;
      setProgress({ progress: 0, message: text("preparingDownload") });
    }, 2200);
    return;
  }

  if (statusData.status === "error") {
    if (progressContainer) progressContainer.hidden = true;
    if (downloadBtn) downloadBtn.disabled = false;
    showToast(text("downloadFailedTitle"), statusData.message || text("downloadFailedMessage"), "error");
    return;
  }

  window.setTimeout(() => pollJob(jobId), 1200);
}

formatTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (!tab.disabled && tab.dataset.format) {
      setFormat(tab.dataset.format);
    }
  });
});

bookFilter?.addEventListener("input", applyFilters);

selectAllBtn?.addEventListener("click", () => {
  getCards().filter(isVisibleCard).forEach((card) => {
    setCardSelected(card, true);
  });
  updateCount();
});

deselectAllBtn?.addEventListener("click", () => {
  getCards().forEach((card) => {
    setCardSelected(card, false);
  });
  updateCount();
});

bookList?.addEventListener("click", (event) => {
  if (event.target.closest("[data-bookmark-toggle], [data-details-button], .expand-toggle")) return;
  const card = event.target.closest(".book-item");
  if (!card || card.classList.contains("hidden")) return;
  const selected = !card.classList.contains("selected");
  setCardSelected(card, selected);
  updateCount();
});

downloadForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = selectedDownloadPayload();
  if (payload.book_links.length === 0) {
    showToast(text("noValidSelectionTitle"), text("noValidSelectionMessage"), "error");
    return;
  }

  if (progressContainer) progressContainer.hidden = false;
  if (downloadBtn) downloadBtn.disabled = true;
  setProgress({ progress: 0, message: text("startingDownload") });

  try {
    const response = await fetch("/start-download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.job_id) {
      throw new Error(data.error || "Failed to start download.");
    }
    showToast(text("downloadStartedTitle"), text("downloadStartedMessage"));
    pollJob(data.job_id);
  } catch (error) {
    if (progressContainer) progressContainer.hidden = true;
    if (downloadBtn) downloadBtn.disabled = false;
    showToast(text("downloadFailedTitle"), error.message || text("downloadFailedMessage"), "error");
  }
});

const firstAvailableTab = formatTabs.find((tab) => !tab.disabled);
if (firstAvailableTab?.dataset.format) {
  setFormat(firstAvailableTab.dataset.format);
} else {
  applyFilters();
}
