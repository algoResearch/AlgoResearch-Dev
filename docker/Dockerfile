# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System deps for psycopg2, Pillow, and WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl netcat-openbsd pkg-config \
    libjpeg-dev zlib1g-dev libfreetype6-dev liblcms2-dev libtiff5-dev libwebp-dev \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info \
    libcairo2 libgirepository1.0-dev gir1.2-pango-1.0 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=algoresearch.settings.dev \
    PORT=8000

# Build argument for Fernet key (used during collectstatic)
ARG FERNET_KEY=""
ENV FERNET_KEY=${FERNET_KEY}

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install --prefer-binary -r requirements.txt

# Copy project
COPY . /app

# Optionally collect static (noop in dev storage; harmless if missing)
RUN python manage.py collectstatic --noinput || true

# Entrypoint to (optionally) wait for DB, run migrations, seed superuser in dev
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# Use Gunicorn+Uvicorn ASGI (closer to prod behavior)
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "algoresearch.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
