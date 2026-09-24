# Campos de teléfono

El constructor ofrece **Número de teléfono** separado de **Numérico**. Usa un
campo `tel`, teclado numérico, autocompletado y validación de formato. El valor
se conserva como texto, incluidos ceros iniciales. Solo admite dígitos del 0 al 9,
con una longitud de 6 a 25 dígitos. No admite letras, espacios, signos ni guiones.
El navegador filtra lo escrito y pegado; el servidor también exige solo dígitos.

La vista pública incorpora un icono de teléfono y un placeholder predeterminado,
respetando cualquier placeholder personalizado.

El tipo se determina por la configuración elegida, sin inferirlo del título.
Los campos `NUMBER` se presentan como **Numérico**, con icono propio, sin flechas,
teclado numérico y solo dígitos. Conservan sus límites y almacenamiento numérico;
se rechazan signos, decimales y notación exponencial antes de convertir el valor.
Para conservar ceros iniciales en teléfonos debe elegirse **Número de teléfono**
desde el constructor. No se modifican versiones publicadas ni respuestas anteriores.
