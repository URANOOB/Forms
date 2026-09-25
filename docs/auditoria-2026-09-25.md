# Auditoría del proyecto — 25 de septiembre de 2026

> Actualización: el [seguimiento de auditoría](auditoria-seguimiento.md) resuelve la
> limitación de solicitudes, el almacenamiento obligatorio en producción, la propiedad
> de revisión, la papelera y la identidad/límite de columnas Excel mencionados aquí.
> Este documento conserva el estado de la primera auditoría.

Se revisaron la recepción pública, el constructor, las versiones, las condiciones,
la edición y revisión de respuestas, los adjuntos, los reportes, los permisos,
la configuración de despliegue y los componentes principales de la interfaz.
Se aplicaron correcciones locales y se añadieron pruebas de regresión. No se
desplegaron cambios ni se modificaron Supabase, R2 o cuentas de producción.

## Hallazgos corregidos

| Prioridad | Problema y efecto | Corrección y evidencia |
| --- | --- | --- |
| Alta | Los campos NUMBER convertían a float: `9007199254740993` podía almacenarse redondeado. | Enteros exactos y rechazo explícito fuera del rango compartido por Python/JavaScript: 0–9007199254740991. Pruebas de validación, persistencia y navegador. Los umbrales de versiones históricas siguen siendo legibles. |
| Alta | Varias cargas válidas individualmente podían exceder el límite de la petición en Vercel y terminar en un rechazo antes de llegar a Django. | Presupuesto agregado de 4.000.000 bytes con reserva multipart cuando `VERCEL=1`, comprobado en navegador y servidor. El navegador conserva lo escrito y explica cómo reducir el envío. |
| Media | Un ZIP cualquiera renombrado DOCX/XLSX superaba la comprobación de firma. | Validación de partes Office, formato ZIP, macros VBA, cifrado y tamaño descomprimido declarado. Un XLSX real pasa; ZIP renombrado, truncado y contenedor con macros se rechazan. |
| Media | Caracteres de control aceptados en las respuestas rompían la generación de Excel. | Representación visible `\uXXXX` de caracteres incompatibles con XML; fórmulas siguen tratadas como texto. Verificado guardando y reabriendo el Excel generado por la ruta administrativa. |
| Media | El panel de respuestas aceptaba una redirección de sesión como HTML válido; las peticiones antiguas podían alterar contenido o quitar el indicador de carga de una petición nueva. | Comprobación de redirecciones y tipo de contenido, identidad de petición y cancelación antes de cambiar el DOM. Prueba de respuestas de red fuera de orden. |
| Media | La lista de respuestas del constructor podía aplicar una respuesta antigua después de una búsqueda nueva. | Se comprueba la cancelación también después de recibir y procesar el JSON. |
| Media | Las condiciones recorrían todos los grupos para cada campo y repetían ese trabajo por sección. | Índices de grupos por campo y campos por sección, tanto en Python como en JavaScript. Se mantiene el orden original de las reglas. |
| Media | Cada dato escalar enviado generaba un INSERT independiente. | Inserción por lotes dentro de la misma transacción. Prueba: 20 respuestas de campos se escriben con un solo INSERT; el reintento mantiene una sola Submission. |
| Baja | El progreso contaba secciones que el recorrido omitía. | El indicador usa la posición y longitud del recorrido aplicable. Verificado un formulario de tres secciones que recorre solo dos. |
| Baja | Los enlaces del resumen de errores de grupos de radio podían apuntar a un fragmento vacío. | Anclaje al identificador del widget y enfoque de su primer control. Verificado con errores devueltos por el servidor. |
| Media | El README describía cuatro roles antiguos, un Visor de solo lectura y un guardado/publicación diferente del comportamiento real. | Documentación alineada con `docs/users.md` y el código: Administrador y Visor; ambos gestionan formularios y respuestas, solo Administrador gestiona usuarios. Guardar un formulario publicado activa una nueva versión conservando el acceso. |
| Media | Las pruebas de navegador no se ejecutaban en CI y varias seguían buscando la interfaz anterior. | Casos actualizados para la UI vigente, navegador Chromium portable y ejecución incorporada al workflow. También se versionaron las referencias a los JavaScript modificados para invalidar caché. |

## Comprobaciones y resultados

- Base inicial: **171 pruebas Django aprobadas** sobre PostgreSQL local.
- Después de los cambios: **183 pruebas Django aprobadas**; incluyen 12 nuevas
  pruebas de precisión, archivos, permisos, filtros, exportación, límites e idempotencia.
- **8 pruebas de navegador aprobadas**: formularios públicos, validación cliente/servidor, bienvenida,
  saltos, archivos pendientes, límites agregados, concurrencia del panel, galería,
  métricas, lectura de respuestas, vista previa, revisión, descarga CSV y constructor.
- El script independiente de importación de catálogos pasa: reemplazo, reintento,
  cancelación, errores, peticiones pendientes y reapertura.
- Inspección de capturas y comprobaciones de ancho a **390 px**, además de escritorio
  y modo oscuro en los componentes cubiertos. No equivale a una certificación de
  accesibilidad ni a pruebas exhaustivas en Safari/Firefox o dispositivos físicos.
