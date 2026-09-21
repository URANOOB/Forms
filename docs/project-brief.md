# CONTEXTO DEL PROYECTO

Quiero construir una plataforma web institucional de formularios dinámicos, comparable conceptualmente con una versión privada y especializada de Typeform/Jotform, pero considerablemente más pequeña y orientada a una institución que recopila información sensible y documentos de personas.

La aplicación será utilizada aproximadamente por 20 personas al día, por lo que no necesitamos diseñar para cargas absurdas ni introducir infraestructura innecesaria. Sin embargo, la arquitectura debe ser robusta, segura, mantenible y capaz de crecer sin necesitar una reescritura.

El usuario final únicamente debe ver los formularios públicos.

El personal de la institución tendrá acceso a un panel administrativo desde el cual podrá:

* crear formularios;
* editar formularios;
* duplicarlos;
* archivarlos;
* publicarlos;
* pausarlos;
* configurar campos;
* crear secciones;
* configurar lógica condicional;
* consultar respuestas;
* consultar documentos;
* descargar documentos individuales;
* descargar documentos agrupados en ZIP;
* exportar respuestas a Excel;
* consultar métricas;
* configurar correos de notificación;
* administrar usuarios y permisos.

---

# STACK PRINCIPAL

Utilizar:

* Python
* Django
* PostgreSQL
* Supabase exclusivamente como PostgreSQL administrado
* Django Admin
* Django Unfold para la interfaz administrativa
* Cloudflare R2 para almacenamiento de archivos
* Django Templates
* HTMX cuando tenga sentido
* Alpine.js únicamente para interacciones pequeñas del frontend si realmente aporta valor
* JavaScript/TypeScript ligero cuando sea necesario para el constructor de formularios

No utilizar:

* Next.js
* React como frontend completo
* Supabase Auth
* Supabase Storage
* Firebase
* MongoDB
* microservicios
* Kubernetes
* Redis inicialmente salvo que aparezca una necesidad real
* Celery inicialmente salvo que aparezca una necesidad real

Evitar sobreingeniería.

La aplicación debe comenzar como un monolito Django bien estructurado.

---

# INFRAESTRUCTURA

Arquitectura deseada:

Cloudflare
→ Django
→ Supabase PostgreSQL

y:

Navegador
→ subida directa
→ Cloudflare R2

Los archivos NO deben almacenarse como blobs dentro de PostgreSQL.

PostgreSQL únicamente debe guardar:

* metadata;
* referencia al archivo;
* tamaño;
* MIME type;
* nombre original;
* checksum;
* fecha;
* usuario asociado;
* información relacionada.

Los buckets de R2 deben ser privados.

Nunca almacenar documentos sensibles en URLs públicas permanentes.

Para visualización o descarga se deben utilizar mecanismos temporales y seguros.

---

# IMPORTANTE SOBRE CLOUDFLARE

El objetivo es desplegar Django sobre Cloudflare Python Workers.

Sin embargo, este soporte es relativamente reciente.

Por lo tanto:

1. Mantener el proyecto lo más estándar posible.
2. No acoplar lógica de negocio a Cloudflare.
3. Aislar integración con R2.
4. Aislar configuración de infraestructura.
5. Mantener compatibilidad para poder mover Django posteriormente a un hosting Python tradicional sin reescribir la aplicación.

Cloudflare es el deployment target, no debe convertirse en el corazón de la aplicación.

---

# DOMINIOS PRINCIPALES

Separar conceptualmente el proyecto en aplicaciones Django similares a:

accounts/
forms/
submissions/
documents/
notifications/
exports/
analytics/
audit/

No crear aplicaciones innecesariamente pequeñas.

Mantener cohesión de dominio.

---

# MODELO CONCEPTUAL

La aplicación debe contemplar aproximadamente las siguientes entidades.

## Workspace

Representa un espacio lógico.

Inicialmente puede existir un único workspace institucional, pero el diseño debe permitir varios en el futuro.

Campos aproximados:

* id UUID
* name
* slug
* created_at
* updated_at
* is_active

---

# Form

Representa un formulario.

Campos aproximados:

* id UUID
* workspace
* name
* slug
* description
* status
* active_version
* created_by
* created_at
* updated_at

