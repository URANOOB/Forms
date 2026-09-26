# Inicio operativo

El inicio prioriza respuestas pendientes y sustituye las tarjetas de formularios
por una tabla paginada de actividad. Las métricas de usuarios, formularios publicados
y espacio libre del disco ya no forman parte de la vista principal.

## Períodos y estados

**Hoy**, **7 días**, **30 días** y **Todo** filtran por la fecha de recepción, en la
zona horaria de la aplicación. Los totales muestran el estado **actual** de esas
respuestas; no reconstruyen el estado que tenían en una fecha anterior.
**Pendientes** significa exclusivamente `SUBMITTED`; `UNDER_REVIEW` tiene su propio
contador. Las proporciones de validadas y rechazadas usan el total del período.

Los contadores y filas enlazan a Respuestas conservando fechas, estado o formulario.
La tabla ordena por pendientes, en revisión y última recepción. Incluye las
respuestas conservadas de formularios eliminados, identificándolos como tales.

El gráfico presenta conteos diarios, incluyendo ceros, y compara con el período
anterior. El día actual está en curso; la comparación anterior comprende días
completos. No se calcula porcentaje cuando el período anterior tuvo cero respuestas.
En **Todo**, los contadores incluyen todo el historial y el gráfico muestra los
últimos 30 días, indicado en su encabezado. Sus puntos admiten foco de teclado
y hay una tabla alternativa de datos diarios.

## Actividad reciente

Los últimos doce eventos combinan envíos, revisiones y cargas de adjuntos ordenados
por su fecha real. El filtro se aplica a la fecha del evento, por lo que una revisión
reciente de una respuesta antigua puede aparecer aunque esa respuesta no esté en
los contadores del período. No se muestran los datos personales de las respuestas
ni los comentarios de revisión en este listado.

`submissions.0005` añade `SubmissionFile.uploaded_at`. Los adjuntos nuevos guardan
su fecha de carga; los existentes quedan con `NULL` y no generan eventos con fechas
supuestas. Aplicar con `uv run python manage.py migrate`.

## Infraestructura

Se muestran tres tarjetas para superusuarios: **Base de datos**, **Archivos** y
**Correos**, con proveedor, uso, disponible o margen de referencia, límites y hora de consulta.
Se utiliza el entorno conectado: `.env` sigue mostrando almacenamiento local;
`uv run --env-file .env.supabase python manage.py runserver` usa Supabase y R2.
El entorno local no se presenta como si fuera la infraestructura remota.

PostgreSQL local usa `pg_database_size(current_database())`. En Supabase se suman
los tamaños de las bases del proyecto (`sum(pg_database_size(datname))` sobre
`pg_database`), siguiendo su documentación de tamaño de base. Esto incluye datos
e índices, pero no representa el disco completo ni el WAL. Las tablas contadas
pertenecen al esquema de la aplicación, sin sumar las tablas internas de Supabase.

`DATABASE_CAPACITY_BYTES` configura la capacidad en bytes. Para el plan Free
confirmado por el usuario, `.env.supabase` tiene `500000000` (500 MB). Se calcula
disponible como capacidad menos uso, con mínimo cero; la barra se limita al 100 %
pero el texto conserva el porcentaje real si se supera la capacidad.

R2 enumera todas las páginas de objetos del bucket por la API S3 y suma sus tamaños
actuales, incluidos archivos que no estén registrados en Django. No descarga sus
contenidos. Dos alias de storage sobre el mismo bucket se cuentan una sola vez.
Se cuentan objetos completos; no partes de cargas multipart aún sin completar.
El entorno local mide los archivos presentes en las carpetas de imágenes/adjuntos,
incluidos los que no tengan registro en la base, sin seguir enlaces simbólicos.

R2 no tiene una capacidad máxima por bucket. El plan gratuito incluye 10 GB-mes
mensuales de almacenamiento Estándar compartidos por la cuenta; la facturación
considera el promedio de picos diarios, no solo el tamaño actual de este bucket.
Por eso `R2_FREE_STORAGE_REFERENCE_BYTES=10000000000` produce una **Referencia
gratuita** y un **Margen de referencia**, no un saldo mensual ni una cuota que
bloquee cargas. La aclaración es visible en la tarjeta. Si se detecta almacenamiento
de acceso no frecuente, se omite esa comparación porque no recibe la franquicia.

