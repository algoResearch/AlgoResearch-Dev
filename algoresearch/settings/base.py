"""
Base Django settings shared by all environments (dev, prod, tests).
Do NOT put environment-specific secrets or toggles (like DEBUG) here.

Usage:
- Local:   DJANGO_SETTINGS_MODULE=algoresearch.settings.dev
- Prod:    DJANGO_SETTINGS_MODULE=algoresearch.settings.prod
"""
from pathlib import Path
import os
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured
from celery.schedules import crontab
import environ

# ---------------------------------
# Paths & environment
# ---------------------------------
# This file lives at: algoresearch/settings/base.py
# BASE_DIR should point to the project root (repo root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env from project root if present
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


# Helper: detect rediss:// (TLS Redis) safely in derived settings files
# Keep here so dev/prod can import and use the same function

def _is_rediss(url: str) -> bool:
    try:
        return urlparse(url).scheme == "rediss"
    except Exception:
        return str(url or '').startswith("rediss://")


# ---------------------------------
# Core Django
# ---------------------------------
# Do NOT set DEBUG here. Each env file sets it.

# Secrets are loaded here to be available to all environments, but
# enforcement ("must be set") should happen in prod.py only.
SECRET_KEY = env('DJANGO_SECRET_KEY', default=None)
FERNET_KEY = env('FERNET_KEY', default=None)

INSTALLED_APPS = [
    # 3rd-party first so middleware/app ordering is clearer
    'captcha',
    'corsheaders',               # required by CorsMiddleware
    'channels',                  # websockets/channels (layer configured per-env)
    'django_celery_beat',        # optional but kept as in your original
    'django_celery_results',
    'csp',                       # Content Security Policy
    'django.contrib.humanize', 
    # Django contrib
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Project apps
    'dashboard',
    'myapp',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # static in prod; harmless in dev
    'csp.middleware.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.common.BrokenLinkEmailsMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.TimezoneMiddleware',
    'dashboard.middleware.RoleBasedRedirectMiddleware',
]

ROOT_URLCONF = 'algoresearch.urls'
WSGI_APPLICATION = 'algoresearch.wsgi.application'
ASGI_APPLICATION = 'algoresearch.asgi.application'

AUTH_USER_MODEL = 'dashboard.User'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # use the shim module:
                'dashboard.cp.unread_conversations_count',
                'dashboard.cp.organization_context',
                'dashboard.cp.default_form_context',
                'dashboard.cp.default_profile_picture',
                'dashboard.cp.committee_membership_context',
            ],
        },
    },
]


APPEND_SLASH = False

# ---------------------------------
# Internationalization / time
# ---------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

# ---------------------------------
# Static & media
# ---------------------------------
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------
# CORS / Security / CSP (baseline)
# Specific hardening and S3 domains are added in prod.py
# Dev relaxations (unsafe-inline) are added in dev.py
# ---------------------------------
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

INTERNAL_IPS = ['127.0.0.1']

# django-csp v4+ config
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net"],
        "style-src": ["'self'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
        "img-src": ["'self'", "data:", "blob:"],
        "connect-src": ["'self'", "wss:"],
        "frame-src": ["'self'", "https://www.youtube.com", "https://www.youtube-nocookie.com"],
        "frame-ancestors": ["'none'"],
    },
}


# ---------------------------------
# Database
# ---------------------------------
# Intentionally not configured here. dev.py/prod.py will set DATABASES.

# ---------------------------------
# Channels / Redis
# ---------------------------------
# Configure CHANNEL_LAYERS per-environment in dev.py/prod.py
# (so local can use redis:// and prod can use rediss:// with SSL tweaks)

# ---------------------------------
# Celery
# ---------------------------------
# Common Celery settings (broker/backend URLs are set per-env)
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_EXPIRES = 3600
CELERY_TIMEZONE = TIME_ZONE

# Optional periodic schedule (kept from your original)
CELERY_BEAT_SCHEDULE = {
    'sample-task': {
        'task': 'dashboard.tasks.sample_task',
        'schedule': crontab(minute=0, hour='*/1'),  # Every hour
    },
}

# ---------------------------------
# File uploads
# ---------------------------------
FILE_UPLOAD_MAX_MEMORY_SIZE = 524288000  # 500 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 524288000

# ---------------------------------
# Emails (baseline). Actual host/port/backend per env
# ---------------------------------
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='algoResearch <noreply@localhost>')

# ---------------------------------
# Defaults
# ---------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'