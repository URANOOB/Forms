# Editor compacto de condiciones

«Mostrar según respuesta» presenta únicamente las reglas configuradas y los borradores que se añadan con **＋ Añadir regla**. Un campo sin reglas empieza con una fila vacía; ya no se dibuja una fila por cada respuesta posible.

- **Si selecciona:** cualquier opción o una respuesta concreta de la pregunta actual.
- **Entonces mostrar:** selector de destino con búsqueda por nombre, número o sección. La búsqueda ignora tildes y mayúsculas. También permite seleccionar una sección completa, excepto la que contiene la pregunta de origen.
- Los resultados incluyen número, nombre, sección y tipo. Cambiar la búsqueda no modifica una regla hasta elegir un destino.
- Las reglas idénticas se rechazan con un mensaje junto a la fila.
- Los borradores sin destino solo existen en la interfaz; no se guardan como condiciones incompletas. Las reglas completas participan en Guardar, Deshacer y Rehacer.
- Escape cierra el selector de destino y devuelve el foco a su cabecera. Enter desde la búsqueda lleva el foco al primer resultado; Tab recorre los controles y resultados.

La opción «Cualquier opción» se guarda con `operator: IS_NOT_EMPTY` y `expected: null`, ya admitidos por el motor público y por la validación del servidor. Una respuesta concreta conserva `EQUALS` (selección simple y Sí/No) o `CONTAINS` (casillas). «No» cuenta como una respuesta; una lista vacía no.

Las condiciones avanzadas agrupadas con otras condiciones no se modifican desde este editor. Se preservan las reglas existentes y sus destinos. Las reglas simples de mostrar que comparten un destino funcionan como alternativas, según el comportamiento existente del motor.

El cambio no requiere migraciones.
