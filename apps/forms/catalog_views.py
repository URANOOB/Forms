from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from openpyxl.utils.exceptions import InvalidFileException

from .catalog_import import analyze_catalog


@require_POST
def import_catalog_view(request, model_admin):
    if not model_admin.has_change_permission(request):
        raise PermissionDenied
    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "Selecciona un archivo CSV, XLSX o XLSM."}, status=400)
    try:
        return JsonResponse(analyze_catalog(upload, request.POST))
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    except (ParseError, DefusedXmlException, InvalidFileException, OverflowError):
        return JsonResponse({"error": "El archivo no contiene una tabla válida."}, status=400)
