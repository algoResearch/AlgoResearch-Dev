# algoresearch/settings/dev.py
from .base import *  # noqa
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# ----------------------
# Absolute safety: never run dev on Heroku
# ----------------------
if os.environ.get("DYNO") or os.environ.get("HEROKU_APP_NAME"):
    raise ImproperlyConfigured("Refusing to run dev settings on a Heroku dyno.")

# ----------------------
# Core dev toggles
# ----------------------
DEBUG = True
LOADTEST_SECRET = "super-secret-loadtest-key"  

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
EXTRA_ALLOWED_HOSTS = os.getenv("EXTRA_ALLOWED_HOSTS", "")
if EXTRA_ALLOWED_HOSTS:
    ALLOWED_HOSTS += [h.strip() for h in EXTRA_ALLOWED_HOSTS.split(",") if h.strip()]

# Force plain HTTP in dev
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Be explicit for repeatable local tests
SESSION_COOKIE_NAME = "sessionid"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Helpful for local forms / APIs
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:8000",
]

# CORS for local loopback origins
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:8000",
]
# If you use other local ports during testing, you can temporarily enable:
# CORS_ALLOW_ALL_ORIGINS = True  # (dev-only)

# ----------------------
# Channels (no Redis required by default)
# Use LOCAL_REDIS_URL only when explicitly requested
# ----------------------
USE_INMEMORY_CHANNELS = env.bool("USE_INMEMORY_CHANNELS", False)  # default False now
USE_TWO_FACTOR = True
LOGIN_URL = "login"

if USE_INMEMORY_CHANNELS:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    CHAT_REDIS_URL = None  # typing_service will fallback to in-memory
else:
    LOCAL_REDIS_URL = env("LOCAL_REDIS_URL", default="redis://127.0.0.1:6379/0")
    REDIS_URL = LOCAL_REDIS_URL
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        },
    }
    # Expose this for app utilities like typing_service
    CHAT_REDIS_URL = REDIS_URL

# ----------------------
# Celery (run tasks inline by default, no broker needed)
# If you want real workers locally, set CELERY_EAGER=0 and USE_INMEMORY_CHANNELS=0
# ----------------------
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_EAGER", True)

if not CELERY_TASK_ALWAYS_EAGER and not USE_INMEMORY_CHANNELS:
    # Use the same local Redis, never prod REDIS_URL
    CELERY_BROKER_URL = LOCAL_REDIS_URL
    CELERY_RESULT_BACKEND = LOCAL_REDIS_URL

# ----------------------
# Caches (local memory – avoids any redis cache backends)
# ----------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "lockout-cache",
    }
}

# ----------------------
# Database (SQLite by default; opt-in Postgres)
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
# CSP relaxations for dev (new django-csp dict format)
# ----------------------
CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"].append("'unsafe-inline'")
CONTENT_SECURITY_POLICY["DIRECTIVES"]["style-src"].append("'unsafe-inline'")

# ----------------------
# Email (force console in dev; ignore SMTP env)
# ----------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "algoResearch <noreply@localhost>"

# Neutralize any SMTP settings that might exist in the shell environment
EMAIL_HOST = ""
EMAIL_PORT = 25
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""

# ----------------------
# Dev-only fallbacks for secrets
# ----------------------
if not SECRET_KEY:
    SECRET_KEY = "dev-only-secret-key"
if not FERNET_KEY:
    FERNET_KEY = "dev-only-fernet-key"

# ----------------------
# Optional: extra visibility during WS load tests
# ----------------------

FILE_CHUNK_SIZE = 2 * 1024 * 1024 
