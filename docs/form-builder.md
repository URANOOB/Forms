# Constructor visual

Abrir una tarjeta de **Formularios** lleva al constructor cuando el usuario tiene
permiso de edición. Crear un formulario en blanco o con plantilla abre directamente
el constructor, sin pasar por el alta administrativa de nombre/slug/metadata. El espacio
del usuario se selecciona automáticamente; cuando hay varios espacios disponibles para
un superusuario, puede elegir uno dentro del editor. El slug se genera automáticamente.
El registro se crea mediante POST al guardar, previsualizar, publicar o subir la primera
imagen. Abrir/cerrar el editor nuevo sin estas acciones no crea registros.
Los usuarios de sólo lectura conservan el detalle administrativo.

## Uso

- Editar título y descripción directamente en la tarjeta superior.
- La barra lateral añade preguntas, bloques de texto, imágenes y secciones.
- Cada pregunta permite cambiar tipo, añadir/quitar opciones, duplicar, subir/bajar,
  mover a otra sección, adjuntar una imagen y marcar como obligatoria.
- Selección única admite botones de opción o lista desplegable. Selección múltiple
  usa casillas. También hay texto corto/largo, correo, teléfono, número, fecha y Sí/No.
- **Mostrar según respuesta**, en las preguntas de Sí/No o selección, permite elegir
  directamente «Si responde Sí → mostrar pregunta X» o «Si selecciona una opción →
  mostrar sección Y». Cada respuesta puede mostrar varias preguntas, imágenes o secciones.
  El contenido permanece oculto hasta seleccionar esa respuesta y se oculta al cambiarla.
  La pregunta que aparece también puede tener opciones que muestren otros componentes.
  Si una pregunta está dentro de una sección condicional, deben cumplirse tanto la
  condición de la sección como la de esa pregunta para mostrarla.
- **Condiciones avanzadas** configura pregunta de origen, comparación y respuesta esperada.
  Puede mostrar/ocultar preguntas o secciones, o cambiar la obligatoriedad de preguntas.
  Un grupo combina todas o alguna de sus condiciones. Varias reglas permiten cadenas:
  participar = Sí → mostrar taller; taller = Fotografía → mostrar sección de contacto.
- **Guardar borrador** persiste los cambios. No hay autoguardado; salir con cambios
  pendientes muestra el aviso del navegador. **Vista previa** guarda primero y abre
  el mismo formulario con sus condiciones, pero sin permitir enviar respuestas.
- **Publicar** guarda y activa esa versión. **Respuestas** lleva a los envíos privados.
  El enlace para participantes se muestra después de publicar.

Las secciones condicionales se muestran en la misma página. Esta implementación no
incluye navegación «ir a la sección» ni saltos entre páginas. El orden se cambia con
flechas; no incluye arrastrar y soltar.

## Versionado y validación

GET no crea versiones ni modifica datos. Guardar una versión publicada genera una
nueva versión en borrador, copia el contenido enviado por el editor y remapea las
relaciones entre preguntas/secciones/reglas. Conserva stable_key y valores de opciones.
Título y descripción también quedan guardados en cada versión. Las respuestas mantienen
sus referencias a los campos de la versión que se respondió.

Guardado y publicación son transacciones con bloqueo de formulario y versión. Un hash
del contenido detecta cambios realizados desde otra pestaña o desde el admin técnico
y devuelve 409 sin sobrescribirlos. El editor conserva los cambios locales si falla.
Las condiciones inválidas, destinos ajenos, claves duplicadas y ciclos revierten todo
el guardado. El runtime usa el mismo FormSchema en publicación, vista previa y envío.

Los endpoints del constructor están bajo el admin, requieren sesión de personal,
permiso `forms.change_form`, workspace autorizado y CSRF en POST. Límites por formulario:
50 secciones, 200 preguntas/bloques, 100 opciones por pregunta, 300 reglas y 1 MB de JSON.

## Imágenes

Imágenes de presentación en PNG/JPEG/WebP: hasta 5 MB y 20 megapíxeles. Pillow decodifica,
ajusta orientación y tamaño (máximo 2400 px), elimina metadatos y vuelve a codificar PNG.
No se aceptan SVG, URLs remotas ni documentos. Los bytes van a Django Storage, no a JSON
ni a PostgreSQL. La base guarda la referencia FormImage del mismo formulario.

En desarrollo, `MEDIA_ROOT` apunta a `media/`, excluido de Git. La aplicación sirve las
imágenes mediante una vista autorizada; no publicar esa carpeta directamente en el
servidor web. Los editores del workspace pueden verlas en borrador. Anónimos sólo pueden
ver imágenes referenciadas por la versión activa de un formulario publicado y workspace
activo. Al pausar o archivar, dejan de estar disponibles para anónimos.

Quitar una imagen de una pregunta elimina la referencia del borrador; no borra el archivo
ni las referencias de versiones anteriores. Limpieza de imágenes huérfanas y proveedor
de almacenamiento de producción quedan pendientes. En despliegue se necesita almacenamiento
persistente compatible con Django Storage. Los adjuntos de participantes se guardan
por separado en `private_uploads/`, con descarga autorizada; R2 continúa pendiente.

## Tipos de preguntas

El selector incluye Respuesta corta, Párrafo, Varias opciones, Casillas, Desplegable,
Subir archivos, Escala lineal, Calificación, ambas cuadrículas, Fecha y Hora.
También conserva correo, teléfono, número, Sí/No y los bloques de contenido.

- Varias opciones y Desplegable comparten el modelo de selección única y conservan
  sus opciones y condiciones al cambiar de presentación.
- Escala lineal: inicio 0 o 1, final entre 2 y 10 y etiquetas opcionales.
- Calificación: entre 2 y 10 estrellas, corazones o pulgares.
- Cuadrículas: hasta 20 filas y 10 columnas; una o varias selecciones por fila.
- Archivos: de 1 a 5 adjuntos, máximo configurable hasta 10 MB por archivo; PDF,
  JPG/JPEG, PNG, WebP, DOCX, XLSX, TXT y CSV. Se validan extensión, tamaño y las
  firmas básicas de los formatos binarios; no hay un servicio antivirus integrado.
  Los archivos se descargan desde Respuestas, con permisos de personal.

Los archivos y cuadrículas admiten condiciones de vacío/no vacío como origen.
Las escalas y calificaciones admiten comparaciones numéricas.
