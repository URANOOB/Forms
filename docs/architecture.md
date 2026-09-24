# Decisiones de arquitectura

## Límites de esta fase

La aplicación incluye constructor visual, formularios públicos, revisión de respuestas,
catálogos y dashboard operativo. `Workspace` permanece como contenedor de compatibilidad
de datos anteriores; no representa una frontera de permisos. Ver [roles](users.md).
La portada pública vive en `/`; los formularios usan `/f/<uuid>/` y se conservan enlaces
antiguos por workspace/slug. La administración exige sesión y permisos de Django.

## Esquema versionado

Form conserva identidad y metadata administrativa. FormVersion posee secciones,
campos y reglas. Sólo puede existir un borrador por formulario; números de versión
y `stable_key` son únicos dentro de su ámbito. `schema_version` identifica el formato
del esquema, no el número de revisión del formulario.

FormField incluye una FK explícita a la versión para imponer unicidad de `stable_key`
en PostgreSQL entre secciones. Su validación comprueba que la sección pertenezca
a esa misma versión. Opciones sólo para campos de selección. JSONB para configuración
y validaciones; se exige un objeto JSON, aunque esté vacío. El runtime soporta límites
de longitud y numéricos; bloquea la publicación con validaciones desconocidas.

Una regla es una condición. `group_key` es opcional; reglas sin grupo son independientes.
Las reglas de un mismo grupo dentro de una versión
comparten combinador AND/OR, acción y destino. Se permite exactamente un destino,
campo o sección; todos los componentes deben pertenecer a la misma versión.
REQUIRE/OPTIONAL se aplican a campos. El motor interpreta datos, nunca código.
La publicación valida operandos y rechaza ciclos; el cliente refleja las condiciones
y el servidor reconstruye visibilidad y obligatoriedad antes de guardar.

Las escrituras ordinarias (`save`/`delete`) del contenido publicado/archivado se bloquean;
no se puede trasladar contenido entre versiones. El admin sólo edita borradores y
limita las opciones de relaciones a versiones editables.
**No usar `QuerySet.update`, `bulk_create`,
`bulk_update`, `QuerySet.delete` ni SQL directo para editar el esquema**: omiten
validación de modelos. Las escrituras ordinarias del contenido y la publicación
comparten bloqueo de FormVersion. Publicación, pausa, archivado y recepción bloquean
Form dentro de transacciones para decidir sobre su estado actual. El constructor clona versiones
conservando stable_key y mantiene intactas las referencias de respuestas históricas.

## Acceso y conservación

Formularios y respuestas se comparten en un panel institucional. Cada endpoint exige
los permisos de Django correspondientes; la gestión de usuarios exige superusuario.
La eliminación de formularios es lógica y conserva respuestas. Las relaciones PROTECT
preservan la autoría. La revisión registra actor, estados, fecha y motivo; rechazar
requiere un motivo. La auditoría de lecturas sigue pendiente.

No existe un endpoint público de consulta de respuestas. La confirmación no expone
datos ni IDs de respuestas. Los adjuntos son privados y se sirven mediante vistas
autorizadas; R2 no se expone como bucket público.

## Infraestructura portable

Django 5.2, Unfold y PostgreSQL mediante psycopg. Sin servicios Cloudflare dentro
del dominio. PostgreSQL local por Compose; Supabase sólo como base administrada.
Conexiones sin persistencia y cursores de servidor deshabilitados para facilitar
uso con ASGI y poolers. La configuración de producción activa HTTPS y cookies
seguras. No se confía en headers de proxy sin validar cómo los normaliza el hosting.

Cloudflare Python Workers sigue siendo el target, **no un despliegue validado**.
En Fase 10 se debe probar compatibilidad real de Django, psycopg y su transporte
PostgreSQL, Unfold/static, R2, correo y generación/streaming de exportaciones bajo
los límites del runtime. El wheel nativo usado localmente no prueba compatibilidad
con Pyodide. El alojamiento solicitado debe ser gratuito y permanecer en Cloudflare. Ver
[compatibilidad y trabajo pendiente](cloudflare-deployment.md).
En hosting convencional se debe servir `STATIC_ROOT` después de `collectstatic`.
No hay secretos, dominios reales ni despliegue configurados en este repositorio.

## Ajustes del alcance detallado de Fase 1

Fechas en UTC. Índices compuestos padre/orden en secciones, campos, opciones y reglas;
UUID como desempate de orden estable. `group` y `combinator` de la base inicial se
migran a `group_key` y `group_operator` conservando grupos existentes como texto.
Los estados de versión incluyen ARCHIVED; la publicación congela el borrador activo.
`setup_roles` funciona sin crear datos demo; `seed_demo` se bloquea en configuración
de producción. La nueva demo no elimina el ejemplo generado en la primera iteración
ni cambia grupos preexistentes. Esto conserva cualquier trabajo local existente.

Referencias consultadas:

- [Django: PostgreSQL, conexiones y poolers](https://docs.djangoproject.com/en/5.2/ref/databases/)
- [Unfold: instalación y ModelAdmin](https://unfoldadmin.com/docs/installation/quickstart/)
- [Cloudflare: paquetes Python y Pyodide](https://developers.cloudflare.com/workers/languages/python/packages/)
