# Arranque de Django en Vercel

Vercel detecta `manage.py` y lee los ajustes antes de cargar las aplicaciones.
El proyecto declara `config.wsgi:application` como entrypoint en `pyproject.toml`.
Cuando Vercel establece `VERCEL=1`, tanto los comandos como WSGI/ASGI seleccionan
`config.settings.production`, incluso si `DJANGO_SETTINGS_MODULE` está vacío o
conserva por error la configuración local o experimental de Workers.
Se respeta únicamente la configuración temporal `_vercel_collectstatic_settings`
que genera el builder para publicar los estáticos en su CDN.
Los dominios exactos que Vercel proporciona en `VERCEL_URL` y
`VERCEL_PROJECT_PRODUCTION_URL` se añaden a los hosts y orígenes CSRF permitidos,
conservando los dominios propios configurados sin aceptar `*.vercel.app`.

Los enlaces de Unfold se resuelven durante las peticiones, para que la detección
pueda serializar los ajustes sin iniciar el registro de aplicaciones.

## Variables del proyecto

Configurar estas variables en los entornos de Vercel donde se vaya a desplegar:

- `DJANGO_SETTINGS_MODULE=config.settings.production` (opcional, pero explícito).
- `DJANGO_SECRET_KEY`: secreto estable de al menos 50 caracteres.
- `DJANGO_ALLOWED_HOSTS`: dominios concretos separados por comas, sin `https://`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: esos orígenes con `https://`.
- `PUBLIC_BASE_URL`: origen HTTPS canónico para compartir formularios, sin ruta.
- `DJANGO_TIME_ZONE=America/Bogota`: fechas, filtros y períodos en hora de Colombia;
  los instantes se conservan en UTC en PostgreSQL.
- `DATABASE_URL`: conexión de Supabase con TLS, contraseña codificada en la URL.
- `FILE_STORAGE=r2`.
- `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` y `R2_ENDPOINT`
  (o `R2_ACCOUNT_ID`).
- Opcionales: `DATABASE_CAPACITY_BYTES=500000000` y
  `R2_FREE_STORAGE_REFERENCE_BYTES=10000000000`.

No copiar credenciales a Git ni hacer público el bucket. `.vercelignore` excluye
los secretos locales, archivos subidos y artefactos de Cloudflare. Vercel recoge
los estáticos mediante `collectstatic`; los documentos privados permanecen en R2.
`vercel.json` incluye explícitamente las plantillas, porque el empaquetador de
Python excluye por defecto cualquier carpeta llamada `public`.
El build no debe ejecutar migraciones ni crear datos de demostración.

Usar el preset Django y el directorio raíz del repositorio. Eliminar cualquier
comando de build o deploy de Wrangler que se haya copiado a los ajustes de Vercel.
Los secretos, la base y los dominios deben estar configurados también durante el
build; no se reemplazan por valores ficticios para ocultar errores de producción.

## Dominio de producción

El dominio principal es `www.logicforms.xyz`; `logicforms.xyz` redirige a él con
308 desde Vercel. Ambos deben figurar en `DJANGO_ALLOWED_HOSTS` y sus orígenes
HTTPS en `DJANGO_CSRF_TRUSTED_ORIGINS`. Configurar
`PUBLIC_BASE_URL=https://www.logicforms.xyz` para que los enlaces de la galería,
el editor y las publicaciones coincidan aunque se acceda por una URL de Vercel.
Cambiar variables requiere un nuevo despliegue. La asociación del dominio al
proyecto no demuestra que DNS ni el certificado TLS estén listos: comprobarlos
por separado y probar el login con CSRF al terminar la propagación.

## Alcance y validación

Esta corrección resuelve la lectura de ajustes y selecciona un arranque de
producción. No demuestra por sí sola que el despliegue remoto sea correcto.
Los tests reproducen la detección del builder y comprueban el menú, la selección
de producción y los errores cuando falta configuración.

El flujo de archivos todavía requiere adaptación para cargas o descargas que
superen el límite de 4,5 MB por petición/respuesta de Vercel Functions, incluido
el importador de hasta 5 MB. Resolverlo antes de considerar soportados esos
archivos en producción. El plan Hobby se limita a uso personal y no comercial.

- [Django en Vercel](https://vercel.com/docs/frameworks/full-stack/django).
- [Límites de Functions](https://vercel.com/docs/functions/limitations).
- [Plan Hobby](https://vercel.com/docs/plans/hobby).
