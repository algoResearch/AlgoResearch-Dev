#!/usr/bin/env bash
set -euo pipefail

# If DEV_DATABASE_URL is set, we assume a real DB and (optionally) wait for it.
if [[ -n "${DEV_DATABASE_URL:-}" ]]; then
  echo "DEV_DATABASE_URL detected. Waiting for DB to be reachable..."
  # Basic wait using netcat if a TCP host/port is present
  # Expected form: postgres://user:pass@host:port/dbname
  host_port=$(python - <<'PY'
import os, sys
from urllib.parse import urlparse
u = urlparse(os.environ["DEV_DATABASE_URL"])
host = u.hostname or ""
port = u.port or 5432
print(f"{host}:{port}")
PY
)
  host="${host_port%:*}"
  port="${host_port#*:}"
  if [ -n "$host" ] && [ -n "$port" ]; then
    for i in {1..60}; do
      if nc -z "$host" "$port"; then
        echo "DB is up!"
        break
      fi
      echo "Waiting for DB ($host:$port)..."
      sleep 2
    done
  fi
fi

# Run migrations (SQLite file if no DEV_DATABASE_URL)
python manage.py migrate --noinput

# Optional: create a dev superuser non-interactively if flags provided
# (Dev only – do NOT use these in prod)
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_EMAIL:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  echo "Ensuring dev superuser exists..."
  python - <<'PY'
import os
from django.contrib.auth import get_user_model
import django
django.setup()
User = get_user_model()
u = os.environ["DJANGO_SUPERUSER_USERNAME"]
e = os.environ["DJANGO_SUPERUSER_EMAIL"]
p = os.environ["DJANGO_SUPERUSER_PASSWORD"]
if not User.objects.filter(username=u).exists():
    User.objects.create_superuser(u, e, p)
    print("Created superuser:", u)
else:
    print("Superuser already present:", u)
PY
fi

exec "$@"
