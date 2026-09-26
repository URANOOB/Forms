(() => {
  const topbar = document.getElementById("platform-topbar");
  if (!topbar) return;

  const search = topbar.querySelector(".platform-global-search");
  const input = search.querySelector("input[name='q']");
  const suggestions = search.querySelector(".platform-search-suggestions");
  const notifications = topbar.querySelector(".platform-notifications");
  const bell = topbar.querySelector(".platform-notifications-button");
  const panel = topbar.querySelector(".platform-notifications-panel");
  const list = topbar.querySelector(".platform-notifications-list");
  const badge = topbar.querySelector(".platform-notification-count");
  const announcement = topbar.querySelector(".platform-activity-announcement");
  let searchTimer;
  let searchRequest;
  let previousUnread = null;

  function resultLink(result, className) {
    const link = document.createElement("a");
    link.className = className;
    link.href = result.url;
    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = result.icon;
    const content = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = result.title;
    const detail = document.createElement("small");
    detail.textContent = className === "platform-search-result"
      ? `${result.type} · ${result.detail || ""}`
      : `${result.detail} · ${result.time}`;
    content.append(title, detail);
    link.append(icon, content);
    if (result.unread) link.dataset.unread = "true";
    return link;
  }

  function message(target, value) {
    const paragraph = document.createElement("p");
    paragraph.textContent = value;
    target.replaceChildren(paragraph);
  }

  async function searchSuggestions() {
    const query = input.value.trim();
    searchRequest?.abort();
    if (!query) {
      suggestions.hidden = true;
      return;
    }
    searchRequest = new AbortController();
    try {
      const url = new URL(search.action, window.location.href);
      url.searchParams.set("q", query);
      url.searchParams.set("format", "json");
      const response = await fetch(url, { signal: searchRequest.signal, credentials: "same-origin" });
      if (!response.ok) throw new Error("search_failed");
      const data = await response.json();
      if (input.value.trim() !== query) return;
      suggestions.replaceChildren(...data.results.map((item) => resultLink(item, "platform-search-result")));
      if (!data.results.length) message(suggestions, "No se encontraron coincidencias.");
      const all = document.createElement("a");
      all.className = "platform-search-all";
      all.href = `${search.action}?q=${encodeURIComponent(query)}`;
      all.textContent = "Ver todos los resultados";
      suggestions.append(all);
      suggestions.hidden = false;
    } catch (error) {
      if (error.name !== "AbortError") suggestions.hidden = true;
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchSuggestions, 250);
  });
  input.addEventListener("focus", () => { if (input.value.trim()) searchSuggestions(); });
  search.addEventListener("submit", (event) => {
    if (!input.value.trim()) event.preventDefault();
  });

  async function refreshActivity() {
    if (document.hidden) return;
    try {
      const response = await fetch(topbar.dataset.activityUrl, { credentials: "same-origin" });
      if (!response.ok) throw new Error("activity_failed");
      const data = await response.json();
      badge.hidden = !data.unread;
      badge.textContent = data.unread >= 99 ? "99+" : String(data.unread);
      bell.setAttribute("aria-label", data.unread ? `Notificaciones, ${data.unread} sin leer` : "Notificaciones, ninguna sin leer");
      if (previousUnread !== null && data.unread > previousUnread) {
        announcement.textContent = `${data.unread - previousUnread} actividad nueva`;
      }
      previousUnread = data.unread;
      list.replaceChildren(...data.items.map((item) => resultLink(item, "platform-notification-item")));
      if (!data.items.length) message(list, "Todavía no hay actividad reciente.");
    } catch {
      if (!panel.hidden) message(list, "No se pudo cargar la actividad.");
    }
  }

  async function markSeen() {
    const csrf = topbar.querySelector("input[name='csrfmiddlewaretoken']")?.value;
    if (!csrf) return;
    try {
      const response = await fetch(topbar.dataset.activityUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrf },
      });
      if (!response.ok) return;
      badge.hidden = true;
      previousUnread = 0;
      bell.setAttribute("aria-label", "Notificaciones, ninguna sin leer");
      list.querySelectorAll("[data-unread]").forEach((item) => { delete item.dataset.unread; });
    } catch { /* The next refresh will retry the visible state. */ }
  }

  bell.addEventListener("click", async () => {
    panel.hidden = !panel.hidden;
    bell.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) {
      await refreshActivity();
      await markSeen();
    }
  });
  document.addEventListener("click", (event) => {
    if (!notifications.contains(event.target)) {
      panel.hidden = true;
      bell.setAttribute("aria-expanded", "false");
    }
    if (!search.contains(event.target)) suggestions.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      panel.hidden = true;
      suggestions.hidden = true;
      bell.setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshActivity(); });
  refreshActivity();
  setInterval(refreshActivity, 30000);
})();
