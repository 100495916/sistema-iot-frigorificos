/**
 * Descarga la lista PENDING de la nevera y la pinta
 */
async function loadShoppingList() {
  const container = document.querySelector("[data-shopping-list]");
  if (!container) return;

  container.innerHTML = renderShoppingLoading();

  try {
    state.shoppingList = await fetchJson(shoppingUrl());
    setApiStatus("API conectada");
    setFeedback("Lista de compra cargada.", "success");
    renderShoppingList();
  } catch (error) {
    state.shoppingList = null;
    if (error.status === 404) {
      setApiStatus("API conectada");
      setFeedback("No hay lista de compra pendiente.", "info");
      container.innerHTML = renderEmptyShoppingList();
      const pedirPanel = document.querySelector("[data-pedir-panel]");
      if (pedirPanel) pedirPanel.hidden = true;
      return;
    }
    setApiStatusFromError(error);
    setFeedback("No se pudo cargar la lista de compra.", "error");
    container.innerHTML = `
      <article class="shopping-item-row">
        <div class="shopping-item-copy">
          <strong>No se pudo cargar la lista de compra</strong>
        </div>
        <div class="shopping-item-actions">
          <span class="shopping-qty-value">!</span>
        </div>
      </article>`;
  }
}

/**
 * Descarga los pedidos en camino y los pinta
 */
async function loadOrderedLists() {
  const panel = document.querySelector("[data-ordered-lists-panel]");
  if (!panel) return;

  try {
    const lists = await fetchJson(orderedListsUrl());
    renderOrderedLists(Array.isArray(lists) ? lists : []);
  } catch {
    renderOrderedLists([]);
  }
}

/**
 * Pinta los items de la lista PENDING
 */
function renderShoppingList() {
  const container = document.querySelector("[data-shopping-list]");
  if (!container) return;

  const items = Array.isArray(state.shoppingList?.items) ? state.shoppingList.items : [];
  const pedirPanel = document.querySelector("[data-pedir-panel]");

  if (!items.length) {
    container.innerHTML = renderEmptyShoppingList();
    if (pedirPanel) pedirPanel.hidden = true;
    return;
  }

  container.innerHTML = items.map((item) => `
    <article class="shopping-item-row">
      <div class="shopping-item-copy">
        <strong>${escapeHtml(getProductName(item))}</strong>
        <p class="shopping-item-code">${escapeHtml(getBarcode(item))}</p>
      </div>
      <div class="shopping-item-actions">
        <span>Cantidad</span>
        <span class="shopping-qty-value">${getShoppingQty(item)}</span>
      </div>
    </article>`).join("");

  if (pedirPanel) pedirPanel.hidden = false;
}

function renderShoppingLoading() {
  return `
    <article class="shopping-item-row">
      <div class="shopping-item-copy">
        <strong>Cargando lista pendiente...</strong>
      </div>
      <div class="shopping-item-actions">
        <span class="shopping-qty-value">0</span>
      </div>
    </article>`;
}

/** HTML del estado vacio */
function renderEmptyShoppingList() {
  return `
    <article class="shopping-item-row">
      <div class="shopping-item-copy">
        <strong>No hay productos pendientes</strong>
      </div>
      <div class="shopping-item-actions">
        <span class="shopping-qty-value">0</span>
      </div>
    </article>`;
}

/**
 * Pinta cada pedido ORDERED con su fecha, el resumen de productos y un
 * boton "Confirmar llegada"
 */
function renderOrderedLists(lists) {
  const panel = document.querySelector("[data-ordered-lists-panel]");
  const container = document.querySelector("[data-ordered-lists]");
  if (!panel || !container) return;

  if (!lists.length) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  container.innerHTML = lists.map((lista) => {
    const items = Array.isArray(lista.items) ? lista.items : [];
    const listId = escapeHtml(lista.listId || "");
    const orderedAt = formatDate(lista.orderedAt);
    const resumen = items.length
      ? items.map((i) => `${escapeHtml(getProductName(i))} x${getShoppingQty(i)}`).join(", ")
      : "Sin productos";

    return `
      <article class="shopping-item-row">
        <div class="shopping-item-copy">
          <strong>Pedido del ${orderedAt}</strong>
          <p class="shopping-item-code">${resumen}</p>
        </div>
        <div class="shopping-item-actions">
          <button type="button" class="rule-action-btn" data-confirmar-llegada="${listId}">Confirmar llegada</button>
        </div>
      </article>`;
  }).join("");
}

