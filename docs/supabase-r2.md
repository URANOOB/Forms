# Traslado a Supabase PostgreSQL y Cloudflare R2

La aplicación conserva Django para autenticación, permisos y migraciones.
Supabase guarda las tablas (incluidos usuarios, versiones, respuestas, estados,
historial y referencias de archivos). R2 guarda exclusivamente los archivos
subidos: `form-images/` y `responses/`. CSS, JavaScript y recursos de la aplicación
siguen usando `staticfiles`.

## 1. Preparar Supabase

En el proyecto de destino, desactivar **Enable Data API** en la integración Data
API antes de crear/restaurar tablas. Este proyecto usa SQL desde Django, no los
endpoints REST/GraphQL ni Supabase Auth. Así las tablas Django no se exponen por
los permisos predeterminados del esquema `public`.

Desde **Connect**, copiar la URI PostgreSQL. Usar conexión directa si el equipo
tiene conectividad IPv6, o **Session pooler**, puerto 5432, para IPv4. El usuario
del pooler incluye la referencia del proyecto: copiar los valores exactos del
panel. No usar el pooler de transacciones (6543) para este traslado.

Guardar la URI en un nuevo `.env.supabase`, ignorado por Git:

```dotenv
DATABASE_URL=postgresql://USUARIO:CONTRASENA_CODIFICADA@HOST:5432/postgres?sslmode=require
FILE_STORAGE=local
```

La contraseña de PostgreSQL es distinta de las API keys de Supabase. Codificar
los caracteres especiales de la contraseña para una URI. Para validación de
identidad del servidor, usar `sslmode=verify-full` y `sslrootcert` con el certificado
CA del proyecto. No compartir la URI ni claves en el chat o en commits.

Conservar `.env` con la conexión PostgreSQL local. Los comandos habituales y las
pruebas continuarán usando esa base. Un comando con
`uv run --env-file .env.supabase ...` carga explícitamente el destino; las variables
del proceso prevalecen sobre archivos dotenv, por lo que deben revisarse antes de
usar este mecanismo. Nunca ejecutar el test runner contra el destino real.

## 2. Preparar R2

Crear un bucket privado, por ejemplo `logicforms-files`. Mantener deshabilitados
el acceso público `r2.dev` y los dominios públicos. Crear una credencial S3 con
**Object Read & Write**, restringida a ese bucket. Guardar en el `.env` local:

```dotenv
FILE_STORAGE=local
R2_ACCOUNT_ID=ID_DE_LA_CUENTA
R2_ACCESS_KEY_ID=ACCESS_KEY
R2_SECRET_ACCESS_KEY=SECRET_KEY
R2_BUCKET_NAME=logicforms-files
R2_ENDPOINT=
```

Si el endpoint queda vacío se construye a partir del Account ID. Si el bucket
requiere un endpoint específico por jurisdicción, copiarlo en `R2_ENDPOINT`.
La aplicación usa HTTPS, región `auto`, firma S3v4, sin ACL pública y sin
sobrescribir objetos. No necesita CORS del bucket porque el navegador utiliza
las rutas de Django. Las imágenes publicadas mantienen las condiciones de acceso
existentes; los adjuntos requieren sesión de personal y permiso de respuestas.

## 3. Preparar y ejecutar el traslado

Primero comprobar versión PostgreSQL de ambos extremos, identidad del proyecto
de destino y ausencia de tablas Django en él. No modificar los esquemas internos
de Supabase. Configurar un rol de aplicación con acceso a las tablas y secuencias;
reservar los privilegios de creación/alteración para restauración y migraciones.

El procedimiento acordado conserva los datos actuales:

1. Detener temporalmente las escrituras de la aplicación, incluidos formularios
   públicos y cambios administrativos. Mantener esa pausa hasta terminar la
   copia y el cambio de conexión.
2. Respaldar la base local y las carpetas `media/` y `private_uploads/` fuera de Git.
3. Crear un archivo `pg_dump` en formato custom con las tablas/secuencias Django
   del esquema local `public`: prefijos `accounts_`, `forms_`, `submissions_`,
   `auth_` y `django_`. Conservar PK, relaciones, secuencias, permisos Django y
   `django_migrations`. Revisar el inventario del dump antes de restaurar.
4. Restaurar en el destino sin tablas Django, usando `pg_restore --no-owner
   --no-privileges --single-transaction --exit-on-error`. No usar `--clean` ni
   `--create`. Así se conservan los objetos administrados por Supabase y un error
   revierte la restauración. Usar herramientas PostgreSQL compatibles con las
   versiones de origen y destino; no hacer una restauración hacia una versión
   mayor anterior sin resolver esa compatibilidad.
5. Copiar los archivos y verificar sus bytes como se describe abajo.
6. Comparar recuentos por tabla, identificadores/relaciones y archivos del destino.
   Revisar `migrate --plan`; aplicar únicamente migraciones pendientes. No ejecutar
   `migrate` para crear tablas antes de esta restauración completa, ni `seed_demo`
   o `setup_roles` para reemplazar los usuarios/grupos trasladados.
7. Cambiar `FILE_STORAGE=r2` en `.env.supabase`, arrancar Django con ese archivo de
   entorno y probar login, formularios, envíos, revisión y descarga autorizada.
   Probar también que una sesión anónima no puede descargar los adjuntos privados.
8. Reabrir recepción. Conservar el respaldo y los originales. Una reversión después
   de recibir datos nuevos requiere conciliarlos, no solo apuntar al respaldo.

Las migraciones crean/modifican estructura; por sí solas **no trasladan registros**.
La restauración completa evita reconstruir identificadores y usuarios manualmente.
Los comandos concretos de exportación/restauración deben apuntar al origen y
destino verificados, con secretos en archivos/entorno, nunca en argumentos visibles.

## Copia verificable de archivos

Con `.env` aún conectado a la base local y las credenciales R2 configuradas:

```powershell
uv run python manage.py copy_files_to_r2
uv run python manage.py copy_files_to_r2 --apply
```

El primer comando solo lee y comprueba los archivos locales referenciados en la
base de datos; no contacta R2. `--apply` conserva cada clave y vuelve a leer cada
objeto en R2 para comparar SHA-256. Una segunda ejecución verifica y omite los
objetos idénticos. Ante contenido diferente en una clave existente se detiene sin
sobrescribirla. Nunca borra archivos locales ni modifica registros. No trasladar
archivos huérfanos automáticamente: conservarlos en el respaldo para revisión.

Si una ejecución falla, no activar R2 hasta resolver el error y repetir la
verificación. Ejecutar sin escrituras concurrentes; la copia no es una transacción
distribuida entre PostgreSQL, disco y R2. La verificación descarga los objetos y
realiza operaciones de lectura/escritura en el bucket.

## Estado de preparación

Implementados el backend opcional R2 y la copia verificada. La base se trasladó
a Supabase el 23 de septiembre de 2026; los 6 archivos también se copiaron y
verificaron en `forms-prod-private`. Consultar el
[informe del traslado](migration-supabase-2026-09-23.md). `.env.supabase` activa R2,
mientras `.env` conserva el entorno local. El servidor de `127.0.0.1:8000` ya se
reinició usando `.env.supabase`, tras comprobar que no había diferencias entre
las bases. Falta el despliegue en Cloudflare. No repetir la restauración inicial
sobre el destino ya poblado.

Fuentes oficiales:

- [Conexiones PostgreSQL en Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).
- [Desactivar la Data API](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api).
- [Credenciales R2](https://developers.cloudflare.com/r2/api/tokens/).
- [Backend S3 de django-storages](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html).
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) y
  [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).
