const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const loadingOverlay = document.getElementById("loadingOverlay");

if (searchForm && searchInput && loadingOverlay) {
  searchForm.addEventListener("submit", () => {
    if (searchInput.value.trim()) {
      loadingOverlay.classList.add("active");
      loadingOverlay.setAttribute("aria-hidden", "false");
    }
  });

  searchInput.focus();

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== searchInput) {
      event.preventDefault();
      searchInput.focus();
    }
  });
}
