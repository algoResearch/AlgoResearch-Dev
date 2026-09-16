# ---------- Project knobs ----------
APP            ?= algoresearch
DJANGO_SETTINGS?= algoresearch.settings.dev
VENV           ?= .venv
PY             ?= $(VENV)/bin/python
PIP            ?= $(VENV)/bin/pip
PRECOMMIT      ?= $(VENV)/bin/pre-commit
RUFF           ?= $(VENV)/bin/ruff
BLACK          ?= $(VENV)/bin/black
ISORT          ?= $(VENV)/bin/isort
CELERY         ?= $(VENV)/bin/celery

export DJANGO_SETTINGS_MODULE = $(DJANGO_SETTINGS)

.DEFAULT_GOAL := help

# ---------- Helpers ----------
define _exists
	@if [ ! -x "$(1)" ]; then echo "⚠️  Missing $(1). Did you run 'make venv install'?"; exit 2; fi
endef

# ---------- Meta ----------
.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mAvailable targets\033[0m\n"} /^[a-zA-Z0-9_\-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo

# ---------- Environment ----------
.PHONY: venv
venv: ## Create virtualenv in .venv
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PIP) -q install --upgrade pip

.PHONY: install
install: venv ## Install Python deps and Git hooks
	$(call _exists,$(PIP))
	@$(PIP) install -r requirements.txt
	@$(PIP) install -r requirements-dev.txt 2>/dev/null || true
	@$(PRECOMMIT) install -t pre-commit -t pre-push || true
	@echo "✅ Dependencies installed."

.PHONY: envexample
envexample: ## Generate .env.example from .env
	$(call _exists,$(PY))
	@$(PY) scripts/make_env_example.py

# ---------- Django basics ----------
.PHONY: run dev
run dev: ## Run Django dev server (http://127.0.0.1:8000)
	$(call _exists,$(PY))
	@$(PY) manage.py runserver

.PHONY: check
check: ## Django system checks
	$(call _exists,$(PY))
	@$(PY) manage.py check

.PHONY: migrate
migrate: ## Apply database migrations
	$(call _exists,$(PY))
	@$(PY) manage.py migrate

.PHONY: makemigrations
makemigrations: ## Create new migrations
	$(call _exists,$(PY))
	@$(PY) manage.py makemigrations

.PHONY: superuser
superuser: ## Create a Django superuser
	$(call _exists,$(PY))
	@$(PY) manage.py createsuperuser

.PHONY: shell
shell: ## Django shell
	$(call _exists,$(PY))
	@$(PY) manage.py shell

.PHONY: collectstatic
collectstatic: ## Collect static files
	$(call _exists,$(PY))
	@$(PY) manage.py collectstatic --noinput

# ---------- Celery (optional) ----------
.PHONY: worker
worker: ## Start Celery worker
	$(call _exists,$(CELERY))
	@$(CELERY) -A $(APP) worker -l info

.PHONY: beat
beat: ## Start Celery beat scheduler
	$(call _exists,$(CELERY))
	@$(CELERY) -A $(APP) beat -l info

# ---------- Quality ----------
.PHONY: lint
lint: ## Run linters (ruff, black --check, isort --check)
	$(call _exists,$(RUFF))
	$(call _exists,$(BLACK))
	$(call _exists,$(ISORT))
	@$(RUFF) .
	@$(BLACK) --check .
	@$(ISORT) --check-only .

.PHONY: format
format: ## Auto-format (ruff --fix, black, isort)
	$(call _exists,$(RUFF))
	$(call _exists,$(BLACK))
	$(call _exists,$(ISORT))
	@$(RUFF) --fix .
	@$(BLACK) .
	@$(ISORT) .

.PHONY: precommit
precommit: ## Run pre-commit on all files
	$(call _exists,$(PRECOMMIT))
	@$(PRECOMMIT) run --all-files

# ---------- Testing ----------
.PHONY: test
test: ## Run Django tests
	$(call _exists,$(PY))
	@$(PY) manage.py test

# ---------- Utilities ----------
.PHONY: clean
clean: ## Remove caches and pyc files
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type f -name "*.py[co]" -delete
	@echo "🧹 Cleaned."

.PHONY: reset-sqlite
reset-sqlite: ## Danger: wipe sqlite DB and re-migrate (dev only)
	@if grep -q "sqlite3" <<< "$$(python - <<'PY'\nfrom algoresearch import settings\nprint(settings.DATABASES['default']['ENGINE'])\nPY)"; then \
		rm -f db.sqlite3; \
		$(PY) manage.py migrate; \
		echo "✅ Fresh sqlite DB created."; \
	else \
		echo "Refusing to reset: not using sqlite3."; \
	fi