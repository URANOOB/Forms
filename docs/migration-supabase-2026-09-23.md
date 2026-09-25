# Traslado de PostgreSQL a Supabase — 23 de septiembre de 2026

## Resultado

Se restauraron los datos y el esquema de PostgreSQL local en el proyecto Supabase
`zrsfylyubusaznfviglf`, mediante el session pooler de puerto 5432 y TLS requerido.
Origen PostgreSQL 17.11; destino PostgreSQL 17.6.

- 22 tablas y 7.078 filas verificadas por recuento y huella del contenido completo.
- 9 secuencias conservadas, incluidos valor actual y estado `is_called`.
- 36 migraciones Django registradas; `migrate --noinput` sin operaciones pendientes.
- `check` sin incidencias y `makemigrations --check --dry-run` sin cambios.
- Todas las restricciones del esquema restaurado validadas.
- Lecturas con el ORM de Django comprobadas contra Supabase.

Los registros incluyen 4 usuarios, 4 formularios (incluidos registros históricos),
39 versiones, 2 respuestas, 4 imágenes de formularios y 2 adjuntos. Los binarios
de los archivos aún permanecen locales; sus referencias en la base se conservaron.

## Método y acceso

Se bloquearon temporalmente las escrituras sobre las tablas locales durante el
respaldo y la copia. Se exportaron las tablas de la aplicación y sus secuencias,
sin sustituir los esquemas internos de Supabase ni los propietarios originales.
La restauración, las comprobaciones de contenido y las restricciones de acceso
se ejecutaron en una única transacción remota. La verificación se repitió después
del commit y después del comando `migrate`.

Las 22 tablas tienen RLS activado, sin políticas de acceso por Data API. Se retiraron
los privilegios de `PUBLIC`, `anon`, `authenticated` y `service_role` sobre las tablas
y secuencias trasladadas. También se retiraron los permisos predeterminados de
esos roles para nuevas tablas/secuencias creadas por `postgres` en `public`.
La conexión Django actual utiliza al propietario `postgres`, que puede acceder
a sus tablas. Antes del despliegue, configurar un rol de ejecución con los permisos
y políticas RLS necesarios si se sustituye al propietario; no basta con cambiar
el usuario de conexión. Mantener desactivada la Data API para esta aplicación.

## Respaldo y evidencias

Directorio privado fuera del repositorio:

`G:\Develop\Forms-backups\supabase-20260924T032428Z`

Contiene el respaldo completo `local-full.dump`, el archivo de traslado
`application.dump`, copias de `media/` y `private_uploads/`, el inventario del
archivo, los manifiestos de verificación y el script de transferencia empleado.
Los respaldos contienen datos de la aplicación; no deben añadirse a Git.

## Estado al terminar el traslado de PostgreSQL

`.env` sigue conectado a PostgreSQL local. `.env.supabase` permite ejecutar comandos
contra Supabase explícitamente mediante `uv run --env-file .env.supabase ...`.
No se activó la base remota en el servidor local ni se desplegó la aplicación.

Las credenciales de R2 estaban vacías al verificar esta operación. Falta copiar
y verificar los archivos, configurar el entorno de despliegue y hacer el cambio
definitivo de conexión. No existe replicación automática: los cambios posteriores
en la base local no aparecen en Supabase. Comparar nuevamente ambos extremos y
conciliar los cambios antes de activar el destino; no repetir una restauración
completa sobre estas tablas ya existentes.

Los comandos de pruebas continúan usando la base local. No ejecutar el test runner
con `.env.supabase`.

## Actualización: archivos R2 verificados

Se configuró el bucket `forms-prod-private`, se corrigió el formato del endpoint
HTTPS y se copiaron los 6 archivos referenciados: 4 imágenes y 2 adjuntos, con
11.119.625 bytes en total. Cada objeto se volvió a leer desde R2 para compararlo
con el original mediante SHA-256. Los archivos locales y sus respaldos se conservan.

Antes de la copia se volvieron a comparar las 22 tablas locales y remotas: seguían
siendo idénticas. Se verificaron las vistas de imágenes y descargas de Django
conectadas a Supabase y R2, incluyendo la lectura completa de los archivos. Las
descargas de adjuntos rechazaron solicitudes anónimas y de personal sin permiso.
Las comprobaciones sobre PostgreSQL se hicieron en transacciones de solo lectura.

`.env.supabase` ahora tiene `FILE_STORAGE=r2`; las credenciales R2 se cargan del
`.env` local, que conserva su conexión PostgreSQL y almacenamiento locales para
desarrollo. Para desplegar, registrar explícitamente todas las credenciales en
los secretos del servicio; no incluir estos archivos dotenv en la imagen.

La evidencia de esta verificación está en `r2-verification.json` dentro del
directorio de respaldo anterior. Falta activar el entorno remoto en el servidor
que atiende la aplicación y realizar el despliegue. No existe sincronización
automática de cambios posteriores del entorno local al remoto.

## Actualización: servidor local conectado a Supabase y R2

Se compararon nuevamente las 22 tablas antes del cambio: no había diferencias.
El servidor de `http://127.0.0.1:8000` se reinició con `.env.supabase`. Ahora las
operaciones de esa aplicación utilizan la base Supabase y el bucket R2. Se verificó
la página real de inicio con una sesión administrativa existente: muestra ambos
proveedores, 500 MB de capacidad de base y 10 GB como referencia gratuita de R2,
con dos barras de uso y sin mensajes de capacidad sin configurar.

Para volver a iniciar el mismo entorno:

```powershell
uv run --env-file .env.supabase python manage.py runserver 127.0.0.1:8000
```

`.env` conserva la configuración local para desarrollo y pruebas. No se sobrescribió
la base local. Desde este cambio los registros nuevos de la aplicación que atiende
el puerto 8000 se guardan en Supabase; no hay replicación hacia PostgreSQL local.
El despliegue de la aplicación en Cloudflare sigue pendiente.
