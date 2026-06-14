/**
 * Carga inicial de la pagina
 */
async function initPage() {
  await loadInventory();
}

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", initPage);
});

const _homeRefreshMs = getAutoRefreshMilliseconds();
if (_homeRefreshMs > 0) {
  setInterval(initPage, _homeRefreshMs);
}

initPage();
