/**
 * Pide al backend que reevalue las reglas contra el inventario actual
 * 
 * Se llama tras crear, editar, activar/desactivar o borrar una regla
 */
async function evaluarListaCompra() {
  try {
    await fetchJson(evalUrl(), { method: "POST" });
  } catch {
    // Si ha fallado, la lista se reevaluara la proxima vez
  }
}

/**
 * Descarga las reglas de reposicion de la nevera y las pinta
 */
async function loadRules() {
  const container = document.querySelector("[data-rules-list]");
  if (!container) return;

  container.innerHTML = `
    <article class="config-toggle-row">
      <div class="config-toggle-copy">
        <strong>Cargando reglas...</strong>
        <p>Consultando ${escapeHtml(state.config.API_BASE_URL)}</p>
      </div>
    </article>`;

  try {
    const rules = await fetchJson(rulesUrl());
    state.rules = Array.isArray(rules) ? rules : [];
    renderRules(state.rules);
  } catch (error) {
    state.rules = null;
    container.innerHTML = `
      <article class="config-toggle-row">
        <div class="config-toggle-copy">
          <strong>No se pudieron cargar las reglas</strong>
          <p>${escapeHtml(getInventoryErrorMessage(error))}</p>
        </div>
      </article>`;
  }
}

/**
 * Pinta cada regla como una fila con su informacion (minimo, objetivo,
 * estado) y sus controles
 */
function renderRules(rules) {
  const container = document.querySelector("[data-rules-list]");
  if (!container) return;

  if (!rules.length) {
    container.innerHTML = `
      <article class="config-toggle-row">
        <div class="config-toggle-copy">
          <strong>No hay reglas configuradas</strong>
          <p>Crea una regla para generar lista de compra automaticamente.</p>
        </div>
      </article>`;
    return;
  }

  container.innerHTML = rules.map((rule) => {
    const barcode = escapeHtml(getBarcode(rule));
    const name = escapeHtml(rule.productName || getProductName(rule));
    const active = rule.enabled !== false;
    return `
      <article class="config-toggle-row">
        <div class="config-toggle-copy">
          <strong>${name}</strong>
          <p>
            Codigo: ${barcode}
            | minimo: ${toNumber(rule.minQty, 0)}
            | objetivo: ${toNumber(rule.targetQty, 0)}
            | ${active ? "activa" : "desactivada"}
          </p>
        </div>
        <div class="config-toggle-actions">
          <label class="toggle-switch" aria-label="Activar o desactivar regla">
            <input type="checkbox" data-toggle-rule="${barcode}" ${active ? "checked" : ""} />
            <span class="toggle-slider"></span>
          </label>
          <button type="button" class="rule-action-btn" data-edit-rule="${barcode}">Editar</button>
          <button type="button" class="rule-action-btn rule-action-delete" data-delete-rule="${barcode}">Eliminar</button>
        </div>
      </article>`;
  }).join("");
}

/**
 * Valida el formulario (barcode obligatorio, objetivo > minimo) y guarda
 * la regla con PUT en el backend
 */
async function saveRuleFromForm(form) {
  const barcode = form.elements.barcode.value.trim();
  const minQty = toNumber(form.elements.minQty.value, 0);
  const targetQty = toNumber(form.elements.targetQty.value, minQty + 1);
  const enabled = form.elements.enabled.value === "true";

  if (!barcode) {
    setFeedback("El codigo de barras es obligatorio.", "error");
    return;
  }
  if (minQty < 0) {
    setFeedback("La cantidad minima no puede ser negativa.", "error");
    return;
  }
  if (targetQty <= minQty) {
    setFeedback("La cantidad objetivo debe ser mayor que la cantidad minima.", "error");
    return;
  }

  setApiStatus("Guardando regla");
  setFeedback("Enviando regla de compra al backend...", "loading");

  try {
    await fetchJson(ruleUrl(barcode), {
      method: "PUT",
      body: { barcode, minQty, targetQty, enabled, source: "DASHBOARD" },
    });
    setApiStatus("API conectada");
    setFeedback("Regla de compra guardada correctamente.", "success");
    cancelEdit(false);
    await loadRules();
    await evaluarListaCompra();
  } catch (error) {
    setApiStatusFromError(error);
    setFeedback(`No se pudo guardar la regla: ${error.message}`, "error");
  }
}

/**
 * Pasa el formulario a modo edicion
 */
function editRule(rule) {
  const form = document.querySelector("[data-rule-form]");
  if (!form) return;

  state.editingBarcode = getBarcode(rule);
  form.elements.barcode.value = getBarcode(rule);
  form.elements.barcode.readOnly = true;
  form.elements.minQty.value = String(toNumber(rule.minQty, 0));
  form.elements.targetQty.value = String(toNumber(rule.targetQty, 1));
  form.elements.enabled.value = rule.enabled === false ? "false" : "true";

  const formTitle = document.querySelector("[data-form-title]");
  if (formTitle) formTitle.textContent = "EDITAR REGLA";

  const submitBtn = form.querySelector("[type=submit]");
  if (submitBtn) submitBtn.textContent = "Actualizar regla";

  const cancelBtn = document.querySelector("[data-cancel-edit]");
  if (cancelBtn) cancelBtn.hidden = false;

  form.scrollIntoView({ behavior: "smooth" });

  setFeedback(`Editando: ${rule.productName || getProductName(rule)}`, "info");
}

