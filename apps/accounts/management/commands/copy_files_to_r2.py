"""Copy referenced local files without rewriting database keys or deleting originals."""

import hashlib
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, StorageHandler
from django.core.management.base import BaseCommand, CommandError

from apps.forms.models import FormImage
from apps.submissions.models import SubmissionFile
from config.storage import storage_settings


def digest(storage, name):
    checksum = hashlib.sha256()
    with storage.open(name, "rb") as stream:
        for chunk in stream.chunks():
            checksum.update(chunk)
    return checksum.digest()


def copy_verified(source, destination, name, checksum):
    if destination.exists(name):
        if digest(destination, name) != checksum:
            raise CommandError("Un objeto de destino tiene contenido distinto. No se sobrescribió.")
        return False
    with source.open(name, "rb") as stream:
        saved = destination.save(name, stream)
    if saved != name:
        raise CommandError(
            "El destino cambió la clave. Detén las escrituras concurrentes y revisa."
        )
    if digest(destination, name) != checksum:
        raise CommandError("La verificación SHA-256 del archivo copiado falló.")
    return True


class Command(BaseCommand):
    help = "Comprueba archivos locales; con --apply los copia a R2 y verifica SHA-256."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Escribir y verificar en R2.")

    def handle(self, *args, **options):
        # Explicit local sources allow running against the copied DB before cutover too.
        sources = (
            (FormImage, FileSystemStorage(location=settings.MEDIA_ROOT)),
            (SubmissionFile, FileSystemStorage(location=settings.BASE_DIR / "private_uploads")),
        )
        inventory = {}
        for model, source in sources:
            for name in model.objects.values_list("file", flat=True).iterator():
                if not name:
                    raise CommandError("Hay un registro sin clave de archivo. Revisa el origen.")
                try:
                    checksum = digest(source, name)
                except OSError:
                    raise CommandError("Falta un archivo local o no se puede leer.") from None
                if name in inventory and inventory[name][1] != checksum:
                    raise CommandError(
                        "Dos archivos de origen comparten clave con distinto contenido."
                    )
                inventory[name] = (source, checksum)
        self.stdout.write(f"Archivos locales comprobados: {len(inventory)}.")
        if not options["apply"]:
            self.stdout.write("Simulación: no se ha escrito en R2 ni cambiado la base de datos.")
            return
        config = storage_settings(settings.BASE_DIR, {**os.environ, "FILE_STORAGE": "r2"})
        destination = StorageHandler(config)["responses"]
        copied = 0
        for name, (source, checksum) in inventory.items():
            copied += copy_verified(source, destination, name, checksum)
        self.stdout.write(
            self.style.SUCCESS(
                f"Verificados en R2: {len(inventory)}; nuevos: {copied}. Origen conservado."
            )
        )
