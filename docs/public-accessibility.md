# Accesibilidad de los formularios públicos

Esta implementación sigue las pautas de [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
con objetivo de nivel AA. No constituye una certificación de conformidad.
En esta sesión se revisó el código y su sintaxis, sin ejecutar pruebas funcionales,
automatizadas, de navegador ni con tecnologías de asistencia, por indicación del usuario.

## Alcance

Presentación del formulario, preguntas, validación, confirmación de envío y formulario
cerrado. La vista previa muestra la misma experiencia que verá el participante.
El panel administrativo, el constructor y la edición interna de respuestas no cargan
el menú ni los estilos nuevos. No hay cambios en los datos de los formularios, sus
reglas condicionales, la persistencia de respuestas ni los permisos.

## Implementación

| Área | Comportamiento |
| --- | --- |
| Idioma y estructura | `lang="es"`, título del documento, región principal, salto al formulario, encabezados, labels, fieldsets y legends. |
| Teclado y foco | Navegación disponible por defecto, foco contrastado, enlaces de errores que abren la sección correcta; el diálogo usa modalidad nativa, Escape y retorno al botón de apertura. |
| Errores | Resumen enfocable con enlaces y errores persistentes junto al campo, `aria-invalid` y `aria-describedby`, incluidas escalas, cuadrículas y detalles adicionales. Los errores del servidor siguen siendo autoritativos. |
| Instrucciones | Asociación de ayudas, requisitos de adjuntos y mensajes con los controles; indicación de obligatoriedad y de formato numérico. No se eliminan silenciosamente caracteres incorrectos al escribir. |
| Contraste | Superficies opacas, textos oscuros y bordes de controles visibles. El acento público se oscurece cuando hace falta para mantener margen sobre 4,5:1 en superficies claras; el tema guardado no se modifica. |
| Ampliación y reflujo | Tipografía en rem, tamaños mínimos legibles, panel desplazable y disposición móvil sin alturas fijas para texto. Las tablas bidimensionales conservan desplazamiento horizontal local y accesible por teclado. |
| Tamaños de interacción | Radios y casillas de 24 px, etiquetas amplias, botones generalmente de 44 px o más; calendario con mínimos de 24 px. |
| Estado y movimiento | Anuncios de progreso y condiciones; respeto por `prefers-reduced-motion` y preferencia local. La animación de confirmación se detiene cuando se solicita reducir movimiento. |
| Archivos | Carga por selección además de arrastre, confirmación y eliminación por teclado, nombres accesibles que incluyen el texto visible. En la vista pública el PDF se abre mediante enlace explícito, sin un visor incrustado que pueda retener el foco. |

El menú ofrece texto normal/grande/extra grande, contraste alto, mayor espaciado,
foco reforzado, movimiento reducido y lectura de la sección visible. La navegación
por teclado es permanente; no hay un interruptor que pueda desactivarla.

Las preferencias se guardan bajo `logicforms-public-accessibility-v1` en localStorage.
Si el almacenamiento está bloqueado, los controles funcionan durante la visita.
No se almacenan respuestas ni datos personales en estas preferencias.

La lectura usa `speechSynthesis` únicamente al pulsar Reproducir, en español,
prefiriendo una voz local cuando está disponible. Se leen encabezados, preguntas e
instrucciones, nunca valores introducidos, archivos ni selecciones. El navegador
determina la disponibilidad y el procesamiento de sus voces. Puede detenerse desde
el menú o la barra; también se detiene al cambiar de sección o abandonar la página.
Si el navegador no admite la función, se indica en el menú. No sustituye al lector
de pantalla del participante.

## Verificación pendiente

Antes de afirmar conformidad AA, revisar el recorrido completo de formularios reales:

- Teclado: bienvenida, selectores con y sin búsqueda, fechas, radios, escalas,
  cuadrículas, archivos, preguntas condicionales, errores y envío.
- Zoom al 200 % y 400 %, viewport de 320 CSS px, texto largo y ajustes de espaciado;
  verificar que no se pierda contenido, controles o foco.
- NVDA con Firefox/Chrome, VoiceOver con Safari y TalkBack con Chrome; comprobar
  nombres, estados, mensajes de error y anuncios de cambios.
- Contraste de todas las variantes, modo de contraste forzado del sistema y
  colores personalizados del formulario; foco no oculto por popovers o diálogo.
- Movimiento reducido, lectura en voz alta, ausencia de destellos, recuperación
  tras errores del servidor, navegación hacia atrás y funcionamiento sin JavaScript.
- Contenido creado por autores: las imágenes informativas deben tener un equivalente
  textual suficiente en la pregunta o ayuda. El encabezado y los fondos se consideran
  decorativos; no deben ser el único lugar donde aparezcan instrucciones importantes.
  Los campos de datos personales de propósito ambiguo requieren revisar su semántica
  de autocompletado; correo y teléfono ya la declaran explícitamente.

Los textos e imágenes cargados por los autores y la compatibilidad efectiva con
lectores de pantalla forman parte de esta revisión; un menú de preferencias por sí
solo no demuestra conformidad con WCAG.
