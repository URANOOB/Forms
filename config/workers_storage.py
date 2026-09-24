"""Keep S3 signature headers intact through Pyodide's Fetch transport."""

from storages.backends.s3 import S3Storage


def normalize_s3_headers(request, **kwargs):
    for name, value in list(request.headers.items()):
        if isinstance(value, bytes):
            request.headers[name] = value.decode("utf-8")


class WorkersS3Storage(S3Storage):
    def _create_session(self):
        session = super()._create_session()
        session.events.register("before-send.s3", normalize_s3_headers)
        return session
