# Developer Setup

## Prereqs
- Python 3.12 (or the repo’s current version)
- Virtualenv (recommended)  
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install -U pip wheel
  pip install -r requirements.txt

## Quick start
```bash
cp .env.example .env
make setup
make dev

1. Open Codespace
2. Create Virtual enviroment and install dependencies,
This script in the terminal: python -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt

3. Create your .env: cp .env.example .env

4. Add in the .env is 
(**** RUN "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

DJANGO_SETTINGS_MODULE=algoresearch.settings.dev
DEBUG=True

FERNET_KEY=REPLACE_WITH_FERNET_KEY

5. Run Database
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000

If ran locally, run 
python -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
cp .env.example .env
# edit .env: DJANGO_SETTINGS_MODULE, DEBUG, FERNET_KEY, optional DEV_DATABASE_URL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver


Use:

python manage.py runserver 0.0.0.0:8000

# Migrations
python manage.py makemigrations
python manage.py migrate

# Shell & superuser
python manage.py shell
python manage.py createsuperuser

# Celery (only if you disable eager in dev)
celery -A algoresearch worker -l info
celery -A algoresearch beat -l info

# Lint/format (Makefile)
make lint
make format
make precommit

# Tests
python manage.py test

Useful Commands: 
python manage.py runserver 0.0.0.0:8000

# Migrations
python manage.py makemigrations
python manage.py migrate

# Shell & superuser
python manage.py shell
python manage.py createsuperuser

# Celery (only if you disable eager in dev)
celery -A algoresearch worker -l info
celery -A algoresearch beat -l info

# Lint/format (Makefile)
make lint
make format
make precommit

# Tests
python manage.py test
