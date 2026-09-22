(() => {
  if (!HTMLElement.prototype.showPopover) return;
  const form = document.getElementById("public-form");
  if (!form) return;
  const controls = [...form.querySelectorAll('.field select:not([multiple])')].filter((select) => select.size <= 1);
  let opened = null;
  const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");

  function close() {
    if (!opened) return;
    const picker = opened;
    opened = null;
    picker.menu.hidePopover();
    picker.select.setAttribute("aria-expanded", "false");
    picker.select.removeAttribute("aria-activedescendant");
    picker.searchInput?.removeAttribute("aria-activedescendant");
    picker.searchInput?.setAttribute("aria-expanded", "false");
  }
  function position() {
    if (!opened) return;
    const { select, menu } = opened;
    const rect = select.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || window.innerHeight;
    const below = top + height - rect.bottom - 16;
    const above = rect.top - top - 16;
    const downward = below >= 220 || below >= above;
    menu.style.width = `${Math.min(rect.width, width - 24)}px`;
    menu.style.maxHeight = `${Math.max(80, Math.min(320, height - 24, downward ? below : above))}px`;
    const size = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left + 12, Math.min(rect.left, left + width - size.width - 12))}px`;
    menu.style.top = `${Math.max(top + 12, Math.min(downward ? rect.bottom + 6 : rect.top - size.height - 6, top + height - size.height - 12))}px`;
  }
  function highlight(picker, index, scroll = true) {
    picker.index = index;
    for (const item of picker.items) item.classList.toggle("is-active", +item.dataset.index === index);
    const item = picker.items.find((item) => +item.dataset.index === index && !item.hidden);
    const control = picker.searchInput || picker.select;
    if (item) {
      control.setAttribute("aria-activedescendant", item.id);
      if (scroll) item.scrollIntoView({ block: "nearest" });
    } else control.removeAttribute("aria-activedescendant");
  }
  function filter(picker) {
    const query = normalize(picker.searchInput.value.trim());
    let count = 0;
    for (const item of picker.items) {
      const option = picker.select.options[+item.dataset.index];
      item.hidden = Boolean(query) && (!option.value || !normalize(option.textContent).includes(query));
      if (!item.hidden && option.value && item.getAttribute("aria-disabled") !== "true") count++;
    }
    picker.resultStatus.textContent = count ? `${count} ${count === 1 ? "opción disponible" : "opciones disponibles"}` : "No se encontraron coincidencias";
    const first = picker.items.find((item) => !item.hidden && item.getAttribute("aria-disabled") !== "true");
    highlight(picker, first ? +first.dataset.index : -1, false);
    position();
  }
  function navigate(picker, key) {
    const available = picker.items.filter((item) => !item.hidden && item.getAttribute("aria-disabled") !== "true");
    const current = available.findIndex((item) => +item.dataset.index === picker.index);
    const step = { ArrowDown: 1, ArrowUp: -1, PageDown: 5, PageUp: -5 }[key] || 0;
    const next = key === "Home" ? 0 : key === "End" ? available.length - 1 : Math.max(0, Math.min(available.length - 1, current + step));
    if (available[next]) highlight(picker, +available[next].dataset.index);
  }
  function choose(picker, index) {
    const option = picker.select.options[index];
    if (!option || option.disabled || option.parentElement.disabled || picker.select.disabled) return;
    picker.select.selectedIndex = index;
    close();
    picker.select.dispatchEvent(new Event("input", { bubbles: true }));
    picker.select.dispatchEvent(new Event("change", { bubbles: true }));
    if (!picker.select.disabled && !picker.select.closest("[hidden]")) picker.select.focus({ preventScroll: true });
  }
  function open(picker) {
    if (picker.select.disabled) return;
    close();
    picker.list.replaceChildren();
    if (picker.searchInput) picker.searchInput.value = "";
    picker.items = [];
    for (const [index, option] of [...picker.select.options].entries()) {
      if (option.hidden) continue;
      const item = document.createElement("div");
      item.className = "form-dropdown-option";
      item.id = `${picker.menu.id}-option-${index}`;
      item.dataset.index = index;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(option.selected));
      item.setAttribute("aria-disabled", String(option.disabled || Boolean(option.parentElement.disabled)));
      if (!option.value) item.classList.add("is-placeholder");
      const label = document.createElement("span");
      label.textContent = option.textContent;
      label.className = "form-dropdown-label";
      if (option.dataset.choiceImage) {
        const thumbnail = document.createElement("img");
        thumbnail.src = option.dataset.choiceImage;
        thumbnail.alt = "";
        thumbnail.className = "form-dropdown-thumbnail";
        item.append(thumbnail);
      }
      const mark = document.createElement("span");
      mark.className = "form-dropdown-check";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = "✓";
      item.append(label, mark);
      picker.list.append(item);
      picker.items.push(item);
    }
    opened = picker;
    picker.menu.showPopover();
    picker.select.setAttribute("aria-expanded", "true");
    if (picker.searchInput) {
      picker.searchInput.setAttribute("aria-expanded", "true");
      filter(picker);
      picker.searchInput.focus({ preventScroll: true });
    }
    position();
    const selected = picker.items.find((item) => item.getAttribute("aria-selected") === "true" && item.getAttribute("aria-disabled") !== "true")
      || picker.items.find((item) => item.getAttribute("aria-disabled") !== "true");
    highlight(picker, selected ? +selected.dataset.index : -1);
  }
  controls.forEach((select, id) => {
    const menu = document.createElement("div");
    menu.className = "form-dropdown-menu";
    menu.id = `form-dropdown-${id}`;
    menu.setAttribute("popover", "manual");
    const label = select.labels?.[0]?.textContent.trim() || "Opciones";
    const searchable = select.dataset.searchable === "true";
    const list = searchable ? document.createElement("div") : menu;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", label);
    if (searchable) {
      menu.classList.add("form-dropdown-searchable");
      list.className = "form-dropdown-results";
      list.id = `${menu.id}-results`;
    }
    document.body.append(menu);
    select.classList.add("form-dropdown-select");
    select.setAttribute("aria-controls", list.id);
    select.setAttribute("aria-haspopup", "listbox");
    select.setAttribute("aria-expanded", "false");
    const picker = { select, menu, list, items: [], index: -1, search: "", searchTime: 0 };
    if (searchable) {
      const header = document.createElement("div");
      header.className = "form-dropdown-search-header";
      const searchInput = document.createElement("input");
      searchInput.type = "search";
      searchInput.placeholder = "Buscar una opción…";
      searchInput.autocomplete = "off";
      searchInput.spellcheck = false;
      searchInput.setAttribute("role", "combobox");
      searchInput.setAttribute("aria-label", `Buscar en ${label}`);
      searchInput.setAttribute("aria-controls", list.id);
      searchInput.setAttribute("aria-autocomplete", "list");
      searchInput.setAttribute("aria-expanded", "false");
      const resultStatus = document.createElement("p");
      resultStatus.className = "form-dropdown-result-status";
      resultStatus.setAttribute("role", "status");
      resultStatus.setAttribute("aria-live", "polite");
      header.append(searchInput);
      menu.append(header, list, resultStatus);
      Object.assign(picker, { searchInput, resultStatus });
      searchInput.addEventListener("input", () => filter(picker));
      searchInput.addEventListener("keydown", (event) => {
        if (event.isComposing) return;
        if (event.key === "Escape" || event.key === "Tab") {
          if (event.key === "Escape") event.preventDefault();
          close();
          select.focus({ preventScroll: true });
        } else if (event.key === "Enter") {
          event.preventDefault();
          if (picker.index >= 0) choose(picker, picker.index);
        } else if (["ArrowDown", "ArrowUp", "PageDown", "PageUp"].includes(event.key)) {
          event.preventDefault();
          navigate(picker, event.key);
        }
      });
    }
    let selectedImage = null;
    if ([...select.options].some((option) => option.dataset.choiceImage)) {
      selectedImage = document.createElement("img");
      selectedImage.className = "choice-selected-image";
      selectedImage.hidden = true;
      select.insertAdjacentElement("afterend", selectedImage);
    }
    const sync = () => {
      select.classList.toggle("is-placeholder", !select.value);
      if (!selectedImage) return;
      const selected = select.selectedOptions[0];
      const url = selected?.dataset.choiceImage;
      selectedImage.hidden = !url;
      if (url) {
        selectedImage.src = url;
        selectedImage.alt = `Imagen de ${selected.textContent}`;
      } else selectedImage.removeAttribute("src");
    };
    sync();
    select.addEventListener("change", sync);
    select.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || select.disabled) return;
      event.preventDefault();
      select.focus({ preventScroll: true });
      if (opened === picker) close(); else open(picker);
    });
    // Prevent the operating system menu while retaining the real select for validation.
    select.addEventListener("mousedown", (event) => event.preventDefault());
    select.addEventListener("click", (event) => {
      event.preventDefault();
      if (event.detail === 0) { if (opened === picker) close(); else open(picker); }
    });
    select.addEventListener("invalid", close);
    select.addEventListener("keydown", (event) => {
      if (event.key === "Tab") { close(); return; }
      if (event.key === "Escape" || (event.altKey && event.key === "ArrowUp")) {
        event.preventDefault(); close(); return;
      }
      if (event.key === "Enter" || (event.key === " " && Date.now() - picker.searchTime > 700)) {
        event.preventDefault();
        if (opened === picker) choose(picker, picker.index); else open(picker);
        return;
      }
      const navigation = ["ArrowDown", "ArrowUp", "Home", "End", "PageDown", "PageUp"];
      if (navigation.includes(event.key)) {
        event.preventDefault();
        if (opened !== picker) { open(picker); return; }
        navigate(picker, event.key);
        return;
      }
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        if (picker.searchInput) {
          if (opened !== picker) open(picker);
          picker.searchInput.value += event.key;
          filter(picker);
          picker.searchInput.focus({ preventScroll: true });
          return;
        }
        const now = Date.now();
        picker.search = now - picker.searchTime < 700 ? picker.search + event.key : event.key;
        picker.searchTime = now;
        if (opened !== picker) open(picker);
        const match = picker.items.find((item) => item.getAttribute("aria-disabled") !== "true" && normalize(select.options[+item.dataset.index].textContent).startsWith(normalize(picker.search)));
        if (match) highlight(picker, +match.dataset.index);
      }
    });
    menu.addEventListener("pointerdown", (event) => {
      if (event.target.closest('[role="option"]')) event.preventDefault();
    });
    menu.addEventListener("pointermove", (event) => {
      const item = event.target.closest('[role="option"]');
      if (item && item.getAttribute("aria-disabled") !== "true") highlight(picker, +item.dataset.index, false);
    });
    menu.addEventListener("click", (event) => {
      const item = event.target.closest('[role="option"]');
      if (item) choose(picker, +item.dataset.index);
    });
    form.addEventListener("reset", () => { close(); setTimeout(sync, 0); });
    window.addEventListener("pageshow", sync);
  });
  document.addEventListener("pointerdown", (event) => {
    if (opened && event.target !== opened.select && !opened.menu.contains(event.target)) close();
  });
  document.addEventListener("focusin", (event) => {
    if (opened && event.target !== opened.select && !opened.menu.contains(event.target)) close();
  });
  new MutationObserver(() => {
    if (opened && (opened.select.disabled || opened.select.closest("[hidden]"))) close();
  }).observe(form, { attributes: true, subtree: true, attributeFilter: ["disabled", "hidden"] });
  window.addEventListener("resize", position);
  document.addEventListener("scroll", position, true);
  window.visualViewport?.addEventListener("resize", position);
  window.visualViewport?.addEventListener("scroll", position);
})();
