# Pie de los formularios públicos

El formulario público, su vista previa y la confirmación de envío comparten un pie
con identidad, enlaces de privacidad, accesibilidad y ayuda, y la firma de LogicForms.
Los enlaces abren otra pestaña para conservar el formulario que se está completando.
La edición interna de respuestas no muestra este pie.

La página `/informacion/` contiene orientación de uso y accesibilidad. La sección de
privacidad es orientación general, no una política institucional ni una certificación.

Configuración opcional del entorno:

- `PUBLIC_INSTITUTION_NAME`: nombre visible; por defecto, `LogicForms`.
- `PUBLIC_SUPPORT_EMAIL`: dirección real de soporte. Si está vacío, la ayuda remite
  al equipo que compartió el formulario y no muestra un correo ficticio.
- `PUBLIC_PRIVACY_URL`: URL HTTPS de la política oficial. Si está vacío, el enlace
  lleva a la sección de orientación del portal.

No se publican direcciones de usuarios ni se usa el remitente de notificaciones
como correo de soporte. Estos ajustes no requieren migraciones.
