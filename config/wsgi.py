from django.core.wsgi import get_wsgi_application

from config.environment import configure_settings

configure_settings()
application = get_wsgi_application()