/**
 * Devuelve el formulario al modo creacion de regla
 */
function cancelEdit(showFeedback = true) {
  const form = document.querySelector("[data-rule-form]");
  if (!form) return;

  state.editingBarcode = null;
  form.reset();
  form.elements.minQty.value = "1";
  form.elements.targetQty.value = "3";
  form.elements.enabled.value = "true";
  form.elements.barcode.readOnly = false;

  const formTitle = document.querySelector("[data-form-title]");
  if (formTitle) formTitle.textContent = "CONFIGURAR REGLA";

  const submitBtn = form.querySelector("[type=submit]");
  if (submitBtn) submitBtn.textContent = "Guardar regla de compra";

  const cancelBtn = document.querySelector("[data-cancel-edit]");
  if (cancelBtn) cancelBtn.hidden = true;

  if (showFeedback) setFeedback("Formulario listo para nueva regla.", "info");
}

/**
 * Activa o desactiva una regla desde su toggle
 */
async function applyToggleRule(barcode, enabled) {
  const rule = (state.rules || []).find((r) => getBarcode(r) === barcode);
  if (!rule) {
    setFeedback("No se encontro la regla para actualizar.", "error");
    await loadRules();
    return;
  }

  setFeedback(`${enabled ? "Activando" : "Desactivando"} regla...`, "loading");

  try {
    await fetchJson(ruleUrl(barcode), {
      method: "PUT",
      body: {
        barcode: rule.barcode,
        minQty: rule.minQty,
        targetQty: rule.targetQty,
        enabled,
        source: "DASHBOARD",
      },
    });
    setApiStatus("API conectada");
    setFeedback(`Regla ${enabled ? "activada" : "desactivada"} correctamente.`, "success");
    await loadRules();
    await evaluarListaCompra();
  } catch (error) {
    setApiStatusFromError(error);
    setFeedback(`No se pudo actualizar la regla: ${error.message}`, "error");
    await loadRules();
  }
}

/**
 * Borra una regla previa confirmacion del usuario
 */
async function deleteRule(barcode) {
  if (!confirm(`¿Eliminar la regla para el codigo ${barcode}?`)) return;

  setFeedback("Eliminando regla...", "loading");

  try {
    await fetchJson(ruleUrl(barcode), { method: "DELETE" });
    setApiStatus("API conectada");
    setFeedback("Regla eliminada correctamente.", "success");
    if (state.editingBarcode === barcode) cancelEdit(false);
    await loadRules();
    await evaluarListaCompra();
  } catch (error) {
    setApiStatusFromError(error);
    setFeedback(`No se pudo eliminar la regla: ${error.message}`, "error");
  }
}

/** Conecta el envio del formulario de reglas */
function bindRuleForm() {
  const form = document.querySelector("[data-rule-form]");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    saveRuleFromForm(form);
  });
}

/**
 * Delegacion de eventos sobre la lista de reglas
 */
function bindRuleActions() {
  const container = document.querySelector("[data-rules-list]");
  if (!container) return;

  container.addEventListener("change", async (e) => {
    const toggle = e.target.closest("[data-toggle-rule]");
    if (toggle) await applyToggleRule(toggle.dataset.toggleRule, toggle.checked);
  });

  container.addEventListener("click", async (e) => {
    const editBtn = e.target.closest("[data-edit-rule]");
    if (editBtn) {
      const barcode = editBtn.dataset.editRule;
      const rule = (state.rules || []).find((r) => getBarcode(r) === barcode);
      if (rule) editRule(rule);
      return;
    }
    const deleteBtn = e.target.closest("[data-delete-rule]");
    if (deleteBtn) await deleteRule(deleteBtn.dataset.deleteRule);
  });
}

/** Conecta el boton "Cancelar edicion" del formulario. */
function bindCancelEdit() {
  const btn = document.querySelector("[data-cancel-edit]");
  if (!btn) return;
  btn.addEventListener("click", () => cancelEdit(true));
}

/**
 * Carga inicial de la pagina
 */
async function initPage() {
  setApiStatus("Conectando");
  setFeedback("Cargando reglas de lista de compra...", "loading");
  await loadRules();
  if (state.rules === null) {
    setApiStatus("API caida");
    setFeedback("No se pudieron cargar las reglas. Revisa que el backend este levantado.", "error");
  } else {
    setApiStatus("API conectada");
    const n = state.rules.length;
    setFeedback(
      n > 0
        ? `${n} regla${n === 1 ? "" : "s"} cargada${n === 1 ? "" : "s"}. Puedes editar, activar/desactivar o eliminar cada regla.`
        : "No hay reglas configuradas. Usa el formulario para crear la primera.",
      "success",
    );
  }
}

bindRuleForm();
bindRuleActions();
bindCancelEdit();

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", initPage);
});

const _rulesRefreshMs = getAutoRefreshMilliseconds();
if (_rulesRefreshMs > 0) {
  setInterval(initPage, _rulesRefreshMs);
}

initPage();
