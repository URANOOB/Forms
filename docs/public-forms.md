# Formularios públicos y respuestas

El enlace público permite GET/POST anónimos; el backend exige usuario staff con permisos
Django. No confundir acceso anónimo con despliegue: una URL localhost
no es accesible desde Internet. El despliegue actual utiliza Vercel, Supabase y R2;
consulta [despliegue](vercel-deployment.md).

## Guardado y privacidad

Submission referencia Form y FormVersion; SubmissionAnswer guarda un JSONB por campo.
Texto y fecha ISO se guardan como strings, números como números JSON, booleanos como
booleanos y selección múltiple como arrays. No se guardan IP, user agent ni datos en
localStorage. Los datos ocultos y claves no reconocidas se descartan.

CSRF permanece activo. Un token firmado de 24 horas contiene formulario, versión y
nonce, nunca respuestas. El nonce es único en PostgreSQL. Una transacción bloquea el
formulario, verifica estado/versión y guarda respuesta y valores atómicamente.
Reintentar el mismo envío conserva un único registro. Las versiones antiguas no se
reinterpretan: un envío con token desactualizado debe revisarse antes de volver a enviar.
La respuesta de validación conserva los datos introducidos, sin redirecciones con PII.
Páginas públicas y confirmación usan Cache-Control no-store; la confirmación es genérica.

La lista de Respuestas incluye iconos para ver, editar y eliminar según los permisos.
La edición conserva fecha y versión originales, valida los tipos y condiciones y permite
gestionar adjuntos. Detecta cambios concurrentes antes de guardar. El borrado requiere
confirmación y elimina los datos y adjuntos de esa respuesta. Las operaciones registran
entradas en la auditoría del admin. Los roles Administrador y Visor pueden gestionar formularios y respuestas;
solo el Administrador gestiona usuarios. Ver [roles](users.md). Auditoría de lecturas y retención quedan pendientes.

## Condiciones y validación

Se admiten texto, correo, teléfono, número, fecha, hora, selección, booleano,
escalas, calificaciones, cuadrículas, archivos y contenido informativo.
Las cuadrículas obligatorias requieren respuesta en todas sus filas. Los archivos
admiten hasta 5 adjuntos por pregunta y hasta 10 MB por archivo, según la configuración.
Se almacenan en `private_uploads/` en local o en R2 privado; su descarga requiere sesión de personal y
`submissions.view_submission`. No se sirve esa carpeta como contenido público.
Validaciones configurables: min_length/max_length para textos (máximo 20000),
min_value/max_value para números. Se rechazan NaN e infinito. Fechas en formato ISO.

Los campos numéricos aceptan enteros entre 0 y 9007199254740991 para mantener la
misma precisión en Python, JSON y JavaScript. Para documentos más largos o valores
con ceros iniciales se debe usar texto; los teléfonos se conservan como texto.
Los valores históricos no se reescriben y un número ya redondeado no puede recuperarse
sin cotejarlo con su fuente original.

En Vercel, el navegador y el servidor comprueban también un presupuesto total de
4.000.000 bytes por envío, incluidos campos, archivos y una reserva por parte multipart.
La configuración por archivo no sustituye este límite agregado. El control del navegador
evita perder lo escrito por un rechazo del proveedor; para transferencias mayores hace
falta implementar cargas directas a R2. Los adjuntos DOCX/XLSX deben contener las partes
Office esperadas, sin macros ni cifrado y con hasta 64 MB declarados al descomprimir.
Esta comprobación no sustituye un análisis antimalware.

Los grupos AND/OR comparten acción/destino. Las reglas sin group_key son independientes.
Los grupos se procesan por orden y UUID; ante acciones sucesivas gana la última
coincidente. SHOW hace que el destino empiece oculto; HIDE lo oculta si coincide.
REQUIRE/OPTIONAL modifican la obligatoriedad base. Los campos ocultos nunca son requeridos.
Las fuentes ocultas no activan reglas posteriores. Se rechazan ciclos antes de publicar.
El grafo se evalúa en orden de dependencias para que el orden visual no afecte al resultado.

JavaScript oculta/deshabilita campos irrelevantes sin borrar lo escrito en el DOM.
Sin JavaScript se muestran todos los campos y el servidor decide cuáles corresponden.
El botón se bloquea durante el envío; la garantía de unicidad está en PostgreSQL.

## Operación

Publicar/Pausar se ofrece en el detalle y en acciones de FormAdmin. El enlace usa un UUID (se conservan los enlaces legacy por workspace/slug), y se construye sobre el host de la petición; configurar hosts/orígenes
HTTPS del despliegue antes de compartir. El esquema publicado es de sólo lectura;
para modificarlo, el constructor genera una nueva versión. Guardar un formulario ya
publicado activa esa versión conservando el estado de acceso; las respuestas previas
no se modifican. Un formulario pausado muestra un aviso y rechaza nuevos envíos.

Referencias: [firma de datos en Django](https://docs.djangoproject.com/en/5.2/topics/signing/)
y [validación de formularios](https://docs.djangoproject.com/en/5.2/ref/forms/validation/).
