# Seguimiento de auditoría — 25 de septiembre de 2026

Este cambio resuelve cinco observaciones posteriores a la auditoría inicial:

- Límites compartidos y atómicos en PostgreSQL para formularios públicos y login.
  Cambiar cookies, solicitar tokens nuevos o alternar entre URL moderna/antigua no
  reinicia el contador. El login se limita por IP y por cuenta, incluso si no existe.
  Las ventanas comienzan con la primera solicitud; los rechazos no extienden el bloqueo.
  Las IPv6 se agrupan por /64. Un fallo del contador rechaza temporalmente la petición.
- Producción exige `FILE_STORAGE=r2`; ninguna omisión permite almacenamiento efímero.
  La configuración de R2 exige credenciales y endpoint HTTPS. El build de Workers
  utiliza configuración R2 ficticia sin acceder al almacenamiento para collectstatic.
- Propiedad durante la revisión aplicada en servidor a todas las modificaciones.
  Se comprueba sobre la fila bloqueada, incluyendo cambios de datos y borrado.
- Papelera con restauración, auditoría y revisión incrementada para invalidar ediciones
  antiguas. Purgado solo por administrador y con confirmación. Los fallos de eliminación
  en almacenamiento dejan tareas persistentes de reintento. Se renombra Visor a Operador.
- Identidad de columnas `(form_id, stable_key)` compartida por vista previa y XLSX.
  Etiquetas duplicadas se distinguen visualmente. Excel conserva los textos extensos
  en partes de 32.000 caracteres en una hoja adicional, siempre como texto literal.

## Configuración y despliegue

Aplicar `uv run python manage.py migrate --noinput` antes de servir esta versión,
con las variables del entorno correspondiente. Las migraciones añaden contadores,
campos de papelera y tareas de limpieza, y renombrarán el grupo existente sin perder miembros.
No se requiere volver a asignar roles manualmente.

Los límites pueden ajustarse mediante las variables `RATE_LIMIT_PUBLIC_READ`,
`RATE_LIMIT_PUBLIC_POST`, `RATE_LIMIT_PUBLIC_HOUR`, `RATE_LIMIT_LOGIN_IP` y
`RATE_LIMIT_LOGIN_ACCOUNT` de `.env.example`. Deben ser enteros positivos.
Considerar redes institucionales que comparten IP antes de reducir los límites.

Vercel utiliza exclusivamente `X-Vercel-Forwarded-For`, gestionada por la plataforma;
fuera de Vercel se utiliza `REMOTE_ADDR`. Workers utiliza `CF-Connecting-IP`.
No activar una cabecera de confianza en un servidor que acepte esa cabecera directamente
del cliente. La documentación de [cabeceras de Vercel](https://vercel.com/docs/headers/request-headers)
describe la identidad aportada por el proxy y las diferencias con `X-Forwarded-For`.

Programar diariamente, en un proceso con acceso a la misma base y al almacenamiento:

```text
uv run python manage.py clear_rate_limits
uv run python manage.py retry_file_deletions
```

El segundo comando termina con error si persisten archivos pendientes, para permitir
alertas del programador. La aplicación intenta eliminarlos inmediatamente después
del commit; las tareas sobreviven a fallos de R2 o a la terminación de una instancia.
No hay purgado automático de la papelera ni un plazo de retención implícito.

## Verificación y alcance

Validación local: 209 pruebas de Django y 9 pruebas de navegador aprobadas;
Ruff, formato, comprobación de Django y ausencia de migraciones pendientes de generar
también aprobados. Migraciones aplicadas en PostgreSQL local, sin ejecutar cambios
en Supabase ni R2 de producción.
Empaquetado de Workers verificado con `wrangler deploy --dry-run` y la versión
4.137.0 fijada en `package-lock.json`, sin desplegar.

Pruebas de regresión: bloqueo concurrente de contadores, ventanas y expiración,
login por IP/cuenta, CSRF, IP falsificada, almacenamiento obligatorio, propiedad de
edición, papelera/restauración/purgado, fallos de almacenamiento, conservación de roles,
columnas duplicadas/renombradas y reconstrucción de textos extensos de Excel.
El navegador cubre la papelera móvil, restauración y purgado por administrador.

Los límites de aplicación complementan los controles de red; no son protección completa
contra ataques distribuidos. Siguen pendientes las cargas directas a R2, el análisis
antimalware y la reconciliación general de objetos descritos en la auditoría inicial.
La identificación de columnas aún recorre respuestas; su optimización para grandes
volúmenes sigue pendiente. Este cambio no repara datos históricos ya redondeados.
