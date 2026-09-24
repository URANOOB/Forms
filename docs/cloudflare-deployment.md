# Integración experimental con Cloudflare Workers

**No validada para producción en Workers Free.** Las pruebas reales del 24 de
septiembre de 2026 registraron `exceededCpu` y HTTP 503 al abrir el panel después
de iniciar sesión. El inicio de sesión consumió aproximadamente 1–1,8 segundos de
CPU; una petición posterior fue interrumpida a los 250 ms. Otras peticiones
funcionaron, pero eso no demuestra estabilidad bajo los límites gratuitos.

El código se conserva en el repositorio como integración experimental. Su merge
no certifica un despliegue estable ni activa un plan de pago. La configuración
para Vercel todavía está pendiente; no se incluye en esta integración.

## Arquitectura y compilación

Django se empaqueta como Python Worker. Supabase conserva PostgreSQL y R2 almacena
exclusivamente archivos privados. No se utilizan Cloudflare Containers.

- Repositorio: `URANOOB/Forms`; rama de producción configurada: `main`.
- Comando de despliegue: `npx wrangler deploy`.
- Wrangler ejecuta el build definido en `wrangler.jsonc` con Node, Python y `uv`.
  Las versiones de las herramientas y dependencias están fijadas.
- URL del despliegue de prueba: `https://forms.sololperco.workers.dev`.
- GitHub Actions valida Django y construye el Worker sin credenciales. La
  integración externa de Cloudflare con GitHub es la que intenta publicarlo.

El build instala dependencias WebAssembly en un entorno temporal e incluye solo
código, plantillas y los archivos estáticos de `collectstatic`, bajo `/static/`.
Excluye secretos, archivos subidos, pruebas, fuentes C, traducciones ajenas a
español/inglés y modelos AWS distintos de S3. Conserva los módulos de formatos
regionales de Django. No ejecuta migraciones ni consulta producción.

## Secretos y seguridad

Configurar como secretos del Worker:

- `DATABASE_URL`: pooler de Supabase con TLS (`sslmode=require`).
- `DJANGO_SECRET_KEY`: clave aleatoria estable de al menos 50 caracteres.
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: acceso al bucket privado.
- `R2_BUCKET_NAME` y `R2_ENDPOINT` (o `R2_ACCOUNT_ID`).

El primer despliegue puede usar
`npx wrangler deploy --secrets-file <archivo-privado.json>`. Mantener ese archivo
fuera del repositorio; los despliegues posteriores conservan los secretos.
No publicar archivos `.env` ni habilitar acceso público al bucket.

Hosts, orígenes CSRF y referencias de almacenamiento están en `wrangler.jsonc`.
Al cambiar de dominio, actualizar ambos valores de seguridad. Los 10 GB de R2
son una referencia gratuita compartida por la cuenta, no una capacidad fija del
bucket ni un cálculo del saldo mensual de facturación.

## Adaptaciones del runtime

- El puente WSGI serializa la vida completa de cada respuesta, incluido el cierre
  de archivos y conexiones, para proteger el ORM síncrono.
- PostgreSQL conserva transacciones y conexiones de corta duración, sin cursores
  de servidor, adecuados para el pooler.
- PBKDF2 usa PyCryptodome conservando el formato y las iteraciones de Django.
  Web Crypto limita las iteraciones y no verifica directamente estos hashes.
- R2 usa el backend privado de Django con transferencias sin hilos. Se restaura
  el contexto SSL del runtime, se convierten cabeceras firmadas a texto y cuerpos
  de archivo a bytes para Fetch. Se conserva la firma SHA-256 y se evitan
  checksums opcionales con codificación chunked.
- El build corrige el manejo de cuerpos JavaScript nulos en urllib3 para
  respuestas HEAD/204. Falla explícitamente si una actualización del proveedor
  exige revisar esa corrección.
- `tzdata` proporciona las zonas horarias ausentes en WebAssembly.

## Validación y bloqueos conocidos

Pasaron 162 pruebas de Django, Ruff, la comprobación de migraciones y la
compilación del Worker en GitHub Actions. Las pruebas remotas verificaron login,
listados autenticados, transacciones PostgreSQL con rollback y bloqueo de filas,
contraseñas existentes y subida, lectura y borrado de un archivo sintético en R2.
Los usuarios y archivos temporales se eliminaron; los datos existentes se
conservaron. El Worker de prueba aislado también fue eliminado.

Persisten dos problemas distintos:

1. El límite de CPU gratuito interrumpe peticiones reales con HTTP 503. El Django
   actual no puede considerarse estable en ese plan solo porque compile en CI.
2. La integración de Cloudflare con GitHub informó
   `This Worker does not exist on your account` al crear previews. La autorización
   OAuth de Wrangler usada en las pruebas no permite leer la API de Builds para
   reparar esa vinculación. El despliegue directo con Wrangler sí se completó.

Las pruebas locales o de CI deben usar su propia base PostgreSQL, nunca la base
de producción. Las migraciones de Supabase siguen siendo una operación explícita.

Referencias oficiales consultadas el 24 de septiembre de 2026:

- [Django en Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/django/).
- [Límites de Workers](https://developers.cloudflare.com/workers/platform/limits/).
- [PostgreSQL desde Python Workers](https://developers.cloudflare.com/hyperdrive/examples/python-workers/).
