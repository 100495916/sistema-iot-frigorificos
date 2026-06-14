// Configuration como fallback

const DEFAULT_CONFIG = {
  API_BASE_URL: "http://127.0.0.1:8000",
  FRIDGE_ID: "Nevera_Docker_001",
  AUTO_REFRESH_SECONDS: 0,
};

// Paginas del dashboard
const NAV_PAGES = ["index.html", "inventory.html", "historial.html", "reglas.html", "lista-compra.html", "configuracion.html"];

const state = {
  config: loadConfig(),
  inventory: null,
  shoppingList: null,
  historyEvents: null,
  rules: null,
  search: "",
  editingBarcode: null,
};

/**
 * Lee los parametros ?fridge= y ?api= de la URL actual
 */
function readUrlParams() {
  const p = new URLSearchParams(window.location.search);
  const result = {};
  if (p.has("fridge")) result.FRIDGE_ID   = p.get("fridge");
  if (p.has("api"))    result.API_BASE_URL = p.get("api");
  return result;
}

/**
 * Serializa la configuracion activa para propagarla en los enlaces de navegacion
 */
function buildQueryString(config) {
  const p = new URLSearchParams();
  p.set("fridge", config.FRIDGE_ID);
  p.set("api",    config.API_BASE_URL);
  return p.toString();
}

/**
 * Construye la URL de una pagina del dashboard
 */
function withParams(page, cfg) {
  return `${page}?${buildQueryString(cfg || state.config)}`;
}

/**
 * Reescribe todos los enlaces de navegacion de la pagina para que lleven
 * la configuracion activa
 */
function updateNavLinks() {
  NAV_PAGES.forEach((page) => {
    document.querySelectorAll(`a[href="${page}"], a[href^="${page}?"]`).forEach((a) => {
      a.href = withParams(page);
    });
  });
}

/**
 * Calcula la configuracion inicial en el siguiente orden:
 * 
 * parametros de la URL > config.js > valores por defecto.
 */
function loadConfig() {
  const fileConfig = window.DASHBOARD_CONFIG || {};
  const baseConfig = { ...DEFAULT_CONFIG, ...fileConfig };
  
  return normalizeConfig({ ...baseConfig, ...readUrlParams() });
}

/**
 * Sanea una configuracion
 */
function normalizeConfig(config) {
  return {
    API_BASE_URL: String(config.API_BASE_URL || DEFAULT_CONFIG.API_BASE_URL).trim().replace(/\/+$/, ""),
    FRIDGE_ID: String(config.FRIDGE_ID || DEFAULT_CONFIG.FRIDGE_ID).trim(),
    AUTO_REFRESH_SECONDS: toNumber(config.AUTO_REFRESH_SECONDS, DEFAULT_CONFIG.AUTO_REFRESH_SECONDS),
  };
}

/**
 * Activa una nueva configuracion y la refleja en la URL
 */
function saveConfig(config) {
  state.config = normalizeConfig(config);
  const query = buildQueryString(state.config);
  window.history.replaceState({}, "", `${window.location.pathname}?${query}`);
  updateNavLinks();
}

/**
 * Devuelve el intervalo de auto-refresco en milisegundos
 */
function getAutoRefreshMilliseconds() {
  return Math.max(0, state.config.AUTO_REFRESH_SECONDS) * 1000;
}

// URL Builders

/** URL del inventario actual de la nevera. */
function inventoryUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/inventario`;
}

/** URL de la lista de compra PENDING de la nevera. */
function shoppingUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra/pendiente`;
}

/** URL de la coleccion de reglas de reposicion de la nevera. */
function rulesUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/reglas-lista-compra`;
}

/** URL de la regla de un producto concreto (para PUT y DELETE). */
function ruleUrl(barcode) {
  return `${rulesUrl()}/${encodeURIComponent(barcode)}`;
}

/** URL del historial de eventos procesados (ultimos 50). */
function processedEventsUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/eventos-procesados?limit=50`;
}

/** URL de la accion de reevaluar las reglas contra el inventario. */
function evalUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra/evaluar`;
}

/** URL de la accion de pedir online la lista PENDING (-> ORDERED). */
function pedirListaCompraUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra/pendiente/pedir`;
}

/** URL de las listas en estado ORDERED (pedidos en camino). */
function orderedListsUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra?status=ORDERED`;
}

/** URL de la accion de completar un pedido (ORDERED -> COMPLETED). */
function completarListaUrl(listId) {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra/${encodeURIComponent(listId)}/completar`;
}

/** URL para añadir un item manual a la lista PENDING. */
function addItemUrl() {
  return `${state.config.API_BASE_URL}/api/v2/fridges/${encodeURIComponent(state.config.FRIDGE_ID)}/lista-compra/pendiente/items`;
}

// API 

/**
 * Wrapper de fetch para la API del backend
 */
