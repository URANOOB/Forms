# Usuarios y roles

La plataforma utiliza dos roles:

- **Administrador:** acceso completo, incluida la creación, edición, desactivación,
  eliminación de usuarios y asignación de roles.
- **Operador:** puede crear, editar, publicar, archivar y eliminar formularios, así como
  consultar y editar respuestas, enviarlas a la papelera y restaurarlas.
  No puede purgar respuestas ni administrar usuarios o permisos.

Durante la revisión, solo el responsable asignado o un administrador puede editar
los datos, cambiar el estado, añadir notas, modificar incidencias o enviar la respuesta
a la papelera/restaurarla. Los demás operadores conservan acceso de lectura.
El purgado definitivo se realiza desde la papelera, con confirmación, y exige administrador.
La migración renombra el grupo `Visor` a `Operador` conservando miembros y permisos;
si ambos existen, los combina.

El administrador asigna el rol desde **Usuarios → Acceso a la plataforma**. El acceso
a esta administración se comprueba en el servidor, también al abrir una URL directa.
Las cuentas inactivas no pueden iniciar sesión. Las cuentas internas de los datos de
ejemplo permanecen inactivas y no aparecen en el listado ni en el contador de usuarios.

Ejecuta `python manage.py setup_roles` después de las migraciones al preparar un
entorno. El comando configura los dos grupos, sustituye los roles anteriores y
normaliza las cuentas existentes. Los administradores usan `is_superuser`; ambos
roles usan `is_staff` para acceder a la plataforma. Los permisos de Operador abarcan las
aplicaciones de formularios y respuestas. La gestión de usuarios queda reservada a
superusuarios activos. Los permisos se asignan por rol, sin excepciones individuales.

La eliminación respeta las relaciones protegidas de la base de datos: si un usuario
es autor de formularios, se puede desactivar su cuenta para conservar la autoría.
Las contraseñas se establecen al crear la cuenta o desde su formulario de cambio;
no se guardan credenciales en el código del proyecto.
