"""Measured storage usage; never confuse a free allowance with bucket capacity."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage, storages
from django.db import DatabaseError, connection, transaction
from django.utils import formats, timezone
from storages.backends.s3 import S3Storage

from apps.submissions.models import SubmissionFile


def storage_size(value):
    """Decimal units, so a 500,000,000-byte allowance displays as 500 MB."""
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if number < 1000 or unit == "PB":
            number = round(number, 2)
            places = 0 if number.is_integer() else 2
            return f"{formats.number_format(number, places, force_grouping=True)} {unit}"
        number /= 1000


def capacity_info(info, capacity, *, reference=False):
    info.update(
        checked_at=timezone.now(),
        capacity_bytes=capacity,
        capacity_label="Referencia gratuita" if reference else "Capacidad",
        remaining_label="Margen de referencia" if reference else "Disponible",
    )
    info["capacity_display"] = storage_size(capacity) if capacity is not None else None
    info["used_display"] = storage_size(info["bytes"]) if info["available"] else "No disponible"
    if info["available"] and capacity is not None:
        info["remaining_bytes"] = max(capacity - info["bytes"], 0)
        info["remaining_display"] = storage_size(info["remaining_bytes"])
        info["percent"] = round(info["bytes"] * 100 / capacity, 1)
        info["progress"] = min(info["percent"], 100)
        info["percent_label"] = "de la referencia gratuita" if reference else "de la capacidad"
        if info["bytes"] > capacity:
            info["state"] = (
                "Referencia gratuita superada" if reference else "Capacidad superada"
            ) + f" por {storage_size(info['bytes'] - capacity)}"
            info["over_capacity"] = True
    elif not info["available"]:
        info["remaining_display"] = "No disponible"
    else:
        info["remaining_display"] = (
            "Sin límite fijo" if info.get("is_r2") else "Sin capacidad configurada"
        )
    return info


def database_info():
    host = connection.settings_dict.get("HOST", "")
    supabase = host.endswith((".supabase.com", ".supabase.co"))
    info = {
        "kind": "database",
        "label": "Base de datos",
        "provider": "Supabase PostgreSQL" if supabase else "PostgreSQL",
        "available": False,
        "scope": "Bases de datos e índices del proyecto" if supabase else "Base de datos local",
    }
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            # Supabase reports database usage across the project's Postgres cluster.
            cursor.execute(
                "SELECT sum(pg_database_size(datname)) FROM pg_database"
                if supabase
                else "SELECT pg_database_size(current_database())"
            )
            info["bytes"] = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = current_schema()"
            )
            info["tables"] = cursor.fetchone()[0]
        info.update(available=True, state="Uso real consultado en PostgreSQL")
    except DatabaseError:
        info["state"] = "No se pudo consultar el almacenamiento"
    return capacity_info(info, settings.DATABASE_CAPACITY_BYTES)


def _file_storages():
    return [storages["default"], SubmissionFile._meta.get_field("file").storage]


def _bucket_client(storage):
    return boto3.client(
        "s3",
        endpoint_url=storage.endpoint_url,
        region_name=storage.region_name,
        aws_access_key_id=storage.access_key,
        aws_secret_access_key=storage.secret_key,
        aws_session_token=storage.security_token,
        config=Config(
            signature_version="s3v4",
            connect_timeout=3,
            read_timeout=5,
            retries={"total_max_attempts": 1},
        ),
    )


def bucket_usage(storage):
    """Count complete objects across every page, including unreferenced objects."""
    client = _bucket_client(storage)
    total = objects = 0
    standard_only = True
    deadline = time.monotonic() + 10
    try:
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=storage.bucket_name)
        for page in pages:
            if time.monotonic() > deadline:
                raise TimeoutError("Bucket listing exceeded the dashboard budget")
            contents = page.get("Contents", [])
            total += sum(item["Size"] for item in contents)
            objects += len(contents)
            standard_only &= all(
                item.get("StorageClass", "STANDARD") == "STANDARD" for item in contents
            )
        return total, objects, standard_only
    finally:
        client.close()


def _local_usage(backends):
    roots = []
    for root in sorted({Path(s.location).resolve() for s in backends}, key=lambda p: len(p.parts)):
        if not any(root.is_relative_to(parent) for parent in roots):
            roots.append(root)
    total = objects = 0

    def fail(error):
        raise error

    for root in roots:
        for directory, _, names in os.walk(root, onerror=fail, followlinks=False):
            for name in names:
                path = Path(directory) / name
                if not path.is_symlink():
                    total += path.stat().st_size
                    objects += 1
    return total, objects


def files_info():
    backends = _file_storages()
    info = {
        "label": "Archivos",
        "kind": "files",
        "available": False,
        "provider": "Almacenamiento de archivos",
    }
    allowance = None
    try:
        if all(isinstance(s, S3Storage) for s in backends):
            buckets = {(s.endpoint_url, s.bucket_name): s for s in backends}
            info["is_r2"] = all(
                (urlsplit(s.endpoint_url or "").hostname or "").endswith(
                    ".r2.cloudflarestorage.com"
                )
                for s in backends
            )
            info["provider"] = "Cloudflare R2" if info["is_r2"] else "Almacenamiento S3"
            info["scope"] = " · ".join(s.bucket_name for s in buckets.values())
            if info["is_r2"]:
                info["capacity_note"] = (
                    "Sin límite fijo de capacidad. Los 10 GB-mes gratuitos de Estándar se "
                    "comparten entre los buckets de la cuenta. El margen mostrado compara "
                    "solo este bucket hoy; no es el saldo mensual de facturación."
                )
                if len(buckets) == 1:
                    allowance = settings.R2_FREE_STORAGE_REFERENCE_BYTES
            results = [bucket_usage(s) for s in buckets.values()]
            info["bytes"] = sum(row[0] for row in results)
            info["objects"] = sum(row[1] for row in results)
            if not all(row[2] for row in results):
                allowance = None
            info["state"] = "Contenido completo del bucket"
        elif all(isinstance(s, FileSystemStorage) for s in backends):
            info["provider"] = "Almacenamiento local"
            info["scope"] = "Imágenes y adjuntos del entorno local"
            info["bytes"], info["objects"] = _local_usage(backends)
            info["state"] = "Archivos presentes en las carpetas de almacenamiento"
        else:
            raise NotImplementedError("Unsupported or mixed storage providers")
        info["available"] = True
    except (OSError, NotImplementedError, BotoCoreError, ClientError):
        info["state"] = "No se pudo consultar el uso completo del almacenamiento"
        info.pop("bytes", None)
        info.pop("objects", None)
    return capacity_info(info, allowance, reference=allowance is not None)


def infrastructure_info():
    # Isolate caches by environment, bucket and capacity; never put credentials in keys.
    identity = {
        "database": [connection.settings_dict.get(k) for k in ("HOST", "PORT", "NAME", "USER")],
        "storages": [
            [
                s.__class__.__name__,
                getattr(s, "endpoint_url", None),
                getattr(s, "bucket_name", None),
                getattr(s, "base_location", None),
            ]
            for s in _file_storages()
        ],
        "capacity": [settings.DATABASE_CAPACITY_BYTES, settings.R2_FREE_STORAGE_REFERENCE_BYTES],
        "language": settings.LANGUAGE_CODE,
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, default=str, sort_keys=True).encode()
    ).hexdigest()
    key = f"dashboard-infrastructure-v3:{fingerprint}"
    data = cache.get(key)
    if data is None:
        data = [database_info(), files_info()]
        cache.set(key, data, 300 if all(item["available"] for item in data) else 30)
    return data
