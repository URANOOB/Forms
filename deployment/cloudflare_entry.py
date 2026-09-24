"""WSGI bridge for the single-threaded Workers runtime."""

import asyncio
import os

from workers import WorkerEntrypoint, wsgi

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.workers"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
request_lock = asyncio.Lock()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        await request_lock.acquire()
        released = False

        def release():
            nonlocal released
            if not released:
                released = True
                request_lock.release()

        def serve(environ, start_response):
            response = application(environ, start_response)

            def body():
                try:
                    yield from response
                finally:
                    try:
                        response.close()
                    finally:
                        release()

            return body()

        try:
            # The SDK streams files. The lease is held until Django closes the
            # response, including cancellation, so database cleanup cannot overlap.
            return await wsgi.fetch(serve, request, self.env)
        except BaseException:
            release()
            raise
