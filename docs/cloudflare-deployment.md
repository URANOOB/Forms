# Candidato de despliegue en Cloudflare Workers

**Bloqueado para producción en Workers Free.** El 24 de septiembre de 2026,
la prueba real registró `exceededCpu` y HTTP 503 al abrir el panel tras iniciar
sesión. Las pruebas de CI no detectan este límite de ejecución remoto. Mantener
este cambio en borrador; no fusionarlo como un despliegue gratuito estable.
No se ha habilitado ningún plan de pago.

La aplicaciÃƒÂ³n usa Django en Python Workers, PostgreSQL en Supabase y R2 ÃƒÂºnicamente
para archivos privados. No utiliza Containers ni cambia el plan de Cloudflare.

## ConfiguraciÃƒÂ³n de GitHub en Cloudflare

- Repositorio: `URANOOB/Forms`; rama de producciÃƒÂ³n: `main`; directorio raÃƒÂ­z: `/`.
- Comando de despliegue: `npx wrangler deploy`.
- Wrangler ejecuta el build definido en `wrangler.jsonc`. El entorno necesita Node,
  Python 3.13 y `uv`; Wrangler y las herramientas de empaquetado estÃƒÂ¡n fijados.
- URL configurada: `https://forms.sololperco.workers.dev`.
- GitHub Actions valida Django y construye el Worker sin credenciales. La integraciÃƒÂ³n
  de Cloudflare con GitHub es la que publica los cambios de `main`.

El build instala dependencias WebAssembly en un entorno temporal, incluye solo el
cÃƒÂ³digo y las plantillas de la aplicaciÃƒÂ³n y publica `collectstatic` bajo `/static/`.
Excluye `.env`, datos, archivos subidos, pruebas, fuentes C, traducciones ajenas a
espaÃƒÂ±ol/inglÃƒÂ©s y los modelos AWS distintos de S3. Conserva los mÃƒÂ³dulos de formatos
regionales de Django. El build no ejecuta migraciones ni consulta producciÃƒÂ³n.

## Secretos del Worker

Configurar en Settings Ã¢â€ â€™ Variables and Secrets, como secretos:

- `DATABASE_URL`: conexiÃƒÂ³n al pooler de Supabase con TLS (`sslmode=require`).
- `DJANGO_SECRET_KEY`: clave aleatoria de al menos 50 caracteres, estable entre deploys.
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: acceso al bucket privado.
- `R2_BUCKET_NAME` y `R2_ENDPOINT` (o `R2_ACCOUNT_ID`).

TambiÃƒÂ©n pueden cargarse en el primer despliegue con
`npx wrangler deploy --secrets-file <archivo-privado.json>`. Mantener ese archivo fuera
del repositorio. Los siguientes despliegues conservan los secretos. No cargar `.env`
como asset ni habilitar acceso pÃƒÂºblico al bucket.

Hosts, orÃƒÂ­genes CSRF y referencias de almacenamiento estÃƒÂ¡n en `wrangler.jsonc`.
Al cambiar el dominio, actualizar ambos valores de seguridad antes de desplegar.
Los 10 GB de R2 son una referencia de la franquicia gratuita compartida por la
cuenta, no un lÃƒÂ­mite del bucket ni un cÃƒÂ¡lculo de facturaciÃƒÂ³n mensual.

## Adaptaciones del runtime

- El puente WSGI serializa la vida completa de cada respuesta, incluido el cierre
  de archivos y conexiones, para proteger el ORM sÃƒÂ­ncrono en el runtime asÃƒÂ­ncrono.
- PostgreSQL mantiene transacciones y cursores normales, con conexiones de corta
  duraciÃƒÂ³n y sin cursores de servidor, adecuados para el pooler.
- PBKDF2 usa PyCryptodome conservando el formato y las iteraciones de Django. No
  rebaja la seguridad ni requiere cambiar las contraseÃƒÂ±as existentes. Web Crypto
  limita las iteraciones y no puede verificar directamente estos hashes.
- R2 conserva el backend privado de Django y utiliza transferencias sin hilos.
  Se restaura el contexto SSL del runtime y las cabeceras S3 firmadas se convierten
  de bytes a texto y los cuerpos de archivo a bytes para Fetch. Conserva la firma
  SHA-256 y evita checksums opcionales con codificación chunked. El build aplica una correcciÃ³n acotada a urllib3
  para reconocer cuerpos JavaScript nulos en respuestas HEAD/204; falla de forma
  explÃ­cita si cambia el cÃ³digo del proveedor y esa correcciÃ³n requiere revisiÃ³n.
- `tzdata` proporciona las zonas horarias que faltan en WebAssembly.

## Comprobaciones y lÃƒÂ­mites

Ejecutar `uv run python manage.py test --noinput`, `uv run ruff check .`,
`uv run ruff format --check .` y `npx wrangler deploy --dry-run` antes del merge.
Los tests deben usar PostgreSQL local o de CI, nunca la base de producciÃƒÂ³n.
Las migraciones siguen siendo una operaciÃƒÂ³n explÃƒÂ­cita con el entorno de Supabase.

Las pruebas de compatibilidad remotas verificaron PostgreSQL, rollback, bloqueo de
filas y hashes de contraseÃƒÂ±as. La ausencia de errores en una prueba no garantiza
capacidad suficiente con carga real: el plan gratuito tiene lÃƒÂ­mites de CPU y
memoria. Se observÃƒÂ³ un rechazo de CPU al importar boto3 durante una peticiÃƒÂ³n; por
eso las dependencias se preparan durante el arranque. Revisar errores y consumo
en Workers antes de ampliar el uso. No se habilita facturaciÃƒÂ³n adicional.

Referencias oficiales consultadas el 24 de septiembre de 2026:

- [Django en Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/django/).
- [LÃƒÂ­mites de Workers](https://developers.cloudflare.com/workers/platform/limits/).
- [PostgreSQL desde Python Workers](https://developers.cloudflare.com/hyperdrive/examples/python-workers/).