Estados:

DRAFT
PUBLISHED
PAUSED
ARCHIVED

Un formulario con respuestas NO debe eliminarse físicamente desde una acción normal del administrador.

Debe archivarse.

---

# FORM VERSIONING

Este requisito es CRÍTICO.

Los formularios deben estar versionados.

Cuando un formulario publicado recibe respuestas, futuras modificaciones estructurales no deben modificar retrospectivamente la interpretación de respuestas antiguas.

Ejemplo:

Version 1:

* Nombre
* Documento
* Diagnóstico

Después se agregan:

* EPS
* Ciudad

Las respuestas originales deben seguir asociadas a Version 1.

Las nuevas respuestas utilizarán Version 2.

Considerar una entidad:

FormVersion

Campos aproximados:

* id UUID
* form
* version_number
* status
* published_at
* created_at
* schema_version

No implementar versionado de una forma artificialmente complicada.

---

# SECCIONES

Un formulario puede contener secciones.

FormSection:

* id
* form_version
* title
* description
* order
* configuration

---

# CAMPOS

FormField:

* id UUID
* section
* stable_key
* label
* help_text
* field_type
* required
* placeholder
* order
* configuration JSONB
* validation JSONB

Tipos iniciales:

SHORT_TEXT
LONG_TEXT
EMAIL
PHONE
NUMBER
DATE
SINGLE_CHOICE
MULTIPLE_CHOICE
BOOLEAN
FILE
DOCUMENT
HEADING
INFORMATION

Diseñar de manera extensible.

No crear una tabla diferente por cada tipo de campo.

---

# OPCIONES

Para campos de selección:

FieldOption:

* id
* field
* label
* value
* order
* is_active

---

# LÓGICA CONDICIONAL

Debe ser posible crear condiciones como:

IF diagnóstico_confirmado == true
THEN mostrar:

* diagnosis_type
* diagnosis_date
* medical_certificate

Operadores iniciales:

EQUALS
NOT_EQUALS
CONTAINS
GREATER_THAN
LESS_THAN
IS_EMPTY
IS_NOT_EMPTY

Permitir inicialmente:

AND
OR

Las reglas deben almacenarse como datos y NO como código Python dinámico.

Nunca ejecutar código ingresado desde el panel administrativo.

Modelo conceptual:

ConditionalRule

* form_version
* source_field
* operator
* expected_value
* action
* target_field / target_section
* group
* order

Acciones iniciales:

SHOW
HIDE
REQUIRE
OPTIONAL

Mantener la implementación inicial sencilla.

---

# FORMULARIO PÚBLICO

Cada formulario publicado debe tener una URL independiente.

Ejemplo:

/f/registro-pacientes/
/f/actualizacion-datos/

El formulario público debe:

* ser mobile-first;
* funcionar bien en celular;
* ser accesible;
* ser rápido;
* mostrar únicamente campos relevantes;
* aplicar lógica condicional inmediatamente;
* conservar los datos introducidos durante la interacción;
* validar cliente y servidor;
* nunca confiar únicamente en JavaScript;
* tener mensajes de error claros;
* permitir carga de documentos;
* mostrar progreso razonable;
* impedir doble envío accidental.

No mostrar Django Admin al usuario final.

---

# RESPUESTAS

Submission:

* id UUID
* form
* form_version
* status
* started_at
* submitted_at
* ip hash si realmente se considera necesario
* user_agent opcional
* metadata JSONB

Evitar guardar información innecesaria.

Estados aproximados:

STARTED
SUBMITTED
UNDER_REVIEW
VALIDATED
REJECTED

---

# RESPUESTAS INDIVIDUALES

SubmissionAnswer:

* submission
* field
* value

Analizar cuidadosamente cómo representar:

* strings
* números
* fechas
* booleanos
* arrays
* respuestas múltiples

Se puede utilizar JSONB para value siempre que exista una capa de validación clara.

No almacenar todas las respuestas del formulario como un único JSON gigante si eso perjudica filtrado, exportación o auditoría.

Buscar equilibrio entre flexibilidad y capacidad de consulta.

---

# DOCUMENTOS

UploadedDocument:

* id UUID
* submission
* field
* storage_key
* original_filename
* mime_type
* size
* sha256
* uploaded_at
* status

Estados:

PENDING
UPLOADED
VALIDATED
REJECTED

Los documentos estarán en Cloudflare R2.

Nunca usar el nombre original como storage_key definitivo.

Generar claves no predecibles.

Ejemplo conceptual:

workspace_uuid/
form_uuid/
submission_uuid/
document_uuid.pdf

---

# SEGURIDAD DE ARCHIVOS

Validar:

* extensión;
* MIME;
* tamaño máximo;
* tipos permitidos;
* nombre;
* duplicados cuando tenga sentido.

No confiar en la extensión del archivo.

Preparar arquitectura para incorporar antivirus posteriormente.

No implementar OCR todavía.

Dejar preparada la entidad/document status para añadirlo después.

---

# FORM WORKSPACE

Cada formulario debe tener una vista administrativa propia parecida a:

Formulario
├── Resumen
├── Constructor
├── Respuestas
├── Documentos
├── Métricas
├── Exportaciones
├── Notificaciones
└── Configuración

No necesitamos que estas sean aplicaciones separadas.

Son secciones dentro del workspace administrativo de un formulario.

---

# CONSTRUCTOR DE FORMULARIOS

Este será uno de los componentes personalizados principales.

No intentar hacerlo exclusivamente utilizando ModelAdmin tradicionales.

Crear una vista administrativa propia integrada visualmente con Django Unfold.

Debe permitir eventualmente:

* crear sección;
* crear campo;
* editar campo;
* eliminar campo;
* duplicar campo;
* mover campos;
* ordenar;
* configurar required;
* configurar opciones;
* configurar validación;
* configurar condiciones.

Para V1 puede utilizar botones arriba/abajo en lugar de drag & drop si eso reduce considerablemente la complejidad.

Priorizar confiabilidad frente a animaciones bonitas.

---

# RESPUESTAS EN ADMIN

Debe existir una vista tabular dinámica.

Ejemplo:

Fecha | Nombre | Documento | Estado

Como los formularios pueden ser diferentes, las columnas deben poder derivarse de los campos configurados.

Debe existir:

* búsqueda;
* filtros;
* filtros por fecha;
* filtros por estado;
* detalle de respuesta;
* acceso a documentos;
* selección múltiple.

---

# DETALLE DE RESPUESTA

Mostrar información organizada por sección.

Ejemplo:

Información personal

Nombre: Juan Pérez
Documento: 123...
Fecha de nacimiento: ...

Información médica

Diagnóstico: ...
Fecha: ...

Documentos

Cédula.pdf
[Ver]
[Descargar]

Certificado.pdf
[Ver]
[Descargar]

Registrar acciones relevantes en auditoría.

---

# EXCEL

Permitir exportar respuestas a .xlsx.

Las columnas deben derivarse del FormVersion correspondiente.

Debe ser posible exportar:

* todas las respuestas;
* respuestas filtradas;
* respuestas seleccionadas.

El Excel debe tener encabezados legibles.

No usar claves internas como encabezados visibles si existe label.

Considerar una hoja adicional de metadata si resulta útil.

---

# ZIP

Permitir descargar documentos:

* individualmente;
* documentos de una Submission;
* documentos de múltiples Submission;
* exportación masiva.

Formato sugerido:

export.zip
├── respuestas.xlsx
├── submission_001/
│   ├── documento_identidad.pdf
│   └── certificado.pdf
├── submission_002/
│   └── documento_identidad.pdf
└── manifest.json

Las exportaciones grandes deben prepararse para ser procesadas asíncronamente en una fase posterior.

No cargar potencialmente gigabytes enteros en memoria.

---

# NOTIFICACIONES

Cada formulario puede definir una o varias direcciones de correo.

Cuando llegue una respuesta:

Submission.created
→ Notification

La respuesta del formulario NO debe depender de que el correo sea enviado correctamente.

Si el proveedor de email falla:

* la Submission debe seguir registrada;
* registrar fallo;
* permitir reintentar.

Crear abstracción para provider de correo.

No acoplar la lógica al proveedor.

---

# MÉTRICAS

