# Crear campos desde archivo

En el constructor, **Crear campos desde archivo** está en el menú de tipos de pregunta, debajo de **Desplegable con opción
adicional**. Abre un asistente para generar entre 1 y 20 campos por importación,
independientes o relacionados. La importación se analiza en el servidor y
no guarda el archivo ni modifica el formulario hasta pulsar **Añadir N campos**.
Los campos se incorporan a la sección seleccionada y participan en Deshacer/Rehacer.
Después se usa el guardado habitual del constructor.

1. Seleccionar un `.csv`, `.xlsx` o `.xlsm`. Se admite hasta 5 MB, 20 hojas, 50 columnas y 5.000 filas
   de datos en la hoja elegida. Los encabezados deben estar entre las filas 1 y 50.
   El CSV admite separadores de coma, punto y coma o tabulación y codificación UTF-8,
   UTF-16 con BOM o Windows-1252. Sus valores se conservan como texto.
   **Cambiar archivo** permite reemplazarlo incluso durante el análisis o volver a
   seleccionar el mismo archivo. Cancelar el selector conserva la selección actual.
2. Revisar la hoja, encabezados y muestra. Se sugieren código, descripción y
   agrupador a partir de sus nombres, valores únicos y repeticiones.
3. Usar **Añadir campo** o **Quitar campo** para elegir cuántos componentes crear.
   Se puede quitar incluso el último campo o usar **Empezar desde cero** para vaciar
   toda la configuración conservando el archivo, la hoja y las columnas. Mientras
   no haya campos, no se puede actualizar ni añadir la propuesta al formulario.
   Cada tarjeta configura nombre, columna del valor guardado, una o varias columnas
   del texto visible (en orden), obligatoriedad y desplegable normal o con búsqueda.
   **Filtrar opciones según** permite elegir un campo anterior o **Sin dependencia**.
   Al quitar un campo, sus hijos directos quedan sin dependencia y se muestra un aviso.
   **Actualizar propuesta** valida los cambios antes de permitir la incorporación.
4. Probar los campos y buscar opciones. Se muestra el valor
   que se guardará. Solo se usan las columnas elegidas; el resto no genera reglas.

Los códigos se conservan como texto, incluyendo ceros iniciales y formatos de
relleno de ceros de Excel. La etiqueta combina las columnas elegidas con « — ». Un mismo
código puede aparecer en varios grupos si conserva la misma descripción. Las
filas idénticas se deduplican con aviso. Vacíos, descripciones contradictorias,
fórmulas, errores y longitudes no admitidas bloquean la propuesta y señalan las
filas que requieren revisión. Solo se validan las columnas seleccionadas. No se ejecutan
fórmulas ni macros. Una columna permite una lista sencilla; código y descripción
pueden formar un único campo. Código y grupo pueden formar dos desplegables relacionados.
También se permiten campos independientes, cadenas y varios campos hijos de un mismo padre.

La sugerencia del archivo CIE10 produce un campo con 25 agrupadores y otro con 556 códigos. CAC Cérvix
contiene 8 opciones y CAC Colorectal 20. No se generan restricciones de edad,
género ni reglas clínicas a partir de las otras columnas.

## Relación y almacenamiento

Se reutilizan `SINGLE_CHOICE`, `widget: select` y `searchable`. Las opciones quedan
en `FieldOption`, con hasta 5.000 opciones por campo. El campo hijo guarda en
`configuration.option_filter` una referencia al `stable_key` del padre y un mapa
de opciones a valores del campo padre. Se admiten varios grupos por opción.
Los valores se toman de la columna seleccionada. Si un campo intermedio repite el
mismo valor bajo diferentes padres, se crean opciones con identificadores internos
distintos y se avisa en la propuesta. Esto evita que una ciudad homónima en dos países
muestre barrios del país equivocado. Los identificadores se muestran en la vista previa.
No se necesitan migraciones.

La referencia estable se conserva cuando el guardado regenera identificadores
de base de datos. Los catálogos publicados pertenecen a su versión y no cambian
al editar una versión posterior. Las escrituras de opciones se agrupan dentro de
la transacción del constructor, después de validar sus invariantes. El límite de
petición JSON es de 8 MB.

El motor valida que el origen exista, sea selección simple, preceda al hijo y que
todas las opciones activas tengan relaciones válidas. Las dependencias participan
en la detección de ciclos junto a las condiciones habituales. Un código inválido
para el grupo no puede activar condiciones posteriores.

En el formulario público y la edición de respuestas, el hijo empieza deshabilitado
hasta que se responde el padre. Cambiar de grupo limpia un código incompatible.
La búsqueda solo contempla opciones del grupo elegido. El servidor también
rechaza combinaciones incompatibles, incluso sin JavaScript o con un POST manipulado.
Sin JavaScript las listas se muestran completas; la relación se valida al enviar.

Las relaciones y opciones importadas se consultan en el constructor como un catálogo;
para cambiarlas se eliminan los campos desde los hijos hacia los padres y se importa de nuevo.
Se pueden editar
los títulos, descripciones, obligatoriedad y tipo de desplegable. La interfaz
impide borrar un agrupador mientras otro campo lo utiliza.

## Verificación

`uv run python manage.py test apps.forms.tests.test_catalog_import --noinput`
cubre análisis, mapeo, códigos, duplicados, límites, permisos, CSRF, guardado,
integridad de relaciones, validación de respuestas y conservación de versiones. Incluye
listas de una columna, dos columnas, combinación ordenada de etiquetas, campos independientes,
cadenas de cuatro niveles, ramificaciones y valores intermedios repetidos en distintos padres.
Incluye CSV con coma, punto y coma o tabulación, textos entrecomillados, varias
codificaciones, XLSM y recuperación del endpoint tras un archivo inválido.
`uv run --with playwright python apps/forms/tests/browser_catalog_import.py`
comprueba en Edge el selector con el listener de Unfold: reemplazo, reselección del
mismo archivo, cancelación, errores, cambio durante el análisis y reapertura del diálogo.
También se comprobó el Excel de 556 filas en navegador: vista previa, móvil,
añadir/quitar campos, deshacer/rehacer, guardar/recargar y filtrado con búsqueda del formulario
público en una cadena de tres campos: Cáncer CAC → Agrupador → Código CIE10.
