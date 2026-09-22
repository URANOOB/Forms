# Mover componentes en el editor

Cada pregunta o bloque muestra un control de puntos en su parte superior. Se puede
arrastrar con ratón, lápiz o pantalla táctil, tanto dentro de una sección como entre
secciones. La línea de inserción marca el destino. Al acercarse a los bordes, el
contenedor se desplaza automáticamente. Escape, cancelar el gesto o soltar fuera
de una sección conserva el orden original.

Pulsar el control de arrastre o «Mover a otra sección» en el menú de tres puntos
abre un diálogo con
la sección de destino y la posición (antes de otro componente o al final). Esta
alternativa también permite mover con teclado y colocar componentes en secciones
vacías.

Ambas interfaces emiten `builder:move-field` con `fieldId`, `sectionId` y
`beforeId` (o `null` para el final). El editor mueve el objeto existente y conserva
ID, clave estable, opciones, configuración, imágenes y referencias de condiciones.
La operación actualiza numeración e índice, participa en Deshacer/Rehacer y se
persiste mediante Guardar, utilizando el guardado de secciones existente.

Se rechazan movimientos que produzcan ciclos en las dependencias de condiciones
o dejen vacía una sección utilizada como destino condicional. No se eliminan reglas
automáticamente. Los controles se deshabilitan al guardar o en formularios
archivados.

Verificación realizada sin ejecutar tests: sintaxis de JavaScript, comprobaciones
de Django, compilación de la plantilla y revisión del diff.