/**
 * Simula el pedido online de la lista PENDING
 */
async function pedirListaCompra() {
  const items = Array.isArray(state.shoppingList?.items) ? state.shoppingList.items : [];
  if (!items.length) {
    setFeedback("No hay productos pendientes para pedir.", "error");
    return;
  }

  const n = items.length;
  const msg = `Vas a realizar un pedido online de ${n} producto${n === 1 ? "" : "s"}:\n`
    + items.map((i) => `  - ${getProductName(i)} x${getShoppingQty(i)}`).join("\n")
    + "\n\n¿Confirmar pedido?";

  if (!confirm(msg)) return;

  setFeedback("Realizando pedido online...", "loading");
  setApiStatus("Pedido en curso");

  try {
    const result = await fetchJson(pedirListaCompraUrl(), { method: "POST" });
    setApiStatus("API conectada");
    setFeedback(result.message || "Pedido realizado correctamente.", "success");
    state.shoppingList = null;
    await loadShoppingList();

    // Refrescar tambien los pedidos en camino
    // El que acabamos de cursar pasa a ORDERED y debe aparecer en el panel "Confirmar llegada".
    await loadOrderedLists();
  } catch (error) {
    setApiStatusFromError(error);
    setFeedback(`No se pudo realizar el pedido: ${error.message}`, "error");
  }
}

/**
 * Marca un pedido como recibido
 */
async function confirmarLlegada(listId) {
  setFeedback("Confirmando llegada del pedido...", "loading");

  try {
    await fetchJson(completarListaUrl(listId), { method: "POST" });
    setApiStatus("API conectada");
    setFeedback("Pedido marcado como recibido.", "success");
    await loadOrderedLists();
  } catch (error) {
    setApiStatusFromError(error);
    setFeedback(`No se pudo confirmar la llegada: ${error.message}`, "error");
  }
}

/**
 * Conecta el formulario de añadir producto manual
 */
function bindAddItemForm() {
  const form = document.querySelector("[data-add-item-form]");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const barcode = form.elements.barcode.value.trim();
    const qty = Number.parseInt(form.elements.qty.value, 10);

    if (!barcode) {
      setFeedback("El codigo de barras es obligatorio.", "error");
      return;
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      setFeedback("La cantidad debe ser mayor que 0.", "error");
      return;
    }

    setFeedback("Añadiendo producto a la lista...", "loading");
    setApiStatus("Conectando");

    try {
      await fetchJson(addItemUrl(), { method: "POST", body: { barcode, qty } });
      setApiStatus("API conectada");
      setFeedback("Producto añadido a la lista de compra.", "success");
      form.reset();
      form.elements.qty.value = "1";
      await loadShoppingList();
    } catch (error) {
      setApiStatusFromError(error);
      setFeedback(`No se pudo añadir el producto: ${error.message}`, "error");
    }
  });
}

/** Conecta los botones "Pedir online" de la pagina. */
function bindPedirOnline() {
  document.querySelectorAll("[data-pedir-online]").forEach((btn) => {
    btn.addEventListener("click", pedirListaCompra);
  });
}

/**
 * Delegacion de eventos en el panel de pedidos
 */
function bindConfirmarLlegada() {
  const panel = document.querySelector("[data-ordered-lists-panel]");
  if (!panel) return;

  panel.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-confirmar-llegada]");
    if (btn) await confirmarLlegada(btn.dataset.confirmarLlegada);
  });
}

/**
 * Carga inicial de la pagina
 */
async function initPage() {
  setApiStatus("Conectando");
  setFeedback("Cargando lista de compra...", "loading");
  await loadShoppingList();
  await loadOrderedLists();
}

bindAddItemForm();
bindPedirOnline();
bindConfirmarLlegada();

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", initPage);
});

const _shoppingRefreshMs = getAutoRefreshMilliseconds();
if (_shoppingRefreshMs > 0) {
  setInterval(initPage, _shoppingRefreshMs);
}

initPage();
