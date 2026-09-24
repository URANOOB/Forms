# Usuarios y roles

La plataforma utiliza dos roles:

- **Administrador:** acceso completo, incluida la creación, edición, desactivación,
  eliminación de usuarios y asignación de roles.
- **Visor:** puede crear, editar, publicar, archivar y eliminar formularios, así como
  consultar, editar y eliminar respuestas. No puede administrar usuarios ni permisos.

El administrador asigna el rol desde **Usuarios → Acceso a la plataforma**. El acceso
a esta administración se comprueba en el servidor, también al abrir una URL directa.
Las cuentas inactivas no pueden iniciar sesión. Las cuentas internas de los datos de
ejemplo permanecen inactivas y no aparecen en el listado ni en el contador de usuarios.

Ejecuta `python manage.py setup_roles` después de las migraciones al preparar un
entorno. El comando configura los dos grupos, sustituye los roles anteriores y
normaliza las cuentas existentes. Los administradores usan `is_superuser`; ambos
roles usan `is_staff` para acceder a la plataforma. Los permisos de Visor abarcan las
aplicaciones de formularios y respuestas. La gestión de usuarios queda reservada a
superusuarios activos. Los permisos se asignan por rol, sin excepciones individuales.

La eliminación respeta las relaciones protegidas de la base de datos: si un usuario
es autor de formularios, se puede desactivar su cuenta para conservar la autoría.
Las contraseñas se establecen al crear la cuenta o desde su formulario de cambio;
no se guardan credenciales en el código del proyecto.
