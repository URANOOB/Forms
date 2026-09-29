# Auditoría del repositorio — 28 de septiembre de 2026

Revisión del árbol de trabajo de `codex/form-drafts-duplicates`, incluidos los cambios locales y archivos nuevos presentes al comenzar. No se modificó código de la aplicación, se desplegó ni se consultaron datos de producción. Este informe complementa las auditorías anteriores; no da por pendientes problemas que el código actual ya resuelve.

Referencia Git al cerrar: `e0076d0`. Durante la revisión, los cambios locales de borradores y duplicados quedaron incorporados en `b6a9965`; se volvió a comprobar que los puntos señalados seguían presentes. El único archivo añadido por esta auditoría es este informe.

Se identificaron **7 fallos**, **2 flujos de recuperación incompletos** y riesgos operativos que siguen abiertos. P1 significa que conviene corregirlo antes de depender de ese flujo; P2, un fallo funcional que debe entrar en la siguiente ronda de correcciones; P3, mantenimiento o documentación.

## Fallos

### 1. [P1] Formularios admitidos por el constructor generan peticiones que Django rechaza

**Evidencia:** `apps/forms/builder.py:196–198`, `apps/forms/question_fields.py:125–128,159–160`, `config/settings/base.py:150–153`, `apps/submissions/views.py:41`.

El constructor admite hasta 200 preguntas; las cuadrículas, hasta 20 filas y 10 columnas; y cada pregunta de adjuntos, hasta 5 archivos. Sin embargo, la configuración no adapta ni tiene en cuenta `DATA_UPLOAD_MAX_NUMBER_FIELDS` y `DATA_UPLOAD_MAX_NUMBER_FILES`. Los valores predeterminados del Django instalado son 1.000 y 100, respectivamente. El límite agregado en bytes no cubre estos límites de cantidad.

**Reproducción aislada sobre el parser real de Django:**

- Seis cuadrículas múltiples de 20 × 10, marcando todas las opciones: cada cuadrícula pasa `GridField.clean()` y `complete()`. La petición contiene 1.200 valores, pesa **97.820 bytes** y termina en `TooManyFieldsSent`.
- Veintiuna preguntas con cinco TXT diminutos cada una: 105 archivos y **13.045 bytes**. El parser termina en `TooManyFilesSent`.

En la ruta pública, el acceso a `request.POST` sucede antes de la validación de respuestas. Por tanto, el rechazo impide guardar y no genera el error de formulario que explica cómo corregirlo. El cliente de borradores tampoco reconoce específicamente ese HTTP 400.

**Corrección:** definir un presupuesto coherente de parámetros y archivos para el formulario completo; validarlo al guardar/publicar y antes del envío. Ajustar los límites del parser a ese presupuesto, manteniéndolos acotados, y ofrecer un mensaje recuperable. Añadir pruebas con peticiones multipart reales en ambos límites.

### 2. [P2] Cambiar ajustes puede perderse sin aviso de cambios pendientes

**Evidencia:** `static/forms/builder.js:35–39,98–100,940–958,1273,1536–1540`.

`snapshot()` incluye preguntas, condiciones, apariencia y textos, pero omite `notifications`, `response_summary` y `duplicate_fields`. Sus controles llaman a `changed()`, que compara esa representación incompleta y sale sin activar `dirty`.

**Reproducción:** abrir un formulario guardado, cambiar únicamente los avisos por correo, la identificación de respuestas o los campos de duplicados y salir. El estado sigue siendo «Formulario guardado» y no se activa la protección de salida. Tampoco se registran estos ajustes para deshacer; la vista previa de un formulario publicado puede omitir el guardado porque ve `dirty === false`.

**Verificación ejecutada:** evaluando la función original de `builder.js`, las tres modificaciones devolvieron `change_detected=false`. Pulsar explícitamente «Guardar cambios» sí envía los ajustes; el fallo está en el seguimiento y el aviso de cambios.

**Corrección:** incluir los tres ajustes en la representación de contenido editable y en el historial, separándolos únicamente de los metadatos de versión/acceso que realmente deben permanecer fuera.