V1:

* total de respuestas;
* respuestas hoy;
* respuestas últimos 7 días;
* respuestas últimos 30 días;
* número de documentos;
* respuestas por estado;
* tendencia diaria.

Posteriormente:

* formulario iniciado;
* formulario completado;
* tasa de abandono;
* tiempo promedio;
* sección donde abandonan.

No recopilar analítica invasiva innecesaria.

---

# USUARIOS Y PERMISOS

Usar:

django.contrib.auth

Utilizar:

Users
Groups
Permissions

Roles iniciales conceptuales:

ADMIN
MANAGER
REVIEWER
VIEWER

Ejemplos:

ADMIN:
todo

MANAGER:
formularios
respuestas
exportaciones
métricas

REVIEWER:
respuestas
documentos
validaciones

VIEWER:
solo lectura

No implementar RBAC paralelo desde cero.

Extender permisos Django cuando sea necesario.

---

# AUDITORÍA

Debido a que se manejarán datos sensibles, registrar eventos relevantes.

Ejemplos:

FORM_CREATED
FORM_UPDATED
FORM_PUBLISHED
SUBMISSION_VIEWED
DOCUMENT_VIEWED
DOCUMENT_DOWNLOADED
EXPORT_CREATED
EXPORT_DOWNLOADED
SUBMISSION_STATUS_CHANGED

AuditLog:

* actor
* action
* object_type
* object_id
* timestamp
* metadata

No guardar datos sensibles completos dentro del audit log.

---

# DATOS SENSIBLES

La plataforma manejará potencialmente información relacionada con salud.

Por ello:

* aplicar principio de mínimo privilegio;
* evitar exposición innecesaria;
* proteger documentos;
* usar HTTPS;
* evitar logs con información sensible;
* no imprimir respuestas completas en consola;
* no enviar información sensible a servicios externos innecesariamente;
* utilizar secretos mediante variables de entorno;
* nunca commitear credenciales;
* crear controles de acceso claros;
* mantener trazabilidad.

---

# BORRADO

Evitar hard delete de:

* Formularios que tengan respuestas.
* Submissions importantes.
* Documentos sin proceso deliberado.

Preferir archivado o estados.

Si se implementa eliminación definitiva posteriormente, debe ser una operación explícita, auditada y protegida.

---

# UUID

Preferir UUID para entidades expuestas públicamente o sensibles.

Nunca utilizar IDs secuenciales como mecanismo de seguridad.

---

# SLUGS

Cada formulario debe tener un slug legible.

Ejemplo:

registro-pacientes

URL:

/f/registro-pacientes/

El slug debe ser único dentro del workspace correspondiente.

---

# VALIDACIONES

Debe existir una capa de validación backend independiente del frontend.

Un usuario nunca debe poder enviar:

* un campo oculto con un valor inválido;
* un campo required faltante;
* una opción inexistente;
* un tipo incorrecto;
* un archivo no permitido.

El backend debe reconstruir y validar las reglas correspondientes al FormVersion enviado.

---

# RENDIMIENTO

Carga aproximada inicial:

20 usuarios/día.

Por tanto:

NO realizar optimizaciones prematuras.

Sí:

* evitar N+1 queries;
* usar select_related/prefetch_related;
* índices razonables;
* paginación;
* streaming donde aplique;
* consultas correctas.

No diseñar para millones de requests diarios.

---

# TESTING

No llenar el proyecto de tests triviales.

Priorizar tests de lógica crítica:

* versionado;
* conditional rules;
* validación;
* permisos;
* submissions;
* exportaciones;
* seguridad de documentos.

---

# EXPERIENCIA DEL DESARROLLADOR

Quiero:

* código legible;
* type hints donde aporten;
* nombres claros;
* docstrings únicamente cuando expliquen decisiones importantes;
* servicios pequeños y bien delimitados;
* evitar archivos gigantes;
* evitar abstracciones prematuras;
* evitar patrones enterprise innecesarios;
* mantener Django idiomático.

---

# MIGRACIONES

Toda modificación al esquema debe realizarse mediante Django migrations.

No editar manualmente la DB de producción.

---

# VARIABLES DE ENTORNO