async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText;
    }
    const error = new Error(detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

// Data Accessors

/** Nombre legible de un item */
function getProductName(item) {
  return item.productName || `Producto ${getBarcode(item)}`;
}

/** Barcode de un item */
function getBarcode(item) {
  return item.barcode || "Sin codigo";
}

/** Cantidad en stock de un item de inventario */
function getProductQty(item) {
  return toNumber(item.qty, 0);
}

/** Cantidad a comprar de un item de lista */
function getShoppingQty(item) {
  return toNumber(item.qtyToBuy ?? item.qty, 0);
}

/** Items del inventario */
function getItems() {
  return Array.isArray(state.inventory?.items) ? state.inventory.items : [];
}

/**
 * Filtra los items del inventario segun el texto de busqueda actual
 */
function getFilteredItems() {
  const search = state.search.trim().toLowerCase();
  const items = getItems();
  if (!search) return items;
  return items.filter((item) => {
    const text = `${getProductName(item)} ${getBarcode(item)}`.toLowerCase();
    return text.includes(search);
  });
}

/**
 * Devuelve las metricas del inventario (total de unidades y productos distintos)
 */
function getMetrics() {
  const items = getItems();
  const apiMetrics = state.inventory?.metrics || {};
  return {
    inventoryCount: toNumber(apiMetrics.inventoryCount, items.reduce((t, i) => t + getProductQty(i), 0)),
    inventoryUniqueItems: toNumber(apiMetrics.inventoryUniqueItems, items.length),
  };
}

// Utilities

/**
 * Convierte cualquier valor a entero de forma segura
 */
function toNumber(value, fallback = 0) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Formatea una fecha ISO al formato corto español
 */
function formatDate(value) {
  if (!value) return "Sin datos";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
}

/** Convierte una clave en texto legible */
function formatMetricKey(key) {
  return String(key).replace(/([A-Z])/g, " $1").replace(/[_-]+/g, " ").trim();
}

/**
 * Escapa los caracteres especiales de HTML
 */
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// UI Helpers

/** Actualiza el indicador de estado de la API */
function setApiStatus(text) {
  document.querySelectorAll("[data-api-status]").forEach((el) => { el.textContent = text; });
}

/**
 * Actualiza el indicador segun el tipo de error
 */
function setApiStatusFromError(error) {
  setApiStatus(error.status ? "API conectada" : "API caida");
}

/**
 * Muestra un mensaje en la caja de feedback de la pagina
 */
function setFeedback(message, type) {
  document.querySelectorAll("[data-feedback]").forEach((el) => {
    el.textContent = message;
    el.dataset.state = type;
  });
}

/** Refresca el reloj de la cabecera (se llama cada segundo) */
function updateClock() {
  const now = new Date();
  const formattedTime = now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", hour12: false });
  document.querySelectorAll("[data-live-time]").forEach((el) => { el.textContent = formattedTime; });
}

// Common Renders

/**
 * Pinta la informacion comun a todas las paginas
 */
function renderCommonInfo() {
  document.querySelectorAll("[data-fridge-id]").forEach((el) => {
    el.textContent = state.inventory?.fridgeId || state.config.FRIDGE_ID || "Sin configurar";
  });
  document.querySelectorAll("[data-api-base-url]").forEach((el) => {
    el.textContent = state.config.API_BASE_URL || "Sin configurar";
  });
  document.querySelectorAll("[data-endpoint-preview]").forEach((el) => {
    el.textContent = `GET /api/v2/fridges/${state.config.FRIDGE_ID}/inventario`;
  });
  document.querySelectorAll("[data-auto-refresh-label]").forEach((el) => {
    el.textContent = state.config.AUTO_REFRESH_SECONDS > 0
      ? `${state.config.AUTO_REFRESH_SECONDS} segundos`
      : "Desactivado";
  });
}

/**
 * Pinta el resumen del inventario
 */
function renderSummary() {
  const metrics = getMetrics();
  const updatedAt = state.inventory?.updatedAt;
  document.querySelectorAll("[data-total-products]").forEach((el) => {
    el.textContent = String(metrics.inventoryCount);
  });
  document.querySelectorAll("[data-unique-products]").forEach((el) => {
    el.textContent = String(metrics.inventoryUniqueItems);
  });
  document.querySelectorAll("[data-last-updated]").forEach((el) => {
    el.textContent = formatDate(updatedAt);
  });
}

/**
 * Traduce un error de la API a un mensaje util para el usuario
 */
function getInventoryErrorMessage(error) {
  if (error.status === 404) {
    return `No existe inventario reconstruido para la nevera ${state.config.FRIDGE_ID}.`;
  }
  if (error instanceof TypeError) {
    return "No se puede conectar con la API. Revisa que el backend este levantado y que CORS este habilitado.";
  }
  return `Error consultando la API: ${error.message}`;
}

/**
 * Carga el inventario de la nevera desde el backend, actualiza el estado
 * global y repinta todos los componentes
 */
async function loadInventory() {
  setApiStatus("Conectando");
  setFeedback("Consultando el inventario oficial en el backend...", "loading");

  try {
    state.inventory = await fetchJson(inventoryUrl());
    setApiStatus("API conectada");
    setFeedback("Inventario cargado correctamente desde MongoDB mediante la API del backend.", "success");
    renderInventoryData();
  } catch (error) {
    state.inventory = null;
    setApiStatusFromError(error);
    setFeedback(getInventoryErrorMessage(error), "error");
    renderInventoryData();
  }
}

/**
 * Repinta todos los componentes que dependen del inventari
 */
function renderInventoryData() {
  renderCommonInfo();
  renderSummary();
  renderInventoryList();
  renderInventoryTable();
  renderMetrics();
}

/**
 * Pinta el listado de tarjetas de productos (filtrado por la busqueda)
 */
function renderInventoryList() {
  const container = document.querySelector("[data-inventory-list]");
  if (!container) return;

  const items = getFilteredItems();

  if (!state.inventory) {
    container.innerHTML = `
      <article class="inventory-item-card">
        <div class="inventory-item-copy">
          <strong>Inventario no disponible</strong>
          <p>Cantidad: -</p>
          <p>Codigo: -</p>
          <p>Origen: Backend API</p>
        </div>
      </article>`;
    return;
  }

  if (!items.length) {
    container.innerHTML = `
      <article class="inventory-item-card">
        <div class="inventory-item-copy">
          <strong>No hay productos que mostrar</strong>
          <p>Cantidad: 0</p>
          <p>Codigo: -</p>
          <p>Origen: Backend API</p>
        </div>
      </article>`;
    return;
  }

  container.innerHTML = items.map(renderInventoryItem).join("");
}

/** Genera el HTML de la tarjeta de un producto */
function renderInventoryItem(item) {
  return `
    <article class="inventory-item-card">
      <div class="inventory-item-copy">
        <strong>${escapeHtml(getProductName(item))}</strong>
        <p>Cantidad: ${getProductQty(item)}</p>
        <p>Codigo: ${escapeHtml(getBarcode(item))}</p>
        <p>Origen: Backend API</p>
      </div>
    </article>`;
}

/**
 * Pinta la tabla de productos
 */
function renderInventoryTable() {
  const tableBody = document.querySelector("[data-inventory-table]");
  if (!tableBody) return;

  const items = getFilteredItems();

  if (!state.inventory) {
    tableBody.innerHTML = `<tr><td colspan="3">Inventario no disponible.</td></tr>`;
    return;
  }
  if (!items.length) {
    tableBody.innerHTML = `<tr><td colspan="3">No hay productos que coincidan con la busqueda.</td></tr>`;
    return;
  }

  tableBody.innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(getProductName(item))}</td>
      <td>${escapeHtml(getBarcode(item))}</td>
      <td>${getProductQty(item)}</td>
    </tr>`).join("");
}

/**
 * Pinta las metricas adicionales del inventario
 */
function renderMetrics() {
  const container = document.querySelector("[data-extra-metrics]");
  if (!container) return;

  const metrics = state.inventory?.metrics || {};
  const metricEntries = Object.entries(metrics).filter(([key]) =>
    !["inventoryCount", "inventoryUniqueItems"].includes(key)
  );

  if (!metricEntries.length) {
    container.innerHTML = `<p class="metric-empty">No hay metricas adicionales.</p>`;
    return;
  }

  container.innerHTML = metricEntries.map(([key, value]) => `
    <div class="metric-line">
      <span>${escapeHtml(formatMetricKey(key))}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>`).join("");
}

/** URL del endpoint de alertas de puerta activas. */
function alertasActivasUrl() {
  return `${state.config.API_BASE_URL}/api/v2/alertas/activas`;
}

// Alertas de puerta

/**
 * Pinta (o elimina) el banner rojo
 */
function _renderBannerAlertas(alertas) {
  const existente = document.getElementById("alerta-puerta-banner");

  if (!alertas.length) {
    if (existente) existente.remove();
    return;
  }

  const texto = alertas
    .map((a) => `Nevera ${escapeHtml(a.fridgeId)}: puerta abierta mas de 30s`)
    .join(" &nbsp;|&nbsp; ");

  const html = `<div id="alerta-puerta-banner" class="alerta-puerta-banner">&#9888; ${texto}</div>`;

  if (existente) existente.outerHTML = html;
  else document.body.insertAdjacentHTML("afterbegin", html);
}

/**
 * Poll de alertas de puerta (cada 20s desde todas las paginas)
 */
async function _checkAlertasPuerta() {
  try {
    const alertas = await fetchJson(alertasActivasUrl());
    // Solo mostramos la alerta de la nevera que el usuario tiene configurada (config.js o param ?fridge=)
    const filtradas = Array.isArray(alertas)
      ? alertas.filter((a) => a.fridgeId === state.config.FRIDGE_ID)
      : [];
    _renderBannerAlertas(filtradas);
  } catch {
    // Si el backend no responde no mostramos nada
  }
}

// Init 

updateClock();
setInterval(updateClock, 1000);
renderCommonInfo();
updateNavLinks();
_checkAlertasPuerta();
setInterval(_checkAlertasPuerta, 20000);

document.querySelectorAll("[data-live-time]").forEach((el) => {
  el.style.cursor = "pointer";
  el.title = "Ir al inicio";
  el.addEventListener("click", () => { window.location.href = withParams("index.html"); });
});