### 3. [P2] Las exportaciones de cuadrículas contienen identificadores internos

**Evidencia:** `apps/submissions/summary.py:91–109`, `apps/submissions/reports.py:47–61`, `apps/submissions/export.py:58–63`. Comparación con la presentación correcta en `apps/submissions/presentation.py:123–135`.

La página de detalle traduce filas y columnas de cuadrículas usando el esquema histórico. CSV, Excel y la vista previa de reportes utilizan `answer_text()`, que para estos diccionarios devuelve JSON sin esa traducción.

**Reproducción verificada:** una respuesta «Calidad: Excelente», con identificadores internos de fila y columna, se exporta como `{"a67b-row-id": "b58a-col-id"}`. Los identificadores generados por el constructor no explican qué respondió la persona. Afecta tanto a cuadrículas simples como múltiples.

**Corrección:** compartir la conversión de cuadrículas entre detalle y exportaciones, conservando siempre las etiquetas de la versión respondida. Verificar tanto CSV como XLSX con cuadrículas simples y múltiples.

### 4. [P2] La detección de duplicados ignora números históricos guardados como float

**Evidencia:** `apps/submissions/duplicates.py:10–19,52–62`; contexto histórico en `docs/auditoria-2026-09-25.md`.

`NUMBER` es un tipo admitido para detectar duplicados, pero `normalized_identity()` acepta únicamente `str` e `int`. La implementación anterior almacenaba números como float, y la auditoría anterior explica que los datos históricos no se convirtieron automáticamente.

**Reproducción verificada con la función original:**

```text
normalized_identity(12345, "NUMBER")   -> "12345"
normalized_identity(12345.0, "NUMBER") -> ""
```

Si existen respuestas con ese formato histórico, una nueva respuesta con el mismo documento no coincide con ellas. Las pruebas actuales de versiones históricas crean números con la implementación nueva, por lo que no cubren este caso. No se consultó producción para determinar cuántas respuestas afectadas existen.

**Corrección:** normalizar también floats finitos e integrales históricos. Esto permite comparar su valor almacenado, pero no recupera precisión que ya se hubiera perdido. Añadir una prueba con JSON histórico que contenga `12345.0`.

### 5. [P2] Dos pestañas comparten y pueden borrar el borrador de la otra

**Evidencia:** `static/forms/public-draft.js:6,37–39,65,155–158,217–222`.

Solo hay una clave de almacenamiento por formulario. Cada pestaña mantiene su token y datos en memoria, pero escribe sobre la misma clave y la elimina sin comprobar a qué token o revisión pertenece. No hay coordinación mediante eventos de almacenamiento ni detección de conflictos.

**Reproducción:** abrir dos pestañas antes de escribir, introducir respuestas distintas y guardar el borrador de la segunda mediante una edición. Al descartar desde la primera se elimina el borrador de la segunda. Si esta se cierra sin otro cambio, ya no podrá recuperarse. El guardado desde cualquiera de ellas también sobrescribe al otro.

**Verificación ejecutada:** la función original `removeStored()` de una pestaña eliminó una entrada cuyo token correspondía a otra. Es una reproducción de la operación de almacenamiento, no una prueba integral de navegador.

**Corrección:** definir una identidad de borrador/sesión y comprobarla antes de sobrescribir o borrar. Si el producto desea un único borrador por formulario, detectar la edición desde otra pestaña y ofrecer un mecanismo explícito para continuar en ella o iniciar otro.

### 6. [P2] Se aceptan validaciones que ningún valor puede satisfacer

**Evidencia:** `apps/forms/public_fields.py:75–96,112–134`; construcción del esquema en `apps/forms/conditions.py` y publicación en `apps/forms/publication.py:22–24`.

Se comprueba que el mínimo no supere al máximo, pero no que los límites sean compatibles con el dominio del tipo de campo.

**Reproducciones verificadas:**

- `NUMBER` con `min_value=0.1` y `max_value=0.9`: el esquema del campo se acepta, pero solo admite enteros no negativos. `0` queda por debajo, `1` por encima y `0.5` se rechaza por contener decimales.
- `PHONE` con `min_length=26`: el campo se construye, pero su expresión de validación admite únicamente entre 6 y 25 dígitos.