- `manage.py check`, `makemigrations --check --dry-run`, Ruff, comprobación de formato,
  sintaxis de JavaScript y `git diff --check`: correctos.
- `check --deploy`: correcto usando configuración de producción y credenciales
  sintéticas. No verifica las variables ni el proxy del despliegue real.
- `collectstatic`: correcto. Los tres avisos de duplicación de scripts administrativos
  corresponden a las sustituciones de Django Unfold, instalado antes del admin Django.
- `pip-audit` sobre las dependencias de producción fijadas en `uv.lock`: **sin
  vulnerabilidades conocidas reportadas**. `npm audit --package-lock-only`: **0**.
  Estos resultados no descartan vulnerabilidades desconocidas o de lógica propia.
- Solo `.env.example` está versionado entre los archivos `.env*`; no se imprimieron
  ni se incluyeron credenciales de producción en este informe. No se auditó todo el historial Git.

Medición local del evaluador Python: un esquema sintético de 200 campos, 50 secciones
y 300 reglas pasó de **119,43 ms a 16,43 ms** por recorrido; se comparó contra el código
de HEAD y se comprobó igualdad de resultados. Es una mejora de aproximadamente **7,3×**
en esa operación, no una promesa sobre el tiempo total de una petición en producción.
Se tomó el menor tiempo de tres repeticiones de tres recorridos para cada implementación.

## Riesgos y trabajo pendiente

| Prioridad | Evidencia y alcance | Siguiente medida |
| --- | --- | --- |
| Alta | No hay limitación de intentos de autenticación ni de creación de envíos en el código. Los tokens y CSRF no impiden que un cliente solicite tokens nuevos repetidamente. No se inspeccionaron reglas WAF externas. | Verificar/configurar límites compartidos en el proveedor para login y formularios; combinar límites con controles de abuso adecuados al volumen real y a usuarios que compartan IP. No usar un contador local por proceso como protección de producción. |
| Alta | R2 se escribe dentro de la transacción que bloquea el formulario. Una carga lenta serializa otros envíos del mismo formulario; además, los archivos grandes siguen atravesando Vercel. | Diseñar cargas directas firmadas a R2, con validación y asociación final atómica. La protección agregada añadida mitiga el rechazo de envíos, pero no sustituye esa arquitectura ni cubre aún las cargas del constructor/importador. |
| Media | `report_columns()` recorre las respuestas y carga opciones/archivos para descubrir columnas, incluso para mostrar una página pequeña. Las búsquedas por etiquetas de opciones también recorren respuestas en Python. | Medir con el volumen real y planes SQL; derivar columnas del esquema y trasladar las coincidencias a consultas/indexación apropiadas. No se añadieron índices sin evidencia de carga. |
| Media | Excel admite 32.767 caracteres por celda. Un experimento local con 40.000 caracteres almacenó solo 32.767. La agrupación de varias preguntas con el mismo título puede superar ese tamaño aunque cada respuesta individual sea válida. | Antes de usar XLSX como archivo íntegro de textos extensos, añadir división explícita en celdas/hoja de continuación o rechazo explicativo y exportación alternativa. Este límite permanece pendiente; la base conserva el texto original. |
| Media | La validación de archivos comprueba extensiones, firmas y estructura básica; no analiza malware ni garantiza la integridad completa de cada documento. | Incorporar cuarentena/análisis de archivos si el contexto operativo lo exige. Mantener bucket privado y descarga autenticada. |
| Media | La base y el almacenamiento de objetos no comparten transacción. Si falla la eliminación compensatoria de un archivo tras un error, puede quedar un objeto huérfano; un ZIP puede quedar incompleto si un objeto falla durante el streaming. | Añadir reconciliación de objetos, registro/reintento de limpieza y pruebas de fallo de almacenamiento real. Los eventos de descarga actuales representan solicitudes, no confirmaciones de transferencia completada. |
| Media | Los permisos por formulario no aíslan instituciones. «Visor» puede editar y eliminar por decisión expresa del diseño actual. | Revisar que la asignación de ese rol y el acceso global sean adecuados para la operación. No se cambió unilateralmente el modelo de permisos documentado. |
| Media | La validación nueva evita redondeos futuros; datos ya redondeados no recuperan su valor original por cambiar el tipo de campo. | Identificar formularios que usen NUMBER para documentos largos o con ceros iniciales y contrastar sus datos con la fuente antes de corregirlos. |

También quedan fuera de esta ejecución las copias y restauraciones reales, la carga
concurrente contra producción, la configuración efectiva del bucket/proxy, un pentest
externo y las pruebas de despliegue en Workers. No se realizaron cambios de esquema.

## Referencias

- [Límites de Vercel Functions](https://vercel.com/docs/functions/limitations): límite
  de payload del proveedor que motivó el presupuesto agregado.
- [Seguridad en Django](https://docs.djangoproject.com/en/5.2/topics/security/):
  protección de contenido subido, configuración del servidor y ausencia de throttling
  de autenticación incorporado.

Las pruebas nuevas están en `apps/submissions/tests/test_audit.py` y
`apps/submissions/tests/browser_public_audit.py`. Para reproducirlas, usar siempre una
base PostgreSQL dedicada/local y `FILE_STORAGE=local`; no cargar `.env.supabase`.
