/**
 * Conecta el buscador de productos
 */
function bindSearch() {
  const form = document.querySelector("[data-search-form]");
  const input = document.querySelector("[data-search-input]");
  if (!form || !input) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    state.search = input.value;
    renderInventoryList();
    renderInventoryTable();
  });

  input.addEventListener("input", () => {
    state.search = input.value;
    renderInventoryList();
    renderInventoryTable();
  });
}

/**
 * Carga inicial de la pagina
 */
async function initPage() {
  await loadInventory();
}

bindSearch();

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", initPage);
});

const _inventoryRefreshMs = getAutoRefreshMilliseconds();
if (_inventoryRefreshMs > 0) {
  setInterval(initPage, _inventoryRefreshMs);
}

initPage();
