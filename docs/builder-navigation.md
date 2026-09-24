# Orientación en el editor

La barra principal y sus pestañas permanecen visibles al desplazarse; Guardar y
su estado se muestran únicamente en esa barra. La pestaña Preguntas incorpora
una barra flotante compacta a la izquierda, con iconos para abrir el índice e ir
al elemento anterior o siguiente. El contexto de edición aparece dentro del
índice. La barra respeta el espacio del menú lateral y la cabecera principal;
el índice se ajusta al espacio visible, también en móvil. El índice permite
buscar por título, número, sección o tipo de pregunta, sin distinguir tildes ni
mayúsculas. También permite volver a la bienvenida y navegar a secciones vacías.

Las preguntas muestran una numeración continua y su tipo de campo. Los bloques
informativos no incrementan la numeración. La pregunta activa tiene una etiqueta
«Editando pregunta». El índice identifica el elemento activo con `aria-current`;
se puede recorrer con Tab y cerrar con Escape.

La interfaz de navegación recibe eventos `builder:navigation-update` y solicita
los desplazamientos mediante `builder:navigate`. No modifica el contenido del
formulario ni se incluye en el historial. Al guardar se conserva el elemento
activo por su posición en la sección, ya que el servidor puede renovar sus IDs.

Verificación sin ejecutar tests: sintaxis JavaScript, compilación de la plantilla
del editor y comprobaciones de Django.
