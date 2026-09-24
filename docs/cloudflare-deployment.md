# Despliegue en Cloudflare Workers

La aplicaciÃ³n usa Django en Python Workers, PostgreSQL en Supabase y R2 Ãºnicamente
para archivos privados. No utiliza Containers ni cambia el plan de Cloudflare.

## ConfiguraciÃ³n de GitHub en Cloudflare

- Repositorio: `URANOOB/Forms`; rama de producciÃ³n: `main`; directorio raÃ­z: `/`.
- Comando de despliegue: `npx wrangler deploy`.
- Wrangler ejecuta el build definido en `wrangler.jsonc`. El entorno necesita Node,
  Python 3.13 y `uv`; Wrangler y las herramientas de empaquetado estÃ¡n fijados.
- URL configurada: `https://forms.sololperco.workers.dev`.
- GitHub Actions valida Django y construye el Worker sin credenciales. La integraciÃ³n
  de Cloudflare con GitHub es la que publica los cambios de `main`.

El build instala dependencias WebAssembly en un entorno temporal, incluye solo el
cÃ³digo y las plantillas de la aplicaciÃ³n y publica `collectstatic` bajo `/static/`.
Excluye `.env`, datos, archivos subidos, pruebas, fuentes C, traducciones ajenas a
espaÃ±ol/inglÃ©s y los modelos AWS distintos de S3. Conserva los mÃ³dulos de formatos
regionales de Django. El build no ejecuta migraciones ni consulta producciÃ³n.

## Secretos del Worker

Configurar en Settings â†’ Variables and Secrets, como secretos:

- `DATABASE_URL`: conexiÃ³n al pooler de Supabase con TLS (`sslmode=require`).
- `DJANGO_SECRET_KEY`: clave aleatoria de al menos 50 caracteres, estable entre deploys.
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: acceso al bucket privado.
- `R2_BUCKET_NAME` y `R2_ENDPOINT` (o `R2_ACCOUNT_ID`).

TambiÃ©n pueden cargarse en el primer despliegue con
`npx wrangler deploy --secrets-file <archivo-privado.json>`. Mantener ese archivo fuera
del repositorio. Los siguientes despliegues conservan los secretos. No cargar `.env`
como asset ni habilitar acceso pÃºblico al bucket.

Hosts, orÃ­genes CSRF y referencias de almacenamiento estÃ¡n en `wrangler.jsonc`.
Al cambiar el dominio, actualizar ambos valores de seguridad antes de desplegar.
Los 10 GB de R2 son una referencia de la franquicia gratuita compartida por la
cuenta, no un lÃ­mite del bucket ni un cÃ¡lculo de facturaciÃ³n mensual.

## Adaptaciones del runtime

- El puente WSGI serializa la vida completa de cada respuesta, incluido el cierre
  de archivos y conexiones, para proteger el ORM sÃ­ncrono en el runtime asÃ­ncrono.
- PostgreSQL mantiene transacciones y cursores normales, con conexiones de corta
  duraciÃ³n y sin cursores de servidor, adecuados para el pooler.
- PBKDF2 usa PyCryptodome conservando el formato y las iteraciones de Django. No
  rebaja la seguridad ni requiere cambiar las contraseÃ±as existentes. Web Crypto
  limita las iteraciones y no puede verificar directamente estos hashes.
- R2 conserva el backend privado de Django y utiliza transferencias sin hilos.
  Se restaura el contexto SSL del runtime y las cabeceras S3 firmadas se convierten
  de bytes a texto para Fetch. El build aplica una corrección acotada a urllib3
  para reconocer cuerpos JavaScript nulos en respuestas HEAD/204; falla de forma
  explícita si cambia el código del proveedor y esa corrección requiere revisión.
- `tzdata` proporciona las zonas horarias que faltan en WebAssembly.

## Comprobaciones y lÃ­mites

Ejecutar `uv run python manage.py test --noinput`, `uv run ruff check .`,
`uv run ruff format --check .` y `npx wrangler deploy --dry-run` antes del merge.
Los tests deben usar PostgreSQL local o de CI, nunca la base de producciÃ³n.
Las migraciones siguen siendo una operaciÃ³n explÃ­cita con el entorno de Supabase.

Las pruebas de compatibilidad remotas verificaron PostgreSQL, rollback, bloqueo de
filas y hashes de contraseÃ±as. La ausencia de errores en una prueba no garantiza
capacidad suficiente con carga real: el plan gratuito tiene lÃ­mites de CPU y
memoria. Se observÃ³ un rechazo de CPU al importar boto3 durante una peticiÃ³n; por
eso las dependencias se preparan durante el arranque. Revisar errores y consumo
en Workers antes de ampliar el uso. No se habilita facturaciÃ³n adicional.

Referencias oficiales consultadas el 24 de septiembre de 2026:

- [Django en Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/django/).
- [LÃ­mites de Workers](https://developers.cloudflare.com/workers/platform/limits/).
- [PostgreSQL desde Python Workers](https://developers.cloudflare.com/hyperdrive/examples/python-workers/).
