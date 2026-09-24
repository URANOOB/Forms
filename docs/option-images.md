# Imágenes de las opciones de respuesta

En el editor, cada opción de una pregunta de selección tiene su propio botón de
imagen. Permite subir PNG, JPG o WebP de hasta 5 MB, muestra una miniatura y ofrece
acciones para cambiarla o quitarla. El título de la pregunta ya no tiene botón de
imagen; los bloques de imagen siguen disponibles.

La relación opcional `FieldOption.image` guarda el recurso `FormImage`, validando
que pertenece al mismo formulario. La migración `0010_fieldoption_image` incorpora
esta relación sin modificar opciones existentes. Las imágenes se conservan al
guardar, publicar, duplicar o mover preguntas.

Las opciones y casillas muestran las imágenes junto a sus etiquetas. El selector
desplegable personalizado incluye miniaturas y muestra la imagen de la selección
actual debajo del control. Los valores enviados y las condiciones no cambian.
El endpoint de imágenes permite al público únicamente recursos de opciones
activas que pertenezcan a la versión pública vigente. Los borradores mantienen
los permisos existentes del editor.

Verificación realizada sin ejecutar tests: comprobaciones de Django, migración
aplicada, sintaxis JavaScript y compilación de las plantillas.
