# Repository layout and moved files

The Django packages stay at their original import paths. Required root files such
as `manage.py`, `requirements.txt`, `Procfile`, `Aptfile`, and Docker Compose remain
where Django, Heroku, and Docker expect them.

## Where files went

| Former path | Current path |
| --- | --- |
| `load-tests/` | `dashboard/tests/load/` |
| `loadtest_*.py` | `dashboard/tests/load/loadtest_*.py` |
| Root `test_*.py` and `conftest.py` | `dashboard/tests/` |
| `soft-ui-dashboard/` | `static/vendor/soft-ui-dashboard/` |
| Root model diagrams and class images | `docs/diagrams/` |
| Old requirements files and legacy `views.py` | `docs/archive/` |
| `create_form_issues.sh` | `scripts/create_form_issues.sh` |
| `.githooks/` | `scripts/hooks/` |
| `MakeFile.m` | `Makefile` |
| `mydjango.conf` | `docker/nginx.conf` |
| `docker-compose.demo.yml` | `docker/compose.demo.yml` |
| Root `.devcontainer` template | `docker/devcontainer.json` |
| `algoResearchs.code-workspace` | `docs/algoresearch.code-workspace` |

`docs/archive/` holds historical references, not supported entry points. Install
from the root `requirements.txt`; run the application through `manage.py` or Daphne.
The configuration files under `docker/` are templates; the main README's Compose
setup remains the supported local startup path.

## Development commands

Run these from the repository root with your development environment active:

```bash
python manage.py check
python -m pytest dashboard/tests
python manage.py collectstatic --noinput
```

Tests require your own local PostgreSQL configuration. Load-test scripts and
Artillery scenarios now live together in `dashboard/tests/load/`. Review their
local target, user count, and authentication settings before running them.
Relative JavaScript processor paths still resolve within that directory. The
load-test workflow uses the new Python script locations.

If you previously enabled the repository's custom pre-push hook, update its path:

```bash
git config core.hooksPath scripts/hooks
```

This hook blocks direct pushes to the production Heroku remote. Do not enable it
alongside a different hook manager without deciding which hook system to use.

## Generated and private files

`staticfiles/`, `staticfiles_collected/`, and `staticfiles.tar.gz` were generated
output. Rebuild static files with `collectstatic`; source assets stay in `static/`.
Database backups, Redis dumps, cookies, logs, OS metadata, the sample PDF, and
empty scratch files are no longer tracked. The nested `AlgoResearch-Dev-master/`
folder contained only OS metadata. The empty root `templatetags/` package was not
registered or imported by the application.

The retired `monitor_db_connections.py` contained an embedded database credential
and connection-termination code. It is no longer part of the tracked application.
Do not execute a leftover local copy. Rotate the exposed credential and review
Git history separately; deleting current files does not erase earlier commits.

Existing local copies are preserved by the cleanup procedure, but users updating
an older checkout should back up any files they need before pulling deletions.
Do not commit or redistribute those private copies. This cleanup reduces the
current tree; it does not shrink old Git history or certify the entire codebase
as free of sensitive data.
