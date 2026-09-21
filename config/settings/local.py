from .base import *  # noqa: F403
from .base import env_bool, env_list

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = SECRET_KEY or "local-development-only-not-for-deployment"  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
ENABLE_DEMO_SEED = True
