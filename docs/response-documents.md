# Consulta de respuestas y documentos

El detalle de una respuesta utiliza el mismo diseño en el listado del editor y en
la página individual del administrador. Las secciones agrupan los datos en una,
dos o tres columnas según el espacio disponible. Los párrafos, las cuadrículas y
los archivos ocupan una fila completa.

Cada adjunto muestra su nombre, extensión, tamaño y acciones para consultar o
descargar. «Ver archivo» abre un diálogo accesible que se cierra con su botón o
con Escape. La vista previa admite PDF mediante el visor del navegador, imágenes
PNG/JPEG/WebP y texto TXT/CSV (hasta 64 KiB de contenido visible). Los demás formatos
ofrecen descarga; no se envían documentos a servicios externos.

El visor solicita el archivo al endpoint autenticado existente `response_file`.
No se exponen rutas públicas ni se modifican permisos. Rechaza redirecciones de
sesión y respuestas que no sean adjuntos. El contenido se presenta con tipos MIME
permitidos; el texto se inserta con `textContent`. Las solicitudes pendientes se
cancelan y las URL temporales se liberan al cerrar el visor.

Verificación realizada sin ejecutar tests: sintaxis JavaScript, comprobaciones
de Django y compilación de las plantillas modificadas.
