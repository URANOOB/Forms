# Notificaciones por correo

## Arquitectura

`apps/notifications` contiene la selección de destinatarios, outbox, envío, eventos
firmados y panel Correos. Resend es el único proveedor; toda llamada al SDK oficial
Python pasa por `resend_client.py`. Se fijan sus dependencias en `uv.lock` y las del
Worker experimental en `pylock.toml`.

La migración `notifications.0001_initial` crea:

- `FormNotificationSettings`: tres interruptores y el stable key del campo EMAIL.
- `EmailNotification`: destinatario, evento, estado, referencias, asunto, ID del
  proveedor, clave única de idempotencia y fechas. No almacena cuerpos HTML/texto.
- `EmailSendAttempt`: cada llamada al proveedor, su resultado y error sanitizado.
- `EmailDeliveryEvent`: identificador único, tipo y fechas; no guarda el payload.
- `EmailSuppression`: destinatarios con rebote, queja o supresión, para no insistir.

La respuesta o revisión y la notificación se crean en la misma transacción. Solo
después de confirmar se intenta enviar mediante `transaction.on_commit`. El fallo
de Resend queda registrado y no revierte la respuesta ni su aprobación/rechazo.
Un lock de fila reclama el envío; la petición HTTP ocurre fuera de la transacción,
con timeout de diez segundos. La concesión dura dos minutos para poder recuperar
procesos interrumpidos sin bloquear permanentemente un correo.

## Eventos y destinatarios

| Evento | Disparador | Destinatario |
| --- | --- | --- |
| Nueva respuesta | Se guarda una respuesta nueva | Email del creador del formulario |
| Solicitud aprobada | UNDER_REVIEW → VALIDATED | Respondiente |
| Solicitud rechazada | UNDER_REVIEW → REJECTED | Respondiente |

El editor permite activar cada aviso y elegir «Automático» o un campo de tipo
EMAIL. La selección usa exclusivamente el tipo semántico y busca el stable key en
la versión histórica de la respuesta. No interpreta nombres de preguntas.
Automático requiere exactamente un campo EMAIL contestado con dirección válida.
Si faltan correos o hay varios candidatos, registra SKIPPED y su explicación.
Un campo explícito sin valor válido no recurre a otro destinatario.

La clave única incluye evento, respuesta o revisión y destinatario lógico. Una
petición repetida no duplica; una nueva revisión tras una reapertura sí puede
generar otro aviso. Cambiar configuración no reenvía notificaciones históricas.
Los avisos desactivados también quedan como SKIPPED, sin intentos.

El aviso interno contiene formulario, fecha, identificador y enlace privado; no
incluye respuestas ni documentos. El aprobado contiene una confirmación breve.
El rechazado usa el motivo existente en `SubmissionReview.note`, escapado en HTML,
y enlaza al formulario público para volver a enviarlo. Son plantillas Django HTML
y texto, con estilos en línea, sin React ni contenido editable en Correos.

## Variables

| Variable | Uso |
| --- | --- |
| `EMAIL_PROVIDER=resend` | Único proveedor admitido |
| `EMAIL_FROM=LogicForms <notificaciones@logicforms.xyz>` | Remitente verificado |
| `EMAIL_API_KEY` | Secreto de Resend; nunca versionar |
| `RESEND_WEBHOOK_SECRET` | Secreto `whsec_…` del endpoint de Resend |
| `EMAIL_NOTIFICATIONS_ENABLED=False` | Desactivado por defecto; `True` activa envíos |
| `EMAIL_TEST_RECIPIENT` | Redirige TODOS los destinatarios válidos a una dirección de pruebas |
| `PUBLIC_BASE_URL=https://www.logicforms.xyz` | Origen canónico de los enlaces |

Para activar, se validan proveedor, API key presente, remitente, destinatario de
pruebas y URL pública. Una configuración incompleta impide arrancar con envíos
activados. El webhook devuelve 503 si falta su secreto. Mantener estas variables
en los secretos del entorno, nunca en el navegador ni en archivos versionados.

En pruebas se usa el buzón aprobado por el responsable mediante
`EMAIL_TEST_RECIPIENT`. La redirección se fija al crear cada notificación y la UI y
el mensaje muestran «Prueba». Para producción, vaciar esa variable: cada formulario
usará su creador y el campo del respondiente. Las notificaciones ya creadas no
cambian de destinatario al modificar variables. No reactivar en masa omitidos.

## Webhook y estados

`POST /webhooks/resend/` es el único endpoint nuevo exento de CSRF. Se verifica el
body original y los encabezados `svix-id`, `svix-timestamp`, `svix-signature` con
`resend.Webhooks.verify`. Firmas inválidas reciben 400; no se guarda JSON sin verificar.
Se limita el body a 64 KiB. Los eventos soportados son:

`email.sent`, `email.delivered`, `email.delivery_delayed`, `email.failed`,
`email.bounced`, `email.complained`, `email.suppressed`.

Los duplicados no duplican historial. Un evento firmado cuyo mensaje todavía no
se conoce se retiene sin contenido y se asocia después del envío. Un advisory lock
de PostgreSQL por ID del proveedor serializa ese encuentro con la confirmación.
Eventos atrasados no degradan DELIVERED a SENT ni estados terminales de rechazo.
Los eventos de generaciones anteriores permanecen auditados sin reemplazar el
estado del último envío; una queja o rebote sí bloquea futuros envíos al destinatario.

