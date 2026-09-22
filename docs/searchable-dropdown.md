# Desplegable con búsqueda

Seleccione **Desplegable con búsqueda** en el tipo de pregunta del editor y añada
las opciones habituales. Al pasar desde otro desplegable se conservan sus opciones
y condiciones. El buscador filtra las etiquetas por coincidencia parcial, sin
distinguir mayúsculas o tildes. Puede utilizar códigos incluidos en esas etiquetas.

La pregunta se guarda como `SINGLE_CHOICE`, con `configuration.widget = "select"`
y `configuration.searchable = true`. No requiere migración y conserva el mismo
valor de respuesta y la validación de opciones existente. La consulta de búsqueda
no se envía ni se guarda como respuesta.

El formulario, su vista previa y la edición de respuestas utilizan el selector
compartido. Permite navegar con flechas, confirmar con Enter y cerrar con Escape;
muestra un mensaje cuando no hay coincidencias. Al reabrir se limpia la búsqueda
y se conserva la opción seleccionada. En navegadores sin soporte de Popover, o
sin JavaScript, se mantiene el desplegable nativo.

Comprobaciones de sintaxis, Django y compilación de plantillas; sin ejecutar tests.
