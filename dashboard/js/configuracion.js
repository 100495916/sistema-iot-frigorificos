/**
 * Conecta el formulario de configuracion
 */
function bindSettingsForm() {
  const form = document.querySelector("[data-settings-form]");
  if (!form) return;

  form.elements.apiBaseUrl.value = state.config.API_BASE_URL;
  form.elements.fridgeId.value = state.config.FRIDGE_ID;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    saveConfig({
      API_BASE_URL: form.elements.apiBaseUrl.value,
      FRIDGE_ID: form.elements.fridgeId.value,
    });
    renderCommonInfo();
    setApiStatus("Configuracion guardada");
    setFeedback("Configuracion guardada. Pulsa Probar conexion o el reloj para volver al inicio.", "success");
  });
}

/**
 * Conecta el boton de restaurar que descarta los parametros de la URL y
 * vuelve a la configuracion definida en config.js
 */
function bindConfigReset() {
  const button = document.querySelector("[data-reset-config]");
  const form = document.querySelector("[data-settings-form]");
  if (!button || !form) return;

  button.addEventListener("click", () => {
    const fileConfig = window.DASHBOARD_CONFIG || {};
    const defaults = { ...DEFAULT_CONFIG, ...fileConfig };
    state.config = normalizeConfig(defaults);
    form.elements.apiBaseUrl.value = state.config.API_BASE_URL;
    form.elements.fridgeId.value = state.config.FRIDGE_ID;
    window.history.replaceState({}, "", window.location.pathname);
    updateNavLinks();
    renderCommonInfo();
    setApiStatus("Configuracion restaurada");
    setFeedback("Se ha restaurado la configuracion definida en config.js.", "success");
  });
}

/**
 * Conecta el boton "Probar conexion"
 */
function bindTestConnection() {
  document.querySelectorAll("[data-test-connection]").forEach((button) => {
    button.addEventListener("click", async () => {
      const form = document.querySelector("[data-settings-form]");
      if (form) {
        saveConfig({
          API_BASE_URL: form.elements.apiBaseUrl.value,
          FRIDGE_ID: form.elements.fridgeId.value,
        });
        renderCommonInfo();
      }
      await loadInventory();
    });
  });
}

setFeedback("Configura la URL del backend y la nevera que quieres consultar.", "info");
bindSettingsForm();
bindConfigReset();
bindTestConnection();
