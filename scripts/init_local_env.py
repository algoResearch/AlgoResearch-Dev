#!/usr/bin/env python3
"""Create fresh local secrets without reading or overwriting an existing .env."""
import base64
import os
from pathlib import Path
import secrets


def main():
    target = Path(__file__).resolve().parents[1] / ".env"
    config = "\n".join([
        "DJANGO_SETTINGS_MODULE=algoresearch.settings.dev",
        "DEBUG=True",
        "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(48),
        "FERNET_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        "USE_INMEMORY_CHANNELS=1",
        "CELERY_EAGER=1",
        "# Docker Compose supplies its own local database and Redis URLs.",
        "# For a native install, add DEV_DATABASE_URL for your own local PostgreSQL database.",
        "",
    ])
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit("An .env already exists; left it unchanged. Use a fresh checkout for a separate installation.")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(config)
    print("Created .env with fresh local keys. Keep this file private.")


if __name__ == "__main__":
    main()
