# algoResearch

algoResearch is a Django application for research administration, grant applications,
research protocols, and team collaboration. This guide runs a separate development
installation on your own computer.

## Keep your installation independent

Use a **fresh database, fresh encryption keys, and your own account**. You do not need
access to the maintainer's database, accounts, cloud storage, email service, or API keys.
Use synthetic data when trying the application.

- Never copy someone else's `.env`, database backup, cookies, uploaded files, or credentials.
- Do not restore any database or Redis dumps found in this repository or its history.
- Keep `.env`, local databases, uploads, logs, and exports private. Review files before
  committing or sharing them; ignore rules do not protect files already tracked by Git.
- Keep the generated Django and Fernet keys for the lifetime of your local database.
  Replacing them can make existing encrypted messages unreadable.
- These instructions use development settings and bind the website to your computer's
  loopback interface. They are not instructions for a public production deployment.

**Repository data notice:** legacy backups, logs, and a script containing embedded
database credentials have been removed from the current tracked tree. They may still
exist in older commits or local copies. Exclusions do not remove Git history.
Maintainers must review historical data and rotate exposed credentials before
considering the repository safe to redistribute.

## Recommended setup: Docker

Works with Docker Desktop on macOS or Windows, or Docker Engine with the Compose
plugin on Linux. On Windows, run these commands in WSL2 with Docker integration enabled.
You also need Git and Python 3 to generate your private local configuration. The
application container uses Python 3.11 and includes its native PDF/image libraries.

### 1. Clone the project

```bash
git clone https://github.com/algoResearch/AlgoResearch-Dev.git
cd AlgoResearch-Dev
```

Run all remaining commands from this directory. Use a fresh terminal without inherited
production credentials or a production `DJANGO_SETTINGS_MODULE`.

### 2. Generate your local configuration

```bash
python3 scripts/init_local_env.py
```

This creates an ignored `.env` with randomly generated Django and Fernet keys. It
refuses to overwrite an existing `.env` and never reads the maintainer's configuration.
The script uses only Python's standard library. `.env.example` documents the options;
its placeholder keys are not usable credentials.

### 3. Start the application

```bash
docker compose up --build web
```

Leave this terminal running. Compose also starts PostgreSQL and Redis, applies
migrations, collects static assets, and serves HTTP and WebSockets with Daphne.
The first build can take several minutes.

- Website: <http://127.0.0.1:8000/>
- PostgreSQL and Redis are internal to the Compose network; no host ports are published.
- The database uses a new Docker volume. No backup import or production data sync is required.
- The bundled database credentials are for the isolated development container only.
- The background worker handles queued application tasks. The periodic `beat` scheduler
  is deliberately not included in the startup command.
- Development email is printed in the web terminal; it is not sent through SMTP.
  Optional AI/cloud integrations require your own credentials and may not work without them.
  Local development is not a network sandbox: explicitly using an integration can make
  outbound requests.

### 4. Create your own administrator

After the web server is ready, open a second terminal in the same directory. Start
the worker after the initial migrations finish, then create your account:

```bash
docker compose up -d worker
docker compose exec web python manage.py createsuperuser
```

Choose your own username, email, and password at the prompts. No shared account or
preset password is provided. Open <http://127.0.0.1:8000/it-admin-login/> and log in.
When prompted for an email verification code, find the development email in:

```bash
docker compose logs --tail=100 web
```

Those logs may contain login codes; do not publish them. Create your own test
organization and users through the administrator interface. A fresh database will not
contain the maintainer's organizations, grant submissions, or uploaded documents.

### 5. Verify and stop

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py migrate --check
docker compose ps
```

Open the login page to confirm the server responds. To stop the services while keeping
your database and uploaded files:

```bash
docker compose down
```

Start them again with `docker compose up web worker`. **Do not add `--volumes` / `-v`
to the stop command unless you intend to delete the local Docker data volumes.**

## Alternative: run Python locally

Use Python **3.11**, a dedicated local PostgreSQL database, and the native libraries
needed by psycopg2, Pillow, and WeasyPrint. Docker is the simpler option if those
libraries are not already installed. See [docker/Dockerfile](docker/Dockerfile) for
the Linux system dependencies used by the project. On Windows, use WSL2.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
python scripts/init_local_env.py
```

If you already generated `.env`, skip the last command. Create an empty database and a
local database role you control, then edit `.env` to add its connection string:

```dotenv
DEV_DATABASE_URL=postgres://YOUR_LOCAL_USER:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/algoresearch_local
```

Replace the placeholders; URL-encode special characters in database credentials.
**PostgreSQL is required for a fresh install:** historical migrations contain
PostgreSQL array fields, even though development settings offer a SQLite fallback.
Do not use a production connection string or restore a supplied backup.

```bash
export DJANGO_SETTINGS_MODULE=algoresearch.settings.dev
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
daphne -b 127.0.0.1 -p 8000 algoresearch.asgi:application
```

Use the administrator login URL above. Email verification messages appear in this
terminal. Stop Daphne with Ctrl+C. Reactivate the virtual environment, set
`DJANGO_SETTINGS_MODULE`, and run the Daphne command to restart it.

The generated configuration uses in-memory channels and runs Celery tasks inline for
this single-process setup, so a separate Redis server and worker are not required.
For multiple processes and background workers, use the Docker setup. Daphne does not
automatically reload Python changes; restart it after editing code. After changing
static assets, rerun `collectstatic`.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Invalid Fernet key | Generate `.env` with the setup script in a fresh checkout; do not use the example placeholder. Do not regenerate keys for an existing populated database. |
| Database connection refused | In Docker, check `docker compose ps` and `docker compose logs postgres`. Native installs need a running local PostgreSQL server and a valid `DEV_DATABASE_URL`. |
| Migration error involving an array or `[]` | You may be using the SQLite fallback. Configure a fresh PostgreSQL database. |
| Port 8000 already in use | Stop the other local server before starting this installation. |
| PDF/image library import errors | Prefer the Docker installation, which installs the native libraries. |
| Verification email never arrives | Development email is printed to the web server's terminal/logs, not delivered to your inbox. |
| Missing styles after an update | Run `docker compose exec web python manage.py collectstatic --noinput` (or the equivalent native command). |
| Optional integration unavailable | Supply your own integration credentials only if you intend to use that service. Never request or copy the maintainer's secrets. |

## Contributing safely

Use a branch and a pull request. Review `git status` and the staged diff before
committing. Share sanitized error messages rather than `.env`, database dumps, logs,
verification codes, or screenshots containing private data. Do not enable production
settings, cloud uploads, or scheduled imports merely to run the local application.

## Repository layout

| Directory | Contents |
| --- | --- |
| `algoresearch/` | Django settings, URLs, and server entry points |
| `dashboard/` | Main application, templates, migrations, and tests |
| `myapp/` | Shared application utilities and integrations |
| `static/` | Source assets, including vendor styles in `static/vendor/` |
| `docker/` | Docker build files, demo Compose file, and configuration templates |
| `scripts/` | Local setup and maintenance tools; Git hooks in `scripts/hooks/` |
| `docs/` | Diagrams, historical references, and the repository layout guide |
| `.github/` | GitHub workflows and repository ownership configuration |

Collected static files, uploads, logs, and backups are local artifacts, not source
folders. See [the layout guide](docs/repository-layout.md) for moved paths and commands.
