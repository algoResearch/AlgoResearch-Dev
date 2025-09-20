from .base import *  # noqa
from .base import _is_rediss
import dj_database_url
import os
from django.core.exceptions import ImproperlyConfigured

# ----------------------
# Core toggles
# ----------------------
DEBUG = False
if os.environ.get("DYNO"):
    # Ensure the dyno is using prod settings explicitly
    assert os.environ.get("DJANGO_SETTINGS_MODULE") == "algoresearch.settings.prod", \
        "Heroku dyno must use algoresearch.settings.prod"

ALLOWED_HOSTS = [
    "ryanccarmody.com",
    "www.ryanccarmody.com",
    ".herokuapp.com",   # any herokuapp subdomain
]
if env("DEPLOY_TARGET", default="") != "prod":
    raise ImproperlyConfigured("Refusing to run prod settings without DEPLOY_TARGET=prod")

CSRF_TRUSTED_ORIGINS = [
    "https://ryanccarmody.com",
    "https://www.ryanccarmody.com",
    "https://*.herokuapp.com",
]

# (Optional) Only allow cross-site requests from your production origins
CORS_ALLOWED_ORIGINS = [
    "https://ryanccarmody.com",
    "https://www.ryanccarmody.com",
]

# ----------------------
# Required secrets in prod
# ----------------------
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in production.")
if not FERNET_KEY:
    raise ImproperlyConfigured("FERNET_KEY is required in production.")

# ----------------------
# Redis / Channels
# ----------------------
REDIS_URL = env("REDIS_URL", default=env("REDISCLOUD_URL", default=None))
if not REDIS_URL:
    raise ImproperlyConfigured("REDIS_URL (or REDISCLOUD_URL) is required in production.")

_channel_hosts = (
    [{"address": REDIS_URL, "ssl": True, "ssl_cert_reqs": None}]
    if _is_rediss(REDIS_URL) else
    [REDIS_URL]
)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": _channel_hosts},
    },
}

# Celery (prod)
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
if _is_rediss(REDIS_URL):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": None}

# Django cache (Redis)
_redis_opts = {"CLIENT_CLASS": "django_redis.client.DefaultClient"}
if _is_rediss(REDIS_URL):
    _redis_opts["CONNECTION_POOL_KWARGS"] = {"ssl_cert_reqs": None}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": _redis_opts,
        "KEY_PREFIX": "django",
    }
}

# ----------------------
# Database
# ----------------------
DATABASES = {"default": dj_database_url.config(conn_max_age=600, ssl_require=True)}

# ----------------------
# Storage: S3 for media, WhiteNoise for static
# ----------------------
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default=None)
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default=None)
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")

if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME]):
    raise ImproperlyConfigured("AWS_* env vars must be set in production.")

AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = False
AWS_S3_FILE_OVERWRITE = False
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"

STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},  # media
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=31536000, public"}

# CSP allow S3 for images and media
CONTENT_SECURITY_POLICY["DIRECTIVES"]["img-src"].append(f"https://{AWS_S3_CUSTOM_DOMAIN}")
CONTENT_SECURITY_POLICY["DIRECTIVES"].setdefault("media-src", ["'self'"]).append(
    f"https://{AWS_S3_CUSTOM_DOMAIN}"
)

# ----------------------
# Security hardening
# ----------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# Deprecated in Django 4.x: SECURE_BROWSER_XSS_FILTER -> remove
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year once you're confident
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# WhiteNoise static caching
WHITENOISE_MAX_AGE = 31536000  # 1 year

# ----------------------
# Email (required in prod)
# ----------------------
REQUIRED_EMAIL_SETTINGS = ["EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"]
for var in REQUIRED_EMAIL_SETTINGS:
    if env(var, default=None) in (None, ""):
        raise ImproperlyConfigured(f"{var} must be set in production.")

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="algoResearch <noreply@ryanccarmody.com>")

# ----------------------
# Logging to stdout (Heroku)
# ----------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "heroku": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "heroku",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}