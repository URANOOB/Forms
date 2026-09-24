# Respuestas por estado

La sección **Respuestas** abre un tablero ligero con cuatro columnas de 300–320 px,
desplazamiento horizontal y tarjetas centradas en el respondiente. Permite alternar
entre **Estado** y **Tabla**. Ambas vistas conservan la búsqueda y los filtros de formulario,
estado y fecha. Los contadores corresponden a todos los resultados filtrados;
cada columna muestra hasta 12 tarjetas y ofrece un enlace a la tabla completa
de ese estado cuando hay más resultados.

| Estado | Significado | Acciones disponibles |
| --- | --- | --- |
| Recibida | Envío nuevo pendiente de revisión | Iniciar revisión |
| En revisión | Se está comprobando la información | Validar o rechazar |
| Validada | Información revisada y aceptada | Reabrir revisión |
| Rechazada | Respuesta no aceptada | Reabrir revisión |

**Revisar** abre los datos recibidos. El menú **⋯** ofrece las transiciones permitidas,
marcar una incidencia, descargar CSV y consultar el historial. También se puede
gestionar la revisión desde el detalle de la respuesta. Rechazar exige un motivo
de hasta 2.000 caracteres; las demás acciones admiten un comentario opcional.
No se cambia de estado por abrir o consultar una respuesta.

Cada transición registra estado anterior, nuevo estado, usuario, fecha y
comentario. El historial se consulta en el detalle. Las respuestas existentes
conservan su estado y no se inventan eventos de revisión anteriores.

El cambio de estado requiere el permiso existente `submissions.change_submission`.
Se valida en el servidor, con CSRF y bloqueo de la respuesta dentro de una
transacción. Una revisión desactualizada devuelve un conflicto y pide recargar.

La edición de datos se gestiona por separado. Cambiar los datos de una respuesta
validada o rechazada la devuelve a **En revisión** y registra el motivo automático.
Guardar sin modificar datos conserva el estado. Cualquier cambio en los datos
invalida los formularios de revisión abiertos previamente.

La migración `submissions.0003` añade la revisión de concurrencia y el historial;
se aplica con `uv run python manage.py migrate`.

## Identificación y contexto

Las tarjetas y la tabla muestran el nombre del respondiente, hasta tres datos
relevantes, la fecha y el número real de archivos adjuntos. La detección automática
reconoce etiquetas habituales de nombre, apellidos, documento, orden y contacto;
no utiliza respuestas arbitrarias como nombres. El documento se muestra oculto
salvo los últimos cuatro caracteres. Cuando no hay identificación reconocible se
muestra **Respuesta sin identificación**.

En el constructor, **Configuración → Identificación de respuestas** permite elegir
el título y hasta tres campos, y ocultar parte de cada dato. La configuración se
guarda en el formulario, referenciando las claves estables de los campos. También
se aplica a respuestas anteriores sin alterar sus datos ni su versión. Un campo
ausente en una versión anterior aparece como **Sin dato**. Los valores de selección
se presentan con las etiquetas de la versión que recibió la respuesta.

**Nueva** identifica las respuestas recibidas pendientes de revisión. Las señales
**Requiere atención**, **Documento ilegible**, **Incompleta** y **Duplicado** las marca
explícitamente un revisor, con una explicación obligatoria, desde el detalle. Se
pueden retirar al resolverlas y sus cambios se registran en el historial. No se
deducen automáticamente incidencias ni urgencias clínicas.

La tabla permite seleccionar respuestas de la página y descargarlas en CSV.
El menú de cada tarjeta también permite la descarga individual. El CSV contiene
los datos completos de las respuestas autorizadas, incluyendo los documentos sin
ocultar y los nombres de archivos; no incluye el contenido binario de los adjuntos.
Los valores recibidos se protegen frente a su interpretación como fórmulas.

`forms.0011` añade la configuración de identificación y `submissions.0004` las
señales de revisión. Ambas migraciones se aplican con el comando habitual.

## Comprobaciones

El detalle presenta las respuestas como datos de lectura: secciones plegables sin
cajas, dos columnas para valores cortos y ancho completo para direcciones, textos
largos, cuadrículas y documentos. El índice **Contenido** abre la sección elegida
y desplaza el foco a su encabezado. También permite expandir o contraer todo.

Las fechas, los números de documento y los teléfonos se formatean solo al mostrarse;
los valores guardados y las descargas conservan los datos originales. Los campos
vacíos indican **No proporcionado**; `0` y `No` siguen siendo respuestas válidas.
Se conservan los títulos de las secciones. Solo los títulos genéricos, como
**Sección 1**, reciben una descripción según sus campos reconocibles.

El encabezado muestra el título de la versión recibida, el respondiente cuando
está identificado y los datos del envío. **⋯** reúne descargar CSV, ver la versión
(con permiso) y eliminar (con permiso y confirmación). El panel de revisión usa
botones contextuales y muestra el número de cambios en el acceso al historial.

`uv run python manage.py test apps.submissions.tests.test_presentation --noinput`
comprueba formatos, conservación de valores, permisos, adjuntos, opciones y secciones.

`uv run --with playwright python manage.py test apps.submissions.tests.browser_detail --noinput`
verifica navegación, secciones plegables, vista previa, descarga, acciones de revisión
y presentación móvil en Edge. Guarda capturas con datos ficticios en el directorio temporal.

`uv run python manage.py test apps.submissions.tests.test_review --noinput`
comprueba transiciones, permisos, CSRF, motivos obligatorios, historial, filtros,
contadores, edición, eliminación y cambios simultáneos.

`uv run python manage.py test apps.submissions.tests.test_summary --noinput`
comprueba identificación, ocultación de documentos, configuración sobre versiones
anteriores, etiquetas de opciones, número de consultas, incidencias y descargas.

`uv run --with playwright python manage.py test apps.submissions.tests.browser_review --noinput`
recorre el flujo completo en Edge, alterna tablero y tabla y comprueba la vista
móvil. Utiliza una base de pruebas y guarda capturas en el directorio temporal.
