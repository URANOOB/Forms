# Reauditoría del 29 de septiembre de 2026

Revisión de `main`, commit `fb9a2c322b0927c82cda7e9126038ee81391609f`, después de integrar las correcciones de septiembre. Se contrastó el código con la auditoría del día 28 y con el documento de remediación. La revisión combina inspección, PostgreSQL local y Chromium; no modifica el código funcional ni consulta producción.

**Resultado: siete de los nueve hallazgos anteriores quedan cerrados en los escenarios comprobados y dos quedan parcialmente resueltos. Se reproducen tres problemas actuales: pérdida de una respuesta entre pestañas, incompatibilidad de formularios antiguos con el nuevo presupuesto y condiciones que dejan secciones inalcanzables.**

Las 294 pruebas generales y las 18 pruebas de navegador existentes pasan. Las tres reproducciones adicionales fallan al exigir el comportamiento correcto. Por tanto, que la suite existente esté verde no permite dar por terminada la remediación.

## Comprobación de los hallazgos anteriores

| Hallazgo del 28 de septiembre | Estado | Evidencia de esta ejecución |
| --- | --- | --- |
| 1. Rechazos por cantidad de parámetros/archivos | **Parcial** | Pasa el envío real con seis cuadrículas completas y 105 archivos; pasan los límites del parser y su error recuperable. El presupuesto nuevo también se aplica al leer versiones antiguas y puede romper sus enlaces: F2. |
| 2. Ajustes que no activaban cambios pendientes | **Corregido** | Chromium verifica notificaciones, identificación de respuestas y duplicados: cambios pendientes, deshacer, rehacer y guardado al abrir vista previa. |
| 3. Exportación de cuadrículas como identificadores | **Corregido** | CSV, Excel y detalle conservan las etiquetas históricas incluso después de cambiar las etiquetas del borrador. La conversión compartida también la utilizan los reportes. |
| 4. Duplicados históricos con números float | **Corregido** | Una respuesta histórica con `12345.0` coincide con una nueva con `12345`. Los valores no finitos, fraccionarios y booleanos no se convierten en identidades válidas. |
| 5. Borradores que se sobrescribían/borraban entre pestañas | **Parcial** | La separación de almacenamiento y el descarte pasan las pruebas existentes. Una bifurcación de la pestaña original reutiliza el identificador de envío y pierde una respuesta: F1. |
| 6. Validaciones sin ningún valor admisible | **Corregido** | Se rechazan intervalos numéricos sin enteros válidos y longitudes incompatibles con teléfono/correo. Se admite un intervalo que sí contiene un entero válido. |
| 7. Limpieza de archivos sin reintento durable | **Corregido** | Fallos simulados al borrar y rollbacks dejan tareas de limpieza; se intenta cada archivo y se conserva el adjunto original si fracasa la edición. Los reintentos eliminan las tareas completadas. |
| 8. Pérdida del último administrador | **Corregido** | Se bloquean degradación, desactivación y eliminación individual/masiva del último administrador. Dos degradaciones concurrentes dejan uno activo. |
| 9. Archivado sin regreso desde el panel | **Corregido** | La acción de desarchivar devuelve el formulario a borrador, conserva la versión y mantiene cerrado el enlace público hasta publicar. |

Pruebas principales: [regresiones del servidor](G:/Develop/Forms/apps/submissions/tests/test_september_audit.py), [regresiones del navegador](G:/Develop/Forms/apps/submissions/tests/browser_september_audit.py) y [protección administrativa](G:/Develop/Forms/apps/accounts/tests/test_admin_safety.py).

## F1 — [P1] Dos borradores distintos pueden confirmar el mismo envío y perder una respuesta

**Ubicación:** [public-draft.js:94](G:/Develop/Forms/static/forms/public-draft.js:94), especialmente la asignación `forkToken = initialToken` en la línea 98. La recuperación identifica el envío por su nonce en [runtime.py:61](G:/Develop/Forms/apps/submissions/runtime.py:61).

