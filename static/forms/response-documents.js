(() => {
  const dialog = document.createElement("dialog");
  dialog.className = "response-document-dialog";
  dialog.setAttribute("aria-labelledby", "response-document-title");
  dialog.innerHTML = `
    <header class="response-document-header">
      <div class="response-document-title"><p>VISTA PREVIA DEL DOCUMENTO</p><h2 id="response-document-title"></h2></div>
      <a class="response-document-download"><span class="material-symbols-outlined" aria-hidden="true">download</span>Descargar</a>
      <button type="button" class="response-document-close" aria-label="Cerrar vista previa" autofocus><span class="material-symbols-outlined" aria-hidden="true">close</span></button>
    </header>
    <div class="response-document-body"></div>
    <footer class="response-document-footer" role="status"></footer>`;
  document.body.append(dialog);
  const title = dialog.querySelector("h2");
  const download = dialog.querySelector("a");
  const body = dialog.querySelector(".response-document-body");
  const footer = dialog.querySelector("footer");
  let controller = null;
  let objectURL = null;
  let opener = null;

  function release() {
    controller?.abort();
    controller = null;
    body.replaceChildren();
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = null;
  }

  function message(text) {
    const paragraph = document.createElement("p");
    paragraph.className = "response-document-message";
    paragraph.textContent = text;
    body.replaceChildren(paragraph);
  }

  dialog.querySelector("button").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener("close", () => {
    release();
    if (opener?.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  });

  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-document-url]");
    if (!trigger) return;
    const url = new URL(trigger.dataset.documentUrl, location.href);
    if (url.origin !== location.origin) return;
    release();
    opener = trigger;
    title.textContent = trigger.dataset.documentName;
    download.href = url.href;
    download.setAttribute("aria-label", `Descargar ${trigger.dataset.documentName}`);
    footer.textContent = "Cargando documento…";
    message("Preparando vista previa…");
    dialog.showModal();
    const kind = trigger.dataset.documentKind;
    if (!["image", "pdf", "text"].includes(kind)) {
      message("Este formato no dispone de vista previa. Puede descargar el archivo para abrirlo en la aplicación correspondiente.");
      footer.textContent = "Archivo disponible para descargar.";
      return;
    }
    const pending = new AbortController();
    controller = pending;
    try {
      const previewUrl = new URL(url.href);
      previewUrl.searchParams.set("preview", "1");
      const response = await fetch(previewUrl, { signal: pending.signal, credentials: "same-origin", cache: "no-store" });
      if (!response.ok || response.redirected || !response.headers.get("content-disposition")?.startsWith("attachment")) {
        throw new Error("No se pudo abrir el documento. Compruebe su sesión y vuelva a intentarlo.");
      }
      const blob = await response.blob();
      if (pending.signal.aborted) return;
      body.replaceChildren();
      if (kind === "text") {
        const text = await blob.slice(0, 65536).text();
        if (pending.signal.aborted) return;
        const preview = document.createElement("pre");
        preview.textContent = text;
        preview.tabIndex = 0;
        preview.setAttribute("aria-label", "Contenido del documento");
        body.append(preview);
        footer.textContent = blob.size > 65536 ? "Vista parcial. Descargue el archivo para consultar todo el contenido." : "Vista previa del contenido del archivo.";
      } else {
        const mimeTypes = { PDF: "application/pdf", PNG: "image/png", JPG: "image/jpeg", JPEG: "image/jpeg", WEBP: "image/webp" };
        const mime = mimeTypes[trigger.dataset.documentExtension];
        if (!mime) throw new Error("Este formato no dispone de vista previa.");
        objectURL = URL.createObjectURL(new Blob([blob], { type: mime }));
        if (kind === "image") {
          const preview = document.createElement("img");
          preview.alt = trigger.dataset.documentName;
          preview.addEventListener("error", () => {
            if (pending.signal.aborted) return;
            message("No se pudo mostrar esta imagen. Puede descargar el archivo para revisarlo.");
            footer.textContent = "Vista previa no disponible.";
          });
          preview.src = objectURL;
          body.append(preview);
        } else {
          const preview = document.createElement("object");
          preview.type = "application/pdf";
          preview.data = objectURL;
          preview.setAttribute("aria-label", `Vista previa de ${trigger.dataset.documentName}`);
          const fallback = document.createElement("p");
          fallback.className = "response-document-message";
          fallback.textContent = "Su navegador no permite mostrar este PDF. Utilice Descargar para abrirlo.";
          preview.append(fallback);
          body.append(preview);
        }
        footer.textContent = "Si el documento no se muestra, puede descargarlo para abrirlo en su dispositivo.";
      }
    } catch (error) {
      if (pending.signal.aborted) return;
      message(error.message || "No se pudo cargar el documento.");
      footer.textContent = "Cierre el visor e intente abrir el archivo de nuevo.";
    }
  });
  window.addEventListener("pagehide", release);
})();
