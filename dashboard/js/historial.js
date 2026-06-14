/**
 * Descarga los 50 eventos procesados de la nevera
 */
async function loadHistory() {
  const container = document.querySelector("[data-history-list]");
  if (!container) return;

  container.innerHTML = `
    <article class="history-row">
      <span class="history-pill history-pill-add">Cargando eventos procesados desde MongoDB</span>
      <span class="history-action">i</span>
    </article>`;

  try {
    const events = await fetchJson(processedEventsUrl());
    state.historyEvents = Array.isArray(events) ? events : [];
    setApiStatus("API conectada");
    renderHistory();
  } catch (error) {
    state.historyEvents = [];
    setApiStatusFromError(error);
    container.innerHTML = `
      <article class="history-row">
        <span class="history-pill history-pill-remove">${escapeHtml(getInventoryErrorMessage(error))}</span>
        <span class="history-action">!</span>
      </article>`;
  }
}

/**
 * Pinta la lista de eventos como pildoras de colores (verde añadido,
 * rojo retirado)
 */
function renderHistory() {
  const container = document.querySelector("[data-history-list]");
  if (!container) return;

  if (!state.historyEvents) {
    container.innerHTML = `
      <article class="history-row">
        <span class="history-pill history-pill-add">Cargando eventos procesados desde MongoDB</span>
        <span class="history-action">i</span>
      </article>`;
    return;
  }

  if (!state.historyEvents.length) {
    container.innerHTML = `
      <article class="history-row">
        <span class="history-pill history-pill-remove">No hay eventos procesados para esta nevera</span>
        <span class="history-action">!</span>
      </article>`;
    return;
  }

  container.innerHTML = state.historyEvents.map((event) => {
    const view = getHistoryView(event);
    return `
      <article class="history-row">
        <span class="history-pill history-pill-${view.type}">${escapeHtml(view.text)}</span>
        <span class="history-action">${escapeHtml(view.sign)}</span>
      </article>`;
  }).join("");
}

/**
 * Traduce un evento crudo del backend a su representacion visual
 */
function getHistoryView(event) {
  const eventType = event.eventType || "UNKNOWN";
  const payload = event.payload || {};
  const when = formatDate(event.processedAt);
  const product = payload.productName || payload.nombre || payload.barcode || "sin producto";

  if (eventType === "PRODUCT_ADDED") {
    return { type: "add", sign: "+", text: `${when} - Producto anadido - ${product} x${toNumber(payload.cantidad, 0)}` };
  }
  if (eventType === "PRODUCT_REMOVE") {
    return { type: "remove", sign: "-", text: `${when} - Producto retirado - ${product} x${toNumber(payload.cantidad, 0)}` };
  }
  if (eventType === "FRIDGE_CREATED") {
    return { type: "add", sign: "i", text: `${when} - Nevera creada - ${event.fridgeId || state.config.FRIDGE_ID}` };
  }
  return { type: "warning", sign: "i", text: `${when} - ${eventType} - ${event.eventId || "sin eventId"}` };
}

function getInventoryReference(payload) {
  return payload.inventoryEventId || "sin referencia";
}

/**
 * Carga inicial de la pagina
 */
async function initPage() {
  setApiStatus("Conectando");
  setFeedback("Cargando historial de eventos procesados...", "loading");
  await loadHistory();
  if (state.historyEvents && state.historyEvents.length > 0) {
    const n = state.historyEvents.length;
    setFeedback(`${n} evento${n === 1 ? "" : "s"} cargado${n === 1 ? "" : "s"}.`, "success");
  } else if (state.historyEvents && state.historyEvents.length === 0) {
    setFeedback("No hay eventos procesados para esta nevera.", "info");
  }
}

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", initPage);
});

const _historyRefreshMs = getAutoRefreshMilliseconds();
if (_historyRefreshMs > 0) {
  setInterval(initPage, _historyRefreshMs);
}

initPage();
