(() => {
  const openSection = (id, navigate = false) => {
    const section = document.getElementById(id);
    if (!section?.classList.contains("response-section")) return;
    section.open = true;
    if (navigate) {
      section.querySelector("summary").focus({ preventScroll: true });
      section.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    }
  };
  document.addEventListener("click", (event) => {
    const control = event.target.closest("[data-response-expand]");
    if (control) {
      control.closest(".response-details").querySelectorAll(".response-section").forEach((section) => {
        section.open = control.dataset.responseExpand === "true";
      });
    }
    const link = event.target.closest("[data-response-section-link]");
    if (link) {
      event.preventDefault();
      history.replaceState(null, "", link.hash);
      openSection(link.hash.slice(1), true);
    }
  });
  const openHash = () => openSection(location.hash.slice(1), true);
  window.addEventListener("hashchange", openHash);
  openHash();
})();
