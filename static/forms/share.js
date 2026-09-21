document.getElementById("copy-url")?.addEventListener("click", async () => {
  const input = document.getElementById("share-url");
  const status = document.getElementById("copy-status");
  input.select();
  try {
    await navigator.clipboard.writeText(input.value);
    status.textContent = "Enlace copiado.";
  } catch {
    status.textContent =
      "Enlace seleccionado. Cópialo con Ctrl+C o con el menú de tu dispositivo.";
  }
});
