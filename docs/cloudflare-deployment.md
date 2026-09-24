# Despliegue en Cloudflare: pendiente de compatibilidad

El alojamiento debe permanecer en Cloudflare y usar su plan gratuito. Supabase
conserva PostgreSQL; R2 almacena exclusivamente archivos privados. No se configura
Render ni Cloudflare Containers, que requiere Workers Paid.

El PR incorpora la aplicación y su integración con los servicios de datos. El
workflow de GitHub valida el código; **no publica la aplicación**. Hacer merge en
`main` no equivale a tener un servicio de producción funcionando.

## Compatibilidad que falta validar

Cloudflare documenta adaptadores WSGI/ASGI para Django en Python Workers. Ese runtime
usa paquetes Python compatibles con WebAssembly/Pyodide: instalar `psycopg[binary]`
en Windows o Linux no demuestra que la conexión PostgreSQL funcione en Workers.
También deben comprobarse Pillow y el transporte S3 de django-storages/boto3.

Los backends Django D1/Durable Objects documentados por Cloudflare no son un
reemplazo para este proyecto: cambian PostgreSQL y no soportan las transacciones
que protegen publicación, recepción idempotente y revisión concurrente.

Antes de añadir un workflow de despliegue, una prueba aislada debe demostrar:

1. Arranque real de Django/Unfold en Workers y conexión a PostgreSQL de prueba,
   con commit, rollback y bloqueo de filas preservados.
2. Sesión, CSRF, permisos y archivos estáticos con `DEBUG=False` sobre HTTPS.
3. Lectura/escritura privada en un bucket R2 de prueba, imágenes y adjuntos.
4. Importación CSV/XLSX/XLSM y límites de CPU, memoria y tamaño del plan gratuito.

Solo después se puede elegir un adaptador viable o estimar una adaptación del
backend a Workers. No sustituir el backend de datos ni activar recursos de pago
como parte de la conexión de GitHub. Las credenciales se cargarán como secretos
del entorno, nunca desde archivos `.env` versionados.

Referencias oficiales consultadas el 24 de septiembre de 2026:

- [Django en Python Workers y limitaciones de sus backends](https://developers.cloudflare.com/workers/languages/python/packages/django/).
- [Compatibilidad de paquetes Python](https://developers.cloudflare.com/workers/languages/python/packages/).
- [Planes de Cloudflare Containers](https://developers.cloudflare.com/containers/platform/pricing/).