Si la pregunta es obligatoria y visible, no hay una respuesta válida. Estos límites se pueden introducir mediante la edición técnica del campo o un documento enviado al guardado; no se encontró un control de límites en el constructor visual actual. La comprobación de publicación construye esos mismos campos sin detectar la contradicción.

**Corrección:** comprobar la intersección entre los límites configurados y el dominio real del tipo al construir/publicar el esquema. Rechazar intervalos sin ningún entero admisible y longitudes incompatibles con teléfono/correo.

### 7. [P2] La limpieza durable de adjuntos no cubre la edición ni todos los rollbacks

**Evidencia:** `apps/submissions/admin_views.py:313–315,353–356,382–385`, `apps/submissions/runtime.py:266–270`. Contraste con `apps/submissions/trash.py:74–79` y `apps/submissions/file_cleanup.py`.

Al quitar un archivo durante la edición se elimina primero su registro y, después del commit, se intenta borrar el objeto con un callback `robust=True`. Si el almacenamiento falla, se registra el error, pero no se crea `PendingFileDeletion`. El comando de reintentos no tiene ninguna tarea con la que recuperar ese objeto.

Las compensaciones tras un rollback también borran directamente. Si falla el primer borrado, el bucle se interrumpe y los archivos restantes ni siquiera se intentan eliminar.

**Escenario:** editar una respuesta, retirar un adjunto y hacer que `storage.delete()` falle. Los datos de la edición quedan confirmados y el objeto conserva contenido sin una referencia operativa para su limpieza. Este hallazgo se determinó siguiendo el código; no se provocó una caída de R2.

**Corrección:** extender la cola durable que ya usa el purgado a las eliminaciones por edición y a las compensaciones, cuidando que los registros de compensación sobrevivan al rollback. Un fallo de borrado no debe detener el resto de la limpieza.

## Flujos sin recuperación dentro del panel

### 8. [P2] Se puede dejar la plataforma sin ningún administrador activo

**Evidencia:** `apps/accounts/forms.py:23–40,43–48`, `apps/accounts/admin.py:32–48,83–93`.

El editor permite cambiar el rol y desactivar una cuenta, incluida la propia. No hay una validación que conserve al menos un superusuario activo. Con un único administrador, cambiarlo a Operador o desactivarlo deja la gestión de usuarios sin acceso desde la aplicación; recuperar el control requiere una intervención externa.

Es una carencia de recuperación y protección operativa, determinada por inspección de las rutas y formularios. No se modificaron cuentas ni se ejecutó este escenario contra una base.

**Corrección propuesta:** impedir que una modificación o eliminación deje cero administradores activos, con protección frente a cambios concurrentes. Establecer también el procedimiento de recuperación fuera del panel.

### 9. [P2] Archivar un formulario es un camino sin vuelta en la interfaz

**Evidencia:** `templates/admin/forms/gallery.html:80–82`, `apps/forms/admin.py:194–196,229–249`, `apps/forms/publication.py:13–14,59–60`, `apps/forms/builder.py:164–165`.

La acción «Archivar» se ejecuta directamente, sin una confirmación equivalente a la de eliminar. Después, el constructor rechaza guardar y las rutas de publicación/acceso rechazan el estado archivado. No existe una acción o ruta para desarchivar. Los datos se conservan, pero el usuario no puede reutilizar el formulario desde el panel.

**Decisión pendiente:** si archivar debe ser reversible, añadir restauración con permisos y registro de actividad. Si debe ser definitivo, indicarlo claramente antes de ejecutarlo y exigir una confirmación. No se presupone que conservar versiones históricas sea un error.

## Riesgos y trabajo incompleto que siguen presentes

