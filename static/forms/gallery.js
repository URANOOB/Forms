(() => {
  const gallery = document.getElementById("form-grid");
  const buttons = document.querySelectorAll("[data-view]");
  const setView = (view) => {
    gallery.dataset.layout = view === "list" ? "list" : "grid";
    buttons.forEach((button) => {
      const active = button.dataset.view === gallery.dataset.layout;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  };
  if (!gallery) return;
  const filters = document.querySelector(".gallery-filter-menu");
  document.addEventListener("click", (event) => {
    if (filters.open && !filters.contains(event.target)) filters.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && filters.open) {
      filters.open = false;
      filters.querySelector("summary").focus();
    }
  });
  // Enter works even when the filter panel (and its submit button) is closed.
  const search = document.querySelector('.gallery-search input');
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      search.form.requestSubmit();
    }
  });
  try {
    setView(localStorage.getItem("forms-gallery-view"));
  } catch {
    setView("grid");
  }
  buttons.forEach((button) =>
    button.addEventListener("click", () => {
      setView(button.dataset.view);
      try {
        localStorage.setItem("forms-gallery-view", button.dataset.view);
      } catch {
        /* Preferencia opcional. */
      }
    }),
  );
  const positionMenu = (menu) => {
    if (!menu.open) return;
    const panel = menu.querySelector(".card-menu-panel");
    const anchor = menu.querySelector("summary").getBoundingClientRect();
    const viewport = window.visualViewport;
    const leftEdge = viewport?.offsetLeft || 0;
    const topEdge = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || window.innerHeight;
    const margin = 12;
    const gap = 6;
    if (anchor.bottom < topEdge || anchor.top > topEdge + height) {
      menu.open = false;
      return;
    }
    const panelWidth = Math.min(250, width - margin * 2);
    Object.assign(panel.style, {
      position: "fixed",
      margin: "0",
      boxSizing: "border-box",
      zIndex: "2147483647",
      width: `${panelWidth}px`,
      minWidth: "0",
      right: "auto",
      bottom: "auto",
      left: `${Math.max(leftEdge + margin, Math.min(anchor.right - panelWidth, leftEdge + width - panelWidth - margin))}px`,
    });
    const below = Math.max(0, topEdge + height - anchor.bottom - margin - gap);
    const above = Math.max(0, anchor.top - topEdge - margin - gap);
    const desired = Math.min(panel.scrollHeight + 2, 420);
    const opensUp = below < desired && above > below;
    const available = opensUp ? above : below;
    panel.style.maxHeight = `${Math.min(420, available)}px`;
    const actualHeight = panel.getBoundingClientRect().height;
    panel.style.top = `${opensUp ? anchor.top - gap - actualHeight : anchor.bottom + gap}px`;
  };
  document.querySelectorAll(".card-menu").forEach((menu) => {
    const panel = menu.querySelector(".card-menu-panel");
    // The browser's top layer keeps the menu above sticky footers and clipping ancestors.
    const supportsPopover = typeof panel.showPopover === "function";
    if (supportsPopover) panel.setAttribute("popover", "manual");
    menu.addEventListener("toggle", () => {
      if (!menu.open) {
        if (supportsPopover && panel.matches(":popover-open")) panel.hidePopover();
        return;
      }
      document.querySelectorAll(".card-menu[open]").forEach((other) => {
        if (other !== menu) other.open = false;
      });
      if (supportsPopover && !panel.matches(":popover-open")) panel.showPopover();
      positionMenu(menu);
    });
  });
  let menuFrame;
  const repositionMenus = (event) => {
    // Scrolling the options must not move or close their own menu.
    if (event?.target instanceof Element && event.target.closest(".card-menu-panel")) return;
    cancelAnimationFrame(menuFrame);
    menuFrame = requestAnimationFrame(() => {
      document.querySelectorAll(".card-menu[open]").forEach(positionMenu);
    });
  };
  document.addEventListener("scroll", repositionMenus, { capture: true, passive: true });
  window.addEventListener("resize", repositionMenus, { passive: true });
  window.visualViewport?.addEventListener("resize", repositionMenus, { passive: true });
  window.visualViewport?.addEventListener("scroll", repositionMenus, { passive: true });
  document.addEventListener("click", (event) => {
    document.querySelectorAll(".card-menu[open]").forEach((menu) => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape")
      document.querySelectorAll(".card-menu[open]").forEach((menu) => {
        menu.open = false;
        menu.querySelector("summary").focus();
      });
  });
  let noticeTimer;
  document.querySelectorAll("[data-copy-url]").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyUrl);
        const notice = document.getElementById("gallery-notice");
        notice.textContent =
          "Enlace copiado. Ya puedes compartir tu formulario.";
        notice.hidden = false;
        clearTimeout(noticeTimer);
        noticeTimer = setTimeout(() => {
          notice.hidden = true;
        }, 4000);
      } catch {
        const dialog = document.getElementById("copy-dialog");
        const input = document.getElementById("copy-fallback");
        input.value = button.dataset.copyUrl;
        dialog.showModal();
        input.select();
      }
      button.closest("details").open = false;
    }),
  );
})();
