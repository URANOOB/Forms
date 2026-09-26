# Verificación de interfaz, correo y formularios públicos

Verificación local del 25 de septiembre de 2026 sobre PostgreSQL 17 local, con
datos sintéticos, archivos locales y sin envíos reales de correo.

Resultados:

- Suite Django: 268 pruebas aprobadas.
- Chromium: 15 pruebas aprobadas, incluyendo usuarios, reportes, accesibilidad,
  formularios públicos, galería, panel general, revisión de respuestas y correo.
- Importación de catálogos: reemplazo, reintento, cancelación, errores y reapertura aprobados.
- `manage.py check`, `makemigrations --check --dry-run` y `collectstatic --noinput`: correctos.
- Ruff (análisis y formato), sintaxis JavaScript y `git diff --check`: correctos.
- `wrangler deploy --dry-run`: compilación correcta, sin publicación.

Las pruebas nuevas cubren el cálculo y caché de cuotas de Resend, errores del
proveedor y credenciales de consulta; filtros y permisos de usuarios, conservación
de contraseñas, creación, edición, cambio de contraseña e inicio de sesión,
confirmación de eliminación y vistas móviles; selectores de reportes por teclado;
preferencias de accesibilidad persistentes, enlaces de errores, presentación a
320 CSS px con texto ampliado y apertura de ayuda sin perder respuestas.

Se actualizaron las expectativas antiguas del panel y de errores públicos para
comprobar la tarjeta de correos y el resumen accesible. Se corrigió el contraste
del aviso de descargas en reportes.

La integración continua ejecuta los nuevos recorridos de usuarios y accesibilidad.
La compatibilidad manual con lectores de pantalla y la auditoría completa WCAG
siguen descritas en [accesibilidad pública](public-accessibility.md); estas pruebas
automatizadas no constituyen una certificación de conformidad.

El despliegue requiere la migración aditiva
`notifications.0002_formnotificationsettings_internal_recipients` y sus dependencias.
