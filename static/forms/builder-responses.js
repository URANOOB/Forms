(() => {
  const root = document.getElementById("builder");
  if (!root) return;
  const tab = document.getElementById("builder-responses");
  const panel = document.getElementById("builder-responses-panel");
  const list = document.getElementById("builder-responses-list");
  const status = document.getElementById("builder-responses-status");
  const query = document.getElementById("builder-response-query");
  let currentPage = 1;
  let pending = null;

  async function responseData(params, signal) {
    const url = new URL(tab.dataset.url, location.href);
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
    const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
    if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("No se pudieron cargar las respuestas. Revisa tu sesión y vuelve a intentarlo.");
    }
    return response.json();
  }

  async function loadResponses(page = 1) {
    if (!tab.dataset.url) return;
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    currentPage = page;
    status.textContent = "Cargando respuestas…";
    list.setAttribute("aria-busy", "true");
    try {
      const data = await responseData({ page, q: query.value.trim() }, controller.signal);
      if (controller.signal.aborted) return;
      list.innerHTML = data.html;
      document.getElementById("builder-response-count").textContent = `(${data.total})`;
      status.textContent = data.count === 1 ? "1 respuesta" : `${data.count} respuestas`;
    } catch (error) {
      if (!controller.signal.aborted && error.name !== "AbortError") {
        list.replaceChildren();
        status.textContent = error.message;
      }
    } finally {
      if (pending === controller) {
        pending = null;
        list.removeAttribute("aria-busy");
      }
    }
  }

  root.addEventListener("click", async (event) => {
    const selectedTab = event.target.closest("[data-builder-tab]");
    if (selectedTab) {
      const selected = selectedTab.dataset.builderTab;
      root.dispatchEvent(new CustomEvent("builder:tab-change", { detail: selected }));
      for (const name of ["questions", "responses", "settings"]) {
        document.getElementById(`builder-${name}-panel`).hidden = selected !== name;
      }
      root.querySelectorAll("[data-builder-tab]").forEach((button) => {
        button.setAttribute("aria-pressed", String(button === selectedTab));
      });
      if (selected === "responses") await loadResponses(currentPage);
      return;
    }
    const action = event.target.closest("[data-response-action]");
    if (!action) return;
    if (action.dataset.responseAction === "refresh") return loadResponses(currentPage);
    if (action.dataset.responseAction === "page") return loadResponses(Number(action.dataset.page));
    if (action.dataset.responseAction !== "detail") return;
    const row = document.getElementById(action.getAttribute("aria-controls"));
    const opening = row.hidden;
    row.hidden = !opening;
    action.setAttribute("aria-expanded", String(opening));
    if (!opening || row.dataset.loaded) return;
    const details = row.querySelector("[data-response-detail]");
    details.textContent = "Cargando datos…";
    action.disabled = true;
    try {
      const data = await responseData({ response: action.dataset.responseId });
      details.innerHTML = data.html;
      row.dataset.loaded = "true";
    } catch (error) {
      details.textContent = error.message;
    } finally {
      action.disabled = false;
    }
  });
  document.getElementById("builder-response-search").addEventListener("submit", (event) => {
    event.preventDefault();
    loadResponses(1);
  });
  window.addEventListener("focus", () => {
    if (!panel.hidden && !document.querySelector(".response-document-dialog[open]") && !list.querySelector('[data-response-action="detail"][aria-expanded="true"]')) loadResponses(currentPage);
  });
})();