Como mínimo contemplar:

DATABASE_URL

DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS

R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_ENDPOINT

EMAIL_PROVIDER
EMAIL_FROM
EMAIL_API_KEY

---

# UX DEL ADMIN

La interfaz administrativa debe sentirse como una aplicación institucional, no como Django Admin sin personalizar.

Usar Unfold.

Sidebar aproximado:

Dashboard

Formularios

Respuestas

Exportaciones

Usuarios

Auditoría

No mostrar modelos técnicos innecesarios al usuario administrativo.

---

# REGLA FUNDAMENTAL DE DESARROLLO

No construir todo de una vez.

Trabajar por fases.

En cada fase:

1. Analizar estado actual.
2. Proponer cambios concretos.
3. Implementar únicamente el alcance de esa fase.
4. Ejecutar migrations.
5. Ejecutar checks.
6. Ejecutar tests relevantes.
7. Revisar errores.
8. Corregir antes de avanzar.
9. Documentar decisiones importantes.

No anticipar 5 fases creando código que todavía no necesitamos.

---

# FASES

## FASE 1 — Foundation

* Django project.
* settings.
* PostgreSQL.
* Unfold.
* estructura de apps.
* custom user si es conveniente hacerlo desde el inicio.
* Workspace.
* Form.
* FormVersion.
* FormSection.
* FormField.
* FieldOption.
* ConditionalRule.
* Admin básico.
* migrations.
* fixtures o seed mínimo.
* estructura visual inicial.

NO formulario público todavía.

---

## FASE 2 — Form Builder

Crear workspace administrativo propio para formularios.

Implementar:

* crear formulario;
* secciones;
* campos;
* opciones;
* orden;
* edición;
* conditional rules;
* draft;
* publish;
* versionado.

Priorizar funcionalidad.

---

## FASE 3 — Public Form Runtime

Implementar:

/f/<slug>/

Render dinámico.

Lógica condicional.

Validación.

Submission.

SubmissionAnswer.

Responsive/mobile.

Protección contra doble envío.

---

## FASE 4 — Documents

Integración Cloudflare R2.

Upload directo.

UploadedDocument.

URLs temporales.

Descarga protegida.

Validación.

Security checks.

---

## FASE 5 — Response Workspace

Listado.

Filtros.

Detalle.

Estados.

Documentos.

Acciones administrativas.

Permisos.

---

## FASE 6 — Notifications

NotificationRule.

Email provider abstraction.

Nuevo submission → email.

Retries básicos.

Logging seguro.

---

## FASE 7 — Exports

Excel.

ZIP.

Manifest.

Selección.

Filtros.

Preparación para exportaciones asíncronas.

---

## FASE 8 — Analytics

Dashboard del formulario.

Métricas.

Gráficos mínimos.

No construir un Google Analytics casero.

---

## FASE 9 — Security & Audit

AuditLog.

Revisión permisos.

Logs.

Rate limits si son necesarios.

Headers.

CSRF.

Session security.

Revisión archivos.

---

## FASE 10 — Cloudflare deployment

Docker/local development no debe depender de Cloudflare.

Preparar deployment en Python Workers.

Validar:

* Django;
* Unfold;
* static files;
* PostgreSQL;
* R2;
* exports;
* dependencias.

Si una dependencia crítica no es compatible con Python Workers:

NO reescribir medio sistema para obligarlo a funcionar.

Documentar el problema y mantener preparado deployment alternativo convencional.

---

# FUERA DE ALCANCE V1

No implementar todavía:

OCR
AI
firma digital
workflow complejo
API pública
mobile app
multi-tenant billing
custom domains
webhooks externos
realtime
chat
Redis
Celery
motor BPM
drag-and-drop sofisticado

Dejar arquitectura preparada, pero no código muerto.

---

# OBJETIVO DE CALIDAD

Busco una plataforma:

* simple;
* segura;
* mantenible;
* rápida;
* extensible;
* fácil de operar;
* agradable para usuarios no técnicos.

La arquitectura debe parecer construida para las necesidades reales de este proyecto, no como si intentáramos impresionar a un comité de arquitectos cloud.

Ante dos soluciones igualmente correctas, escoger la más simple.