**Reproducción ejecutada con Chromium y PostgreSQL:**

1. Abrir la pestaña A y escribir una respuesta para crear su borrador.
2. Abrir B después y pulsar «Continuar borrador» para recuperar el de A.
3. Modificar la respuesta en B y esperar a que se guarde.
4. Sin recargar A, modificar también su respuesta. Se anuncia que se guarda por separado.
5. Enviar desde A y luego desde B.

Antes del envío existen dos entradas con respuestas diferentes, pero al decodificar sus tokens ambas tienen **el mismo nonce**. A sigue conservando como `initialToken` la identidad que dio origen al borrador compartido; reutilizarlo no crea una identidad nueva.

**Resultado observado:** dos páginas de confirmación, **una sola respuesta en la base** y **cero borradores restantes**. Se guarda «Respuesta A»; «Respuesta B» desaparece. La recuperación de B encuentra el envío de A y lo considera suyo, sin guardar las respuestas de B.

```text
fork_before_send: answers=['Respuesta A', 'Respuesta B'], unique_nonces=1
fork_after_send: confirmations=2, submissions=1, drafts_remaining=0
```

La prueba existente recarga la pestaña antes del caso de recuperación compartida, lo que le proporciona otro token inicial. Además, compara los tokens completos; dos firmas con distinta fecha pueden contener el mismo nonce. No cubre la pestaña original que sigue abierta.

**Corrección recomendada:** cada bifurcación debe obtener una identidad de envío nueva, firmada, independiente de la del borrador original. Los reintentos del mismo borrador deben conservar su identidad. Añadir la secuencia anterior y comprobar dos registros reales en la base, además de los nonces y las entradas de almacenamiento.

## F2 — [P2] El presupuesto nuevo rompe la apertura de versiones ya publicadas

**Ubicación:** [conditions.py:54](G:/Develop/Forms/apps/forms/conditions.py:54), [request_budget.py:28](G:/Develop/Forms/apps/forms/request_budget.py:28) y [views.py:61](G:/Develop/Forms/apps/submissions/views.py:61).

`FormSchema` ejecuta incondicionalmente la nueva validación del presupuesto, tanto al guardar/publicar como al abrir un formulario público. La vista pública no captura esta excepción. No hay una transición para esquemas publicados antes de introducir esos límites agregados.

**Reproducción ejecutada:** construir una versión con 41 preguntas opcionales de adjuntos, cada una con capacidad para cinco archivos. Simular su publicación anterior permitiendo temporalmente una capacidad agregada mayor; restaurar el límite actual de 200 y abrir su enlace. Son 205 archivos de capacidad, no archivos enviados: la petición es un simple GET.

```text
historical_published_form: GET status=500
ValidationError: El formulario admite como máximo 200 archivos en total...
```

El esquema era admitido antes de la corrección; ahora la persona ni siquiera puede abrirlo para responder sin archivos o con pocos adjuntos. El problema depende de que existan esquemas antiguos con esa capacidad; **no se consultó producción para determinar cuántos existen**.

**Corrección recomendada:** separar la admisión de nuevos esquemas de la lectura de versiones publicadas. Mantener los límites reales de las peticiones y sus mensajes recuperables. Si se exige adaptar versiones antiguas, detectar y resolver esos casos de forma controlada antes de activar el requisito; no convertir su lectura en un error 500. Añadir pruebas de compatibilidad con versiones publicadas bajo los límites anteriores.

## F3 — [P2] Se puede publicar una condición que nunca permite acceder a su sección

**Ubicación:** [conditions.py:239](G:/Develop/Forms/apps/forms/conditions.py:239) y [builder.js:178](G:/Develop/Forms/static/forms/builder.js:178).

El selector de destinos ofrece secciones anteriores a la pregunta origen. El servidor comprueba ciclos, pero no que la navegación permita satisfacer esas dependencias. `journey()` recorre las secciones considerando únicamente la actual y las ya visitadas: al decidir sobre una sección anterior, el campo origen de una sección posterior se considera invisible.

