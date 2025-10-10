# Copilot Instructions for AlgoResearch-Dev

## Project Overview
AlgoResearch-Dev is a Django-based project with a modular structure. Key apps include `dashboard` and `myapp`, with core logic in `algoresearch/`. The project uses Celery for background tasks and Docker for containerization.

## Architecture & Key Components
- **Django Apps:**
  - `dashboard/`: Main business logic, models, forms, tasks, and views. Contains submodules for admin, context processors, middleware, migrations, realtime, scripts, signals, storage, templates, templatetags, utils, and views.
  - `myapp/`: Additional app with its own models, views, and management commands.
  - `algoresearch/`: Project-level config, ASGI/WSGI entrypoints, Celery setup, and URL routing.
- **Settings:**
  - Use `algoresearch.settings.dev` for local development and `algoresearch.settings.prod` for production (see `algoresearch/settings/README.md`).
- **Static & Media Files:**
  - Static assets in `static/`, `staticfiles/`, and `staticfiles_collected/`.
  - SCSS/CSS themes in `soft-ui-dashboard/`.
- **Docker:**
  - Use `docker-compose.yml` and `docker/Dockerfile` for local and production builds.

## Developer Workflows
- **Run Server:**
  - `python manage.py runserver --settings=algoresearch.settings.dev`
- **Run Celery Worker:**
  - `celery -A algoresearch worker --loglevel=info`
- **Run Tests:**
  - `pytest` (uses `pytest.ini`)
- **Database:**
  - Default: SQLite (`db.sqlite3`).
  - Backups: `backup.sql`, `backup_file.dump`.
- **Static Files:**
  - Collect: `python manage.py collectstatic --settings=algoresearch.settings.dev`

## Project-Specific Patterns
- **Settings Switching:**
  - Always specify the settings module for management commands.
- **Celery Integration:**
  - Tasks are defined in `dashboard/tasks.py` and registered in `algoresearch/celery.py`.
- **Custom Middleware, Signals, Context Processors:**
  - Extend via subfolders in `dashboard/`.
- **Testing:**
  - Tests are in `dashboard/` and `myapp/`.
  - Use `pytest` for all test runs.

## External Integrations
- **Docker:**
  - Build and run with `docker-compose up --build`.
- **SCSS/CSS:**
  - Customize UI via `soft-ui-dashboard/`.

## Examples
- To run a management command with production settings:
  - `python manage.py migrate --settings=algoresearch.settings.prod`
- To add a new Celery task:
  - Define in `dashboard/tasks.py`, import in `algoresearch/celery.py`.

## References
- `algoresearch/settings/README.md`: Settings usage.
- `docker/`: Docker setup.
- `soft-ui-dashboard/`: UI theming.
- `dashboard/`: Main app logic and patterns.

---
_Review and update this file as project conventions evolve._
