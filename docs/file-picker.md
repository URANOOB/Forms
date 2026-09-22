# Selección de documentos

Los campos FILE y DOCUMENT de la vista pública permiten seleccionar o arrastrar
archivos. Cada archivo se revisa en una tarjeta con nombre, formato y tamaño;
**Confirmar archivo** lo incorpora a la selección que se enviará con el formulario.
**Quitar** lo retira. No se realiza una carga de archivos anticipada.

Las imágenes tienen miniatura; los PDF usan el visor integrado del navegador y un
enlace para abrirlos en otra pestaña. TXT y CSV muestran un fragmento de hasta 4 KB.
Los formatos de Office muestran una tarjeta informativa sin previsualización.
Las vistas previas son locales, sin servicios externos, y sus URL temporales se
liberan al retirar los archivos o abandonar la página.

Se respetan los formatos, tamaño y cantidad configurados, contando los adjuntos
conservados al editar una respuesta. Los archivos pendientes de confirmación impiden
avanzar o enviar. El servidor conserva su validación de tamaño, extensión y firma.
La selección nativa queda disponible si JavaScript o DataTransfer no están disponibles.