**Reproducción ejecutada:** primera sección con «Nombre» obligatorio; segunda sección con «¿Te contactamos?». Configurar «mostrar la primera sección cuando la respuesta de la segunda sea Sí». El formulario se publica correctamente. Incluso evaluando una respuesta con «Sí», la primera sección queda fuera del recorrido y el formulario acepta omitir «Nombre».

```text
published=True
reachable=False
required_name_visible=False
missing_required_name_accepted=True
```

No hay un ciclo entre las preguntas que active la protección existente. La sección omitida tampoco se reconsidera después de contestar la segunda. El resultado es una condición admitida por el editor que no puede cumplirse en el recorrido público y produce respuestas incompletas respecto de lo configurado.

**Corrección recomendada:** validar las dependencias contra la navegación efectiva al guardar y publicar, y limitar el selector a destinos compatibles. Si se quiere admitir este tipo de condición, definir e implementar cómo se vuelve a la sección activada. Probar que todos los destinos ofrecidos pueden alcanzarse cuando se cumple su condición.

## Riesgos anteriores que siguen pendientes

- La detección de duplicados sigue recorriendo respuestas históricas en Python mientras se mantiene el bloqueo del formulario. Las cargas de archivos también prolongan esa transacción. Sigue pendiente medir concurrencia y reducir el trabajo realizado bajo el bloqueo.
- El descubrimiento de columnas de reportes sigue leyendo respuestas antes de paginar. No se han realizado pruebas de carga en esta auditoría.
- Existen comandos de reintento y limpieza, pero la configuración revisada no incluye su programación. La cola durable necesita que se ejecuten. No se inspeccionaron programadores externos.
- El documento de remediación afirma que los nueve hallazgos están corregidos. Esa afirmación debe matizarse con los dos estados parciales de esta revisión.

Las contradicciones anteriores del README y la arquitectura sobre columnas y despliegue sí fueron corregidas. `Workspace`, los enlaces antiguos y el empaquetado experimental de Workers siguen teniendo usos explícitos de compatibilidad o CI; no se identifican como código muerto que pueda eliminarse directamente.

## Verificaciones y alcance

| Comprobación ejecutada | Resultado |
| --- | --- |
| Suite general de Django sobre PostgreSQL local en Docker | 294 pruebas correctas |
| Suite explícita de navegador, incluida recuperación de borradores | 18 pruebas correctas, sin omitir la que necesita Node |
| Prueba adicional existente de importación de catálogos en Chromium | Correcta: reemplazo, reintento, cancelación, errores, solicitudes pendientes y reapertura |
| Tres sondas nuevas que exigen el resultado esperado | Tres fallos de aserción que reproducen F1, F2 y F3; sin errores del arnés en la ejecución final |
| Ruff y comprobación de formato | Correctos; 208 archivos Python con formato válido |
| Sintaxis de JavaScript propio en `static/forms` y `static/errors` | 29 archivos correctos |
| Comprobación de Django y migraciones pendientes | Sin incidencias; no hay cambios de modelos sin migración |
| `git diff --check` | Correcto |

Las pruebas utilizaron una base de pruebas creada y eliminada por Django, almacenamiento local o simulado y correo desactivado. Las sondas adicionales se conservaron fuera del código funcional: [script de reproducción](G:/CodexHome/visualizations/2026/09/29/01a0eb40-c806-7102-a5d9-2bbf4808ee4b/audit_probes.py). Sus aserciones fallan deliberadamente al exigir el comportamiento correcto; no se añadieron a la suite ordinaria.

No se verificaron entrega real de correo, fallos reales de R2, recuperación de copias, despliegue, capacidad de producción ni vulnerabilidades de dependencias contra fuentes externas actualizadas. El único archivo añadido al repositorio por esta revisión es este informe.

**Prioridad:** corregir primero F1 por pérdida silenciosa de datos; después cerrar la compatibilidad histórica de F2 y las condiciones inalcanzables de F3, incorporando las tres reproducciones a las pruebas permanentes.
