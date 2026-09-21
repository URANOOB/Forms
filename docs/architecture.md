# Decisiones de arquitectura

## Límites de esta fase

Foundation creó `accounts` y `forms`; la ampliación solicitada después incorpora
`submissions` para formularios públicos y respuestas privadas. Workspace vive en
accounts. documents, notifications, exports, analytics y audit aparecerán al requerirse.
No existe constructor propio todavía. La publicación está disponible desde FormAdmin.
Los modelos técnicos sí tienen ModelAdmin para edición básica de borradores, conforme
al alcance detallado de Fase 1. El tipo y stable_key de campos existentes se mantienen
de sólo lectura en este admin para no invalidar sus opciones o condiciones.
`/` devuelve 404; los formularios publicados se abren en `/f/<workspace>/<slug>/`.

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
limita las opciones de relaciones a versiones editables del workspace del usuario.
**No usar `QuerySet.update`, `bulk_create`,
`bulk_update`, `QuerySet.delete` ni SQL directo para editar el esquema**: omiten
validación de modelos. Las escrituras ordinarias del contenido y la publicación
comparten bloqueo de FormVersion. Publicación, pausa, archivado y recepción bloquean
Form dentro de transacciones para decidir sobre su estado actual. La clonación de
versiones preservando stable_key sigue pendiente del constructor.

## Acceso y conservación

Un usuario ordinario pertenece a un workspace; todos los accesos a los admins de forms
se filtran por workspace activo, incluso URLs directas y acciones masivas. Los
superusuarios son operadores globales. La membresía en múltiples workspaces se
pospone hasta que exista una necesidad. Esto no es aislamiento por PostgreSQL RLS;
cualquier vista nueva debe aplicar el mismo ámbito y permisos Django.

Se deshabilita hard delete de formularios, usuarios y workspaces en el admin;
archivar/desactivar es el flujo normal. Las FK PROTECT conservan autoría e historial.
La auditoría actual es LogEntry nativo del admin. No sustituye los futuros eventos
de lectura, documentos y exportaciones; no se registran respuestas sensibles.

El slug es único por workspace. La resolución pública siempre usa ambos slugs:
`/f/<workspace>/<slug>/`. No existe listado público de formularios ni endpoint público
para consultar respuestas. La confirmación no expone datos ni IDs de respuestas.

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
con Pyodide. Mantener alternativa WSGI/ASGI convencional si una dependencia falla.
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