Estados: PENDING, SENDING, SENT, DELIVERED, DELIVERY_DELAYED, FAILED, BOUNCED,
COMPLAINED, SUPPRESSED y SKIPPED. SENT significa aceptación de Resend; DELIVERED,
aceptación por el servidor del destinatario, no lectura ni ubicación en bandeja.

## Reintentos

Solo superusuarios pueden reintentar FAILED desde Correos mediante POST con CSRF.
No hay endpoints para editar estados, IDs, fechas o eventos, ni siquiera en admin.
Dos reintentos simultáneos reclaman una sola ejecución. Fallos de transporte
conservan clave y hash del payload; si cambia el contenido se exige revisión.

Resend conserva claves durante 24 horas. Se aplica un límite conservador de 23
horas desde el primer intento para fallos sin confirmación del proveedor; después
no se reenvía automáticamente, pues podría duplicarse un envío aceptado antes.
Un `email.failed` confirmado puede iniciar una nueva generación con clave nueva.
DELIVERED, BOUNCED, COMPLAINED, SUPPRESSED y SKIPPED no ofrecen reintento.

```powershell
uv run python manage.py retry_email_notifications --limit 50
```

Este comando también procesa PENDING y concesiones SENDING vencidas. Requiere un
entorno con envíos habilitados. No hay Celery, Redis ni tarea programada creada.
Tras interrupciones del proceso puede ser necesario ejecutar el comando.

## UI y privacidad

Correos usa los componentes y colores existentes: cuatro métricas, filtros de
servidor, paginación y detalle lateral, que pasa debajo de la tabla en móvil.
Las métricas corresponden al conjunto filtrado; «Enviados hoy» usa la zona local.
Fallidos incluye FAILED, BOUNCED, COMPLAINED y SUPPRESSED; Pendientes incluye
PENDING, SENDING y DELIVERY_DELAYED. SKIPPED no se cuenta como fallo de entrega.

Consulta requiere `submissions.view_submission`. La tabla siempre enmascara las
direcciones y el detalle solo las revela completas a superusuarios. El panel no
expone asunto, cuerpos, documentos, respuestas, motivo de rechazo ni payloads.
El historial de respuestas incorpora envío y entrega. Los errores del proveedor
se sustituyen por diagnósticos permitidos, sin persistir mensajes arbitrarios.
Los modelos operativos sobreviven al purgado de respuestas mediante FK nullable.

## Activación en Resend y Vercel

1. Verificar el dominio de envío en Resend. Publicar exactamente los registros
   SPF/DKIM indicados y revisar DMARC según la política del dominio; esperar DNS.
2. Configurar el remitente definitivo y una API key con el alcance necesario.
3. Añadir las variables anteriores en Vercel, inicialmente con el destinatario de
   pruebas y envíos desactivados. Ejecutar migraciones en la base correcta.
4. Cuando se autorice desplegar el endpoint, crear un webhook de Resend para
   `https://www.logicforms.xyz/webhooks/resend/` con los siete eventos anteriores.
5. Guardar su secreto en `RESEND_WEBHOOK_SECRET`, activar envíos y hacer redeploy.
6. Generar una respuesta y una revisión sintéticas; verificar PENDING → SENT →
   DELIVERED en Correos y los registros del proveedor. Confirmar la recepción real.
7. Al pasar a destinatarios reales, vaciar `EMAIL_TEST_RECIPIENT` en producción y
   verificar correos de creadores y selección de campo en cada formulario.

Esta implementación no despliega, crea webhooks remotos ni modifica DNS/Vercel.

## Comprobaciones y límites

Pruebas unitarias y transaccionales cubren selección histórica, settings, rollback,
fallo del proveedor sin pérdida de respuesta/revisión, concurrencia, idempotencia,
reaperturas, reintentos, supresiones, firmas reales del helper, duplicados, eventos
tempranos/atrasados, privacidad, permisos, filtros y paginación. Playwright cubre
Correos en escritorio/móvil y persistencia de settings en el editor.

```powershell
uv run python manage.py test --noinput
uv run --with playwright python manage.py test apps.notifications.tests.browser_emails --noinput
```

Ejecutar exclusivamente en PostgreSQL de pruebas, con credenciales de envío falsas
y envío global desactivado fuera de tests que lo sobreescriben con mocks.

Limitaciones de v1: on_commit es síncrono y añade latencia hasta el timeout; no hay
worker permanente ni reintentos programados. Si una función serverless se termina
tras confirmar la operación, el outbox requiere recuperación por comando. Sin
webhook desplegado y configurado no puede verificarse la actualización real a
DELIVERED en la aplicación. Los cuerpos históricos no se conservan: un cambio de
plantilla o configuración puede impedir un reintento ambiguo. La retención y
limpieza de metadatos operativos no se automatiza. Workers sigue experimental.

Referencias: [idempotencia de Resend](https://resend.com/docs/dashboard/emails/idempotency-keys),
[firmas de webhooks](https://resend.com/docs/webhooks/verify-webhooks-requests),
[dominios](https://resend.com/docs/dashboard/domains/introduction).
