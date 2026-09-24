# Vista de formularios

La galería usa un contenedor centrado de hasta 1.400 px, con tarjetas de al menos
280 px y hasta cuatro columnas. La vista de lista conserva los mismos datos y
acciones. La preferencia de presentación se mantiene en el navegador.

Cuando solo hay un resultado, la vista de tarjetas usa una composición horizontal
de hasta 740 px, con una vista previa más legible. En móvil vuelve a apilarse.
El encabezado, el buscador y las acciones comparten alineación y espaciado.

La búsqueda se envía con **Enter**. **Filtros** reúne propietario (todos o creados
por mí), estado, fecha de actualización y orden. Los periodos de fecha incluyen
hoy, los últimos siete días y los últimos treinta días, según la zona horaria
configurada en la aplicación. El botón indica cuántos filtros están activos.
Limpiar los filtros conserva la búsqueda; el enlace del estado vacío restablece
la vista completa.

Cada tarjeta muestra una vista previa, estado, título, última actualización,
nombre del creador y total real de respuestas de todas sus versiones. El total
se calcula en una consulta agrupada para los formularios de la página. Los
permisos existentes determinan los enlaces y las acciones disponibles.

El contador está debajo de los filtros. La paginación aparece debajo de los
resultados únicamente cuando hace falta, conservando búsqueda, filtros y orden.
Formularios y Respuestas integran la navegación lateral en su título principal,
sin repetirlo en una franja superior.

## Verificación

`uv run python manage.py test apps.forms.tests.test_gallery_view --noinput`
comprueba recuentos entre versiones, autor, límites de fecha, filtros combinados,
paginación, permisos, formularios eliminados y número de consultas.

`uv run --with playwright python manage.py test apps.forms.tests.browser_gallery --noinput`
comprueba búsqueda con Enter, filtros, lista y tarjetas, navegación a respuestas,
menús, presentación móvil y capturas con datos ficticios.
