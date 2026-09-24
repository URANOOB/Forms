# Formularios institucionales

La plataforma funciona ahora sin espacios de trabajo: formularios, respuestas y métricas
se gestionan en un panel común según permisos por rol. La institución se recoge mediante
los campos del formulario y puede buscarse en los datos recibidos. Las referencias antiguas
a espacios en esta documentación describen el diseño anterior. Las relaciones históricas
se conservan internamente para compatibilidad; ya no determinan permisos ni se administran.
Los nuevos enlaces usan `/f/<uuid>/`; los enlaces anteriores siguen funcionando.

Monolito Django con PostgreSQL y Django Unfold. Incluye la base administrativa,
constructor visual, formularios públicos sin registro y respuestas privadas en el backend.
La aplicación todavía no está desplegada en Internet.

## Desarrollo local

Requisitos: Python 3.12–3.14 (validado con 3.13), [uv](https://docs.astral.sh/uv/)
y Docker con el motor encendido. Ejecutar desde la raíz del repositorio:

```powershell
Copy-Item .env.example .env
uv sync --locked
docker compose up -d --wait
uv run python manage.py migrate
uv run python manage.py setup_roles
uv run python manage.py seed_demo
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Abrir <http://127.0.0.1:8000/admin/>. En macOS/Linux, usar `cp .env.example .env`.

Para ejecutar con la base Supabase y los archivos R2 ya trasladados, arrancar
explícitamente con su configuración (este es el entorno activo del servidor local):

```powershell
uv run --env-file .env.supabase python manage.py runserver 127.0.0.1:8000
```

Los cambios realizados en ese entorno se guardan en Supabase/R2. Mantener los
comandos de pruebas sobre `.env` local, sin `--env-file .env.supabase`.

El puerto PostgreSQL local es **55432**, limitado a localhost. La contraseña del
Compose es exclusivamente de desarrollo. `docker compose stop` detiene la base
conservando los datos. No ejecutar `down -v` si se desea conservarlos.

El seed, exclusivo de `settings.local`, es idempotente: crea **Demo Workspace** y
**Registro de pacientes**, versión 1, sección **Información personal**, campos Nombre,
Documento, Correo y una selección Sí/No. No contiene datos de pacientes. Su autor
técnico está inactivo y no tiene contraseña. Usar `createsuperuser` para acceder.

## Alcance disponible

- Admin Unfold en español, inicio institucional, formularios, usuarios y permisos.
- Usuario UUID personalizado desde la primera migración y workspace institucional.
- Form, FormVersion, FormSection, FormField, FieldOption y ConditionalRule.
- Crear formularios con versión inicial, editar metadata y archivar desde el panel.
- Constructor de tarjetas para preguntas, opciones, secciones, imágenes y condiciones
  encadenadas. Duplicación, orden, obligatoriedad y vista previa interactiva.
- Editar un formulario publicado crea un nuevo borrador; las versiones anteriores
  y sus respuestas permanecen intactas. Publicar activa la nueva versión.
- Personal limitado a su workspace activo; usuarios y grupos sólo para superusuarios.
- Restricciones de integridad, protección de versiones publicadas en escrituras
  ordinarias y pruebas sobre PostgreSQL real.
- Publicación y pausa, URL pública por formulario, validación cliente/servidor,
  lógica condicional y prevención de envíos duplicados.
- Respuestas privadas con búsqueda, filtros por formulario/fecha/estado y detalle
  por sección. Cada envío conserva la versión y los campos que fueron respondidos.

## Publicar y consultar respuestas

**Formularios** abre una galería con tarjetas y miniaturas de los campos reales.
Puedes buscar, filtrar por estado o por formularios propios, ordenar y alternar
tarjetas/lista. El menú de cada tarjeta conserva publicación, pausa, archivado y
enlaces de respuestas/compartir según permisos.

La franja superior ofrece un formulario en blanco y cinco plantillas institucionales.
Seleccionar una plantilla abre directamente el constructor con el nombre, descripción,
campos y opciones sugeridos. El formulario en blanco abre el mismo editor. El espacio
del usuario se selecciona automáticamente; un superusuario puede elegirlo en el editor.
El registro se crea al guardar, previsualizar, publicar o subir la primera imagen.
Abrir la página por sí solo no crea formularios. Nunca publica automáticamente.
Las plantillas viven en `apps/forms/presets.py` y no requieren tablas adicionales.

1. En **Formularios**, abre una tarjeta o crea un formulario para entrar al constructor.
2. Configura las preguntas, guarda un borrador y prueba **Vista previa**.
3. Pulsa **Publicar** y luego **Copiar enlace**. La URL no cambia entre versiones.
4. Las personas responden sin cuenta. Los envíos aparecen en **Respuestas** y en
   **Ver respuestas de este formulario**, sólo para personal autorizado.
5. **Guardar y pausar recepción** deshabilita el enlace sin borrar los datos recibidos.

La ruta incluye el workspace para evitar colisiones de slug:
`/f/demo-workspace/registro-pacientes/`. En desarrollo se abre con
`http://127.0.0.1:8000` como origen. **localhost sólo funciona en tu propio equipo**;
para compartir por Internet se necesita desplegar Django y configurar un dominio HTTPS.
No se publica automáticamente un borrador creado por el seed.

`setup_roles` crea **Administrator**, **Manager**, **Reviewer** y **Viewer** sin datos
demo; también se ejecuta desde el seed. Los dos primeros reciben permisos Django
`view/add/change` sobre los modelos de forms; los otros, `view`. Ninguno recibe delete.
El comando añade permisos base sin quitar asignaciones personalizadas. La creación
de la versión inicial es automática; la clonación se reserva para el constructor.
Todos los grupos pueden consultar respuestas de su workspace; Administrator, Manager
y Reviewer pueden cambiar su estado, mientras Viewer sólo lee. Los datos enviados
no se editan desde el admin. Ejecutar `setup_roles` al actualizar permisos.
Administrar usuarios/grupos/workspaces requiere `is_superuser`. Para el personal,
asignar `is_staff`, workspace y grupo. Los grupos no evitan el aislamiento por workspace.

## Estructura

- `config/`: settings local/production, URLs y entradas WSGI/ASGI.
- `apps/accounts/`: User basado en AbstractUser, Workspace y comando de grupos.
- `apps/forms/`: modelos de formularios, admin, migraciones, seed y tests.
- `apps/submissions/`: recepción pública, validación, almacenamiento y admin de respuestas.
- `templates/public/` y `static/forms/`: interfaz pública responsive, sin librerías frontend.
- `templates/admin/`: inicio institucional sobre Unfold.
- `docs/`: contexto y decisiones; `.github/workflows/`: comprobaciones CI.

## Configuración

`.env` no se versiona. `manage.py` usa `config.settings.local` por defecto.
Variables principales: `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`,
`DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS`. Fechas conscientes de zona
horaria (`USE_TZ=True`), UTC internamente y como zona predeterminada.
WSGI/ASGI usan `config.settings.production`, que exige secreto de al menos 50
caracteres y hosts explícitos. En producción, fijar `DJANGO_SETTINGS_MODULE`
explícitamente y no reutilizar `.env` de desarrollo. Generar un secreto aleatorio
con `uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.

Para Supabase, cambiar `DATABASE_URL` por una conexión PostgreSQL directa o el
session pooler, usando TLS (`?sslmode=require`). No se utiliza el SDK, Auth ni
Storage de Supabase. El rol de producción debe tener privilegios mínimos;
ejecutar tests sólo contra una base dedicada con permiso de crear la base de tests.

El proveedor de archivos se elige con `FILE_STORAGE=local` (predeterminado) o `r2`.
R2 almacena imágenes y adjuntos en un bucket privado; Django conserva el control de
acceso. En local se usan `media/` y `private_uploads/`, respectivamente. No se envían
correos. Consultar [setup y traslado a Supabase + R2](docs/supabase-r2.md) antes de
cambiar la conexión o el proveedor; incluye el comando de copia con verificación.

## Verificación

```powershell
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test --noinput
uv run ruff check .
uv run ruff format --check .
uv run python manage.py collectstatic --noinput
```

GitHub Actions ejecuta estas comprobaciones con PostgreSQL 17. Las dependencias
exactas están en `uv.lock`. Todas las modificaciones de esquema requieren migrations.

## Pendiente

Los campos de una versión publicada son inmutables. El proveedor R2 está integrado;
su activación y el traslado requieren configurar las credenciales del destino.
Correo y auditoría de lecturas permanecen pendientes.
La conexión de GitHub no despliega por sí sola este servidor Django: ver
[compatibilidad con Cloudflare gratuito](docs/cloudflare-deployment.md).
Para Vercel, consultar la [configuración de arranque y variables](docs/vercel-deployment.md).

Consultar [decisiones de arquitectura](docs/architecture.md) y
[contexto original](docs/project-brief.md). La ampliación de formularios públicos y
respuestas fue solicitada después de Foundation; ver [runtime público](docs/public-forms.md).
El uso y los límites del editor están en [constructor visual](docs/form-builder.md).
