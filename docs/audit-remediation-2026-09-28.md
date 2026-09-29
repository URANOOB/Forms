# Correcciones de la auditoría del 28 de septiembre de 2026

El informe fechado se conserva como antecedente. Esta entrega corrige los nueve
hallazgos funcionales y reúne los cambios pendientes de borradores, duplicados y
desarrollo local con Docker.

1. El esquema comprueba el presupuesto agregado antes de guardar o publicar:
   10.000 parámetros y 200 archivos por petición, reservando parámetros para
   controles internos y eliminación de adjuntos durante la edición. El navegador
   comprueba cantidades antes de enviar y los rechazos del parser público se
   presentan como errores recuperables, antes de acceder a POST desde CSRF.
   Los límites existentes de bytes y tamaño por archivo siguen aplicándose.
2. Notificaciones, identificación de respuestas y campos de duplicados forman
   parte del estado editable: cambios pendientes, protección de salida, historial
   y guardado previo a la vista previa.
3. Detalle, CSV, Excel y reportes comparten las etiquetas históricas de cuadrículas.
4. Los números históricos finitos e integrales almacenados como float participan
   en la comparación de duplicados. No se inventa precisión perdida previamente.
5. Las escrituras de borradores comparan su revisión dentro de un bloqueo entre
   pestañas. Una edición divergente crea otro borrador con un token de envío
   propio. Descartar o confirmar solo elimina la revisión que conoce esa pestaña.
   El selector permite recuperar los distintos borradores conservados durante
   24 horas; sin Web Locks, las escrituras utilizan claves privadas por página.
6. Los límites numéricos deben admitir algún entero no negativo representable.
   Las longitudes de teléfono y correo deben intersectar su dominio válido.
7. Eliminar adjuntos al editar crea tareas durables dentro de la transacción.
   Las compensaciones de cargas fallidas se registran después del rollback y
   procesan cada archivo independientemente, dejando reintentos si falla el almacenamiento.
8. El panel conserva un administrador activo con acceso. Un bloqueo transaccional
   de PostgreSQL serializa edición y eliminación individual o masiva antes de
   validar, incluida la edición concurrente de dos administradores.
9. «Desarchivar como borrador» conserva versiones y respuestas, exige permiso de
   edición y registra la acción. El enlace público permanece cerrado hasta publicar.

## Recuperación de acceso administrativo

Si una intervención externa o datos antiguos dejaron la plataforma sin acceso,
un operador autorizado de infraestructura puede ejecutar, en el entorno correcto:

```sh
python manage.py createsuperuser
```

La contraseña se introduce de forma interactiva, nunca se añade al repositorio.
Para una cuenta existente con rol correcto puede usarse
`python manage.py changepassword USUARIO`. Verificar el ingreso al panel antes de
retirar cualquier cuenta de recuperación. Las protecciones del panel no sustituyen
los controles sobre SQL directo, scripts externos o credenciales de infraestructura.

## Riesgos operativos que requieren trabajo independiente

Los riesgos de escala enumerados en la auditoría no se presentan como resueltos:
la detección de duplicados sigue recorriendo respuestas históricas, las cargas
de archivos todavía comparten la transacción de recepción y el descubrimiento
de columnas de reportes recorre respuestas antes de paginar. No hay mediciones
de carga de producción en esta entrega.

La programación de mantenimiento debe configurarse en la infraestructura que
ejecuta producción; el repositorio mantiene los comandos
`clear_rate_limits`, `retry_file_deletions` y `retry_email_notifications`.
La cola durable evita perder las tareas, pero requiere ejecutar los reintentos.
No se afirma haber configurado un programador externo ni probado entrega real
de correo, caídas de R2 o restauración de copias de producción.

## Validación

Las regresiones utilizan PostgreSQL local en Docker y Chromium: multipart real,
límites de esquema, exportaciones históricas, floats, rollback y reintentos de
archivos, administradores concurrentes, desarchivado, historial de ajustes,
vista previa y conflictos entre pestañas. La suite de navegador está incluida
en el flujo de CI del repositorio.
