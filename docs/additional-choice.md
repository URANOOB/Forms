# Desplegable con opción adicional

En el constructor, el tipo **Desplegable con opción adicional** permite solicitar un
campo adicional después de seleccionar una respuesta. **Campo adicional** aparece
debajo de las opciones de la pregunta, abierto por defecto. Su cabecera permite
plegar y volver a abrir la configuración sin entrar al menú de tres puntos. Si se
abre **Mostrar según respuesta**, las condiciones quedan encima de este bloque.
El ajuste **Mostrar campo adicional**
lista las opciones activas de la pregunta por su nombre y permite elegir:

- **Al elegir cualquier opción** (valor inicial de la nueva variante).
- Cualquiera de las opciones registradas, por ejemplo **Opción 1**, **2** u **Otro**.

No se ofrece Otro si no está registrado. Los nombres del selector se actualizan al
editar las opciones. La selección específica se guarda por su valor estable, de
modo que cambiar el nombre no cambia la opción que solicita el texto.

Los desplegables normales que contengan una opción llamada Otro también muestran el
texto automáticamente. El placeholder inicial es **Por favor escriba cual**. Cuando aparece,
el campo es obligatorio y admite hasta 500 caracteres. No se añade automáticamente
una opción a la lista: el autor escribe sus opciones como hasta ahora.

En la variante con opción adicional, **Placeholder del campo adicional** permite
personalizar la indicación (hasta 200 caracteres), con una vista previa inmediata.
Si se deja vacío, se usa la indicación inicial. **Tipo de campo adicional** permite
elegir **Texto**, **Numérico** o **Correo electrónico**. Numérico solicita el teclado
numérico y admite solo dígitos del 0 al 9, sin flechas, signos ni decimales;
Correo electrónico solicita el teclado de correo
y valida su formato. La validación se aplica en el navegador y en el servidor.

La variante usa `SINGLE_CHOICE` con `configuration.widget = "select"` y
`configuration.additional_text` (`other`, `any` u `option`). El modo `option` guarda
el valor estable de la opción en `configuration.additional_text_option`.
El tipo se guarda en `configuration.additional_text_type` (`text`, `number` o `email`)
y la indicación en `configuration.additional_text_placeholder`. Las configuraciones
existentes conservan el tipo texto y el placeholder inicial. No requiere migraciones.

Las condiciones siguen comparando únicamente el valor seleccionado. Cuando se pide
texto, la respuesta se guarda como `{"selected": "valor", "text": "detalle"}`;
las demás selecciones conservan el formato de texto existente. La consulta, búsqueda
y edición de respuestas incluyen el detalle. Los textos enviados para una selección
que no los requiere, o para una pregunta fuera del recorrido, se ignoran en el servidor.

Sin JavaScript, el campo adicional se muestra acompañado de su indicación; la
validación del servidor determina si corresponde exigirlo.