Las unidades mostradas son decimales (MB = 1.000.000 bytes, GB = 1.000.000.000),
para coincidir con las capacidades configuradas, sin etiquetar MiB como MB.
Si no hay capacidad conocida no se inventa un disponible ni un porcentaje.

La tarjeta **Correos** consulta `GET https://api.resend.com/usage` desde el cliente
centralizado de Resend. Muestra el consumo, límite, saldo, porcentaje, enviados,
recibidos y próxima renovación para las cuotas diaria y mensual de toda la cuenta,
incluidos envíos de otras aplicaciones. Usa `used` del proveedor para calcular el
saldo; no estima el consumo a partir de las notificaciones locales ni fija las
cuotas del plan Free. El margen de envío para hoy es el menor saldo entre ambas
cuotas. Si Resend devuelve `null` en el límite diario, muestra **Sin límite diario**
y usa el saldo mensual. En planes de pago, ese saldo representa la cuota incluida;
Resend puede permitir sobreconsumo con cargo. Se avisa al consumir el 80 % o más.
Los filtros del panel no cambian estos períodos y las fechas de renovación vienen
del proveedor, mostradas en la zona horaria de la aplicación.

Se utiliza `EMAIL_API_KEY` o, si está definida, `RESEND_USAGE_API_KEY`: una clave de
la **misma cuenta** con permisos para consultar el consumo. Esto permite mantener
una clave restringida para enviar. La clave de consulta no modifica la configuración
global del SDK de envío. No hace falta activar `EMAIL_NOTIFICATIONS_ENABLED` para
consultar las métricas. Sin clave, con permisos insuficientes, ante fallos de red
o datos incompletos se muestra **No disponible**, nunca ceros o límites supuestos.
La consulta tiene timeout de cinco segundos y no envía correos. Se almacena por
separado durante cinco minutos (30 segundos en errores), aislada por un hash de
la clave y sin conservar credenciales ni respuestas completas. La caché no se
reutiliza después de la próxima renovación indicada por Resend.

Fuente: [Resend Retrieve Usage](https://resend.com/docs/api-reference/usage/retrieve-usage).

Las lecturas completas de almacenamiento se almacenan en caché cinco minutos, separadas por base,
bucket y capacidades. Los errores se guardan solo 30 segundos. Las llamadas a R2
tienen tiempos de espera acotados y un presupuesto de enumeración de diez segundos;
si fallan o se interrumpen, no se presenta el total parcial como completo ni como cero.
Para buckets masivos, sustituir la enumeración síncrona por métricas agregadas o
un proceso de medición en segundo plano.

Los datos se consultan al abrir o recargar el inicio. La pantalla abierta no hace
sondeo automático ni recibe actualizaciones en tiempo real. En Vercel la caché
actual es local a cada instancia, por lo que las horas de consulta pueden variar
entre instancias sin que cambie la fuente de los datos.

Fuentes: [Supabase Free](https://supabase.com/pricing),
[tamaño de bases en Supabase](https://supabase.com/docs/guides/platform/database-size),
[precios y cálculo de R2](https://developers.cloudflare.com/r2/pricing/) y
[límites de R2](https://developers.cloudflare.com/r2/platform/limits/).

## Verificación

`uv run python manage.py test apps.accounts.tests.test_dashboard apps.accounts.tests.test_infrastructure --noinput`

Comprueba períodos, límites de fecha con zona horaria, métricas, tendencia, permisos,
actividad por fecha de evento, enlaces, paginación, medición de objetos no registrados,
fallos parciales, capacidades excedidas, unidades y aislamiento de caché. Las pruebas
se ejecutan localmente; no usar `.env.supabase` con el test runner.

`uv run --with playwright python manage.py test apps.accounts.tests.browser_dashboard --noinput`

Recorre filtros, enlaces, gráfico y navegación móvil en Edge; genera capturas con
datos ficticios en el directorio temporal.
