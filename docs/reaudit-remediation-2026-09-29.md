# Correcciones de la reauditoría del 29 de septiembre de 2026

La [reauditoría](auditoria-2026-09-29.md) describe tres reproducciones sobre
`fb9a2c3`. Se conserva como evidencia del estado anterior.

## Cambios

- **F1, identidad de borradores:** una bifurcación solicita al servidor un token
  firmado nuevo, con un nonce independiente. Primero guarda los datos localmente
  sin identidad de envío, para conservarlos incluso sin conexión o si falla la
  solicitud. Al recuperar o enviar un borrador pendiente se obtiene su identidad
  antes de comprobar recepciones anteriores. Los reintentos conservan el nonce.
  La emisión exige CSRF y un formulario que reciba respuestas.
- **F2, versiones históricas:** el presupuesto agregado se valida en borradores,
  al guardar y publicar. Leer y responder versiones publicadas no vuelve a aplicar
  esa regla de admisión. Los límites reales de parámetros, archivos y bytes de
  cada petición siguen vigentes, con errores recuperables.
- **F3, navegación condicional:** al guardar/publicar borradores se comprueba que
  el origen sea alcanzable y que exista un recorrido desde su sección hasta la
  sección de destino. Se incluyen los saltos configurados y la continuación al
  omitir secciones ocultas. El selector aplica el mismo recorrido; mantiene los
  destinos de preguntas dentro de la sección actual. Los ciclos siguen siendo
  rechazados. Las versiones históricas se conservan; corregir sus condiciones
  requiere guardar y publicar un nuevo borrador.

## Verificación

Las pruebas permanentes incluyen la pestaña original sin recargar, dos nonces
distintos, dos respuestas reales y la limpieza de ambos borradores; también una
bifurcación sin conexión que se recupera tras recargar. En el servidor se prueba
un formulario histórico de 205 archivos de capacidad, su apertura, envíos pequeños
y el rechazo de peticiones que superan el límite real. Las condiciones se comprueban
al guardar, al publicar, con navegación que termina antes del destino y en el
selector del navegador.

Las pruebas se ejecutan sobre PostgreSQL local y Chromium con bases desechables,
archivos locales o simulados y notificaciones desactivadas. No se consulta producción.

Resultado local: 298 pruebas generales y 22 pruebas de navegador correctas,
sin omitir las que usan Node; importación de catálogos en Chromium correcta.
Ruff, formato, sintaxis de los 29 archivos JavaScript propios, comprobación
de Django, ausencia de migraciones pendientes y `git diff --check` correctos.

## Pendientes operativos

Esta corrección no mide ni resuelve los riesgos de escala del bloqueo durante
duplicados/cargas y del descubrimiento de columnas en reportes. La infraestructura
debe programar los comandos de limpieza y reintento existentes. No se ha comprobado
un programador externo, entrega real de correo, fallos de R2, restauración de copias
ni capacidad de producción.
