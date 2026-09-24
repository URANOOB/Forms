from django.core.asgi import get_asgi_application

from config.environment import configure_settings

configure_settings()
application = get_asgi_application()
