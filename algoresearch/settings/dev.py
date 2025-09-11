from .base import *
from .base import _is_rediss
import dj_database_url

# ----------------------
# Dev toggles
# ----------------------
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Nice-to-have for dev
SECURE_SSL_REDIRECT = False

# ----------------------
# Redis / Channels (local-friendly)
# ----------------------
LOCAL_REDIS_URL = env("LOCAL_REDIS_URL", default="redis://127.0.0.1:6379/0")
REDIS_URL = env("REDIS_URL", default=LOCAL_REDIS_URL)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    },
}

# Celery (local)
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
if _is_rediss(REDIS_URL):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": None}

# ----------------------
# Database (dev)
# Prefer DEV_DATABASE_URL; fall back to SQLite for convenience
# ----------------------
DEV_DATABASE_URL = env("DEV_DATABASE_URL", default=None)
if DEV_DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DEV_DATABASE_URL, conn_max_age=0)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ----------------------
# Files / Static (local filesystem)
# ----------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},  # media
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ----------------------
# CSP relaxations for dev
# ----------------------
CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"].append("'unsafe-inline'")
CONTENT_SECURITY_POLICY["DIRECTIVES"]["style-src"].append("'unsafe-inline'")

# ----------------------
# Email (dev)
# Default to console backend to avoid sending real emails locally
# ----------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="algoResearch <noreply@localhost>")

# ----------------------
# Dev-only fallbacks for secrets
# ----------------------
if not SECRET_KEY:
    SECRET_KEY = "dev-only-secret-key"
if not FERNET_KEY:
    FERNET_KEY = "dev-only-fernet-key"