- **Coste de duplicados bajo un bloqueo global del formulario.** `matching_responses()` recorre todas las respuestas de identificación anteriores en Python (`apps/submissions/duplicates.py:26–48`), incluso cuando el llamador solo necesita saber si existe una coincidencia. `save_response()` lo ejecuta manteniendo bloqueada la fila de `Form` (`apps/submissions/runtime.py:209,259–261`). Con más respuestas aumenta el trabajo por envío y esperan los demás envíos del mismo formulario. Conviene almacenar una representación normalizada indexable y medir concurrencia. No se midieron tiempos de producción.
- **Recepción y almacenamiento siguen acoplados.** Las cargas de adjuntos ocurren dentro de esa misma transacción (`apps/submissions/runtime.py:246`). Un almacenamiento lento prolonga el bloqueo; sigue pendiente separar la transferencia de la asociación final. El presupuesto público de bytes tampoco se aplica de forma equivalente a la subida de imágenes y catálogos del constructor.
- **Los reportes siguen recorriendo el conjunto completo.** `report_columns()` descubre columnas leyendo respuestas y precargando opciones/archivos antes de paginar (`apps/submissions/reports.py:241–282`). Sigue siendo un riesgo de escalabilidad ya documentado, no un problema nuevo que se dé por medido.
- **Mantenimiento sin programación incluida en el repositorio.** Existen comandos para limpiar límites de solicitudes, reintentar eliminación de archivos y recuperar correos, pero no una programación desplegada como parte de la configuración revisada. `docs/email-notifications.md` lo reconoce explícitamente. Si un proceso termina tras confirmar una notificación y antes de enviarla, la recuperación requiere ejecutar el comando. No se inspeccionaron programadores externos.

## Documentación, piezas heredadas y cobertura

**[P3] La documentación actual se contradice.** El README dice que las preguntas con el mismo título se agrupan en una columna (`README.md:112–114`), pero el código distingue columnas por formulario y `stable_key`. `docs/architecture.md:62–69` todavía presenta Workers como destino obligatorio y afirma que no hay dominio ni despliegue configurados, mientras el README y `vercel.json` describen Vercel. Conviene actualizar los documentos vigentes y conservar las auditorías fechadas como antecedentes.

`Workspace` y los enlaces antiguos tienen referencias de compatibilidad reales: no se consideran sobrantes que puedan eliminarse sin una migración. El empaquetado de Workers también está conectado a un trabajo de CI, aunque se documenta como experimental. Retirarlo sería una decisión de alcance, no una limpieza automática de código muerto.

Las pruebas existentes cubren casos útiles de permisos, estados, versiones, concurrencia y recuperación. Las carencias de cobertura más claras de esta revisión son: cantidades multipart combinadas; detección de cambios de ajustes; números históricos como float; exportación legible de cuadrículas; conflictos de borradores entre pestañas; validaciones sin solución; y recuperación de limpieza tras edición.

## Verificación y límites de esta auditoría

- Ruff: comprobación de reglas correcta; **200 archivos** ya cumplen el formato.
- Sintaxis de JavaScript: **31 archivos** comprobados, sin errores.
- `git diff --check`: correcto sobre los cambios existentes.
- Reproducciones aisladas ejecutadas: parser multipart con demasiados campos y archivos; omisión de los tres ajustes en `snapshot()`; exportación de cuadrícula; normalización de números históricos; borrado de almacenamiento de otra pestaña; dos configuraciones de campo sin valores válidos.
- **La suite Django no arrancó.** Windows bloquea la carga de la DLL de `psycopg_binary`; el fallo persiste fuera del aislamiento inicial. Los intentos fijaron explícitamente PostgreSQL local y almacenamiento local, con correo desactivado. No se sustituyó PostgreSQL por SQLite para declarar aprobada la suite.
- No se ejecutaron pruebas integrales de navegador, carga, restauración de copias, entrega real de correo, despliegue ni auditoría de dependencias contra bases de vulnerabilidades actualizadas.

Los resultados de pruebas recogidos en auditorías anteriores no se presentan como resultados de esta ejecución. La revisión no demuestra que todos los fallos posibles estén enumerados.

**Orden sugerido:** resolver primero los rechazos multipart y el seguimiento de ajustes; después exportaciones, compatibilidad histórica de duplicados y limpieza de adjuntos; a continuación conflictos de borradores y validaciones imposibles; cerrar las decisiones de recuperación y el mantenimiento programado antes de ampliar el uso operativo.
