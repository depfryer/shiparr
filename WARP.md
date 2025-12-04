# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development commands

### Environment setup

Use a local virtual environment and editable install with dev dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

Pytest is configured via `pyproject.toml` (`[tool.pytest.ini_options]`), so a plain `pytest` will run the full async test suite with coverage:

```bash
pytest
```

Common variants:

- Single test file:
  ```bash
  pytest tests/test_api.py
  ```
- Single test case:
  ```bash
  pytest tests/test_api.py::test_health_endpoint
  ```

### Linting

Ruff is configured in `pyproject.toml` (`[tool.ruff]`). Run it over the main code and tests:

```bash
ruff src tests
```

### Running the app locally

The service is a Quart app with configuration and data paths controlled by environment variables. A typical local run looks like:

```bash
export Shiparr_CONFIG_PATH=./config/projects
export Shiparr_DATA_PATH=./data
export SOPS_AGE_KEY_FILE=./secrets/age.key

python -m Shiparr.app
```

- `Shiparr_CONFIG_PATH` must point to the directory containing per-project YAML files.
- `Shiparr_DATA_PATH` is where the SQLite DB (`Shiparr.db`) will be created.
- `SOPS_AGE_KEY_FILE` is required if you use SOPS-encrypted env files.

### Docker / docker-compose

A basic container workflow using the provided `Dockerfile` and `docker-compose.yml`:

```bash
# Build image
docker build -t Shiparr:latest .

# Start stack (uses docker-compose.yml in repo root)
docker compose up -d

# Tail Shiparr logs
docker compose logs -f Shiparr
```

The `Shiparr` service in `docker-compose.yml` mounts:
- Docker socket (read-only) for managing other stacks
- `./config` as `/config` (configuration YAMLs)
- `./data` as `/data` (SQLite DB)
- `./secrets/age.key` as `/secrets/age.key` (SOPS/age key)
- `./deployments` as `/deployments` (cloned repositories and compose projects)

## High-level architecture

### Runtime overview

- The main entrypoint is `src/Shiparr/app.py`.
  - `create_app()` builds a Quart application, loads settings from environment via `Settings` (see `config.py`), initializes the async SQLite database, loads project configuration from YAML files, synchronizes that configuration into the database, and wires the notification system.
  - `main()` uses those settings (notably the HTTP port) and runs the Quart app; this is what `python -m Shiparr.app` invokes.
- Quart startup lifecycle hooks (`before_serving` / `after_serving`) are used to:
  - Initialize the async engine and session factory
  - Load and validate YAML project config into a `LoadedConfig` instance
  - Sync `projects` and `repositories` tables against the YAML config
  - Create a `NotificationManager` bound to both the loaded config and DB session factory
  - Dispose the async engine cleanly on shutdown
- All HTTP routes are registered via a single blueprint created in `src/Shiparr/routes/__init__.py` and attached to the app in `create_app()`.

### Configuration model

Configuration concerns are centralized in `src/Shiparr/config.py`:

- `Settings` (`pydantic_settings.BaseSettings`) encapsulates global service configuration, populated from environment variables with `Shiparr_` prefix (plus `GITHUB_TOKEN` as a special case). It defines:
  - `config_path` (where project YAMLs live)
  - `data_path` (where SQLite DB lives)
  - HTTP port and logging level
  - Optional Basic Auth credentials and toggle
  - Optional SOPS/age key path and default GitHub token
- `RepositoryConfig` and `ProjectConfig` (`pydantic.BaseModel`) define the schema for a project file under `config/projects/`:
  - `ProjectConfig.repositories` is a mapping keyed by repo name; a validator injects that key into each `RepositoryConfig.name` so YAML remains concise.
  - Both project-level `tokens` and per-repository `notifications`/`global_notifications` are modeled here.
- `ConfigLoader` is the orchestrator for reading and validating configuration:
  - Reads all `*.yml`/`*.yaml` files from `settings.config_path`.
  - Performs `${VAR}` interpolation against `os.environ` before YAML parsing.
  - Validates each file into a `ProjectConfig` and enforces uniqueness of project names.
  - Returns a `LoadedConfig` aggregating `Settings` plus a mapping of project name → `ProjectConfig`.

At runtime, the loaded configuration is stored in `app.config["Shiparr_CONFIG"]` for use by other components (notably notifications and any future scheduler integration).

### Persistence and domain model

Persistent data lives in an async SQLite database managed by `src/Shiparr/database.py` and `src/Shiparr/models.py`:

- `database.py`:
  - Builds an async engine using `sqlite+aiosqlite:///…` URLs with automatic directory creation.
  - Enables WAL mode for better concurrent write performance.
  - Exposes a global `async_session_factory` (`async_sessionmaker[AsyncSession]`) used across the app.
  - Provides `init_db()` to import models and create tables, `get_session()` as an async generator for request-scoped sessions, and `dispose_engine()` for cleanup.
- `models.py` defines three core tables via SQLAlchemy 2.0 declarative ORM:
  - `Project`: identified by unique `name`, linked to the YAML config file and creation timestamp.
  - `Repository`: belongs to a `Project` and captures Git metadata (`git_url`, `branch`, `path`, `local_path`, `last_commit_hash`, `check_interval`).
  - `Deployment`: belongs to a `Repository` and records each deployment attempt (`status`, `commit_hash`, timestamps, and aggregated logs).

The `_sync_config_to_db()` function in `app.py` keeps the database aligned with configuration files by:
- Creating `Project` rows for new project YAMLs
- Upserting `Repository` rows for each configured repository
- Deleting repositories that were removed from configuration

### Deployment pipeline

Deployment orchestration is implemented primarily in `src/Shiparr/deployer.py`, with support from `git_manager.py` and `sops_manager.py`:

- `git_manager.GitManager` wraps GitPython in an async-friendly interface (`asyncio.to_thread`):
  - Constructs authenticated clone URLs when a token is provided.
  - Provides `clone`, `get_local_hash`, `get_remote_hash`, `pull`, and `has_changes` helpers.
- `sops_manager.SopsManager` integrates with the `sops` CLI to decrypt encrypted environment files:
  - `decrypt_file()` runs `sops -d` and writes the decrypted content to a target path (e.g. `.env`).
  - `is_sops_file()` uses a lightweight heuristic to detect SOPS-encrypted files.
- `deployer.Deployer` coordinates the end-to-end deployment for a single repository ID, using an `AsyncSession` and an optional `NotificationManager`:
  - Looks up the target `Repository` from the DB.
  - Creates a `Deployment` row in `pending` state.
  - If there is a recorded `last_commit_hash`, compares it with the remote hash; in the no-change case it marks the deployment as `success` with a "No changes" message and returns early.
  - Ensures the local repository directory exists, then calls `GitManager.pull()` (handling initial clone vs. update implicitly) and updates `Repository.last_commit_hash`.
  - Determines the working directory from `repository.path`, optionally decrypts an `env_file` into `.env` via `SopsManager.decrypt_file()`, and records this step in the deployment logs.
  - Runs `docker compose -f docker-compose.yml up -d` via `asyncio.create_subprocess_exec`, capturing stdout/stderr into the deployment logs.
  - On success: marks the deployment as `success`, commits the session, and triggers `NotificationManager.notify_for_deployment("success", …)` if configured.
  - On failure (including Docker and orchestration errors): marks the deployment as `failed`, commits, and triggers failure notifications.

### Scheduling and background checks

`src/Shiparr/scheduler.py` defines `DeploymentScheduler`, a thin wrapper around APScheduler's `AsyncIOScheduler`:

- It schedules periodic jobs per repository using `IntervalTrigger` with the repository's `check_interval`.
- Each job calls a provided coroutine (typically `Deployer.deploy`) with the repository ID.
- Jobs are named `repo_{repository_id}` to allow rescheduling / replacement.

At present, the scheduler is defined but not yet wired into `create_app()`; future work is expected to hook it into the Quart lifecycle to continuously poll and deploy repositories.

### API surface and authentication

HTTP routes live under `src/Shiparr/routes/` and are registered via a shared blueprint:

- `routes/api.py` exposes the core REST API:
  - Healthcheck endpoint (`/api/health`).
  - Project listing and detail endpoints.
  - Per-project repository listing.
  - Repository detail and deployment history endpoints.
  - A POST endpoint to trigger a deployment for a given repository (`/api/repositories/<id>/deploy`).
  - Deployment detail and logs endpoints.
- `routes/dashy.py` defines `/widget/dashy`, which aggregates per-repository status for a given project into a JSON shape suitable for Dashy custom widgets.
- `routes/logs.py` provides `/containers/<container_id>/logs`, proxying Docker container logs (tail length via `tail` query parameter).

Authentication is implemented as a reusable decorator in `src/Shiparr/auth.py`:

- `require_basic_auth` inspects `Shiparr_SETTINGS` attached to the Quart app for `auth_enabled`, username, and password.
- When enabled, it enforces HTTP Basic Auth on decorated endpoints, except for `/api/health` which is explicitly bypassed.
- The decorator is applied at the route level in the `routes` modules, so behavior is uniform across API, Dashy, and logs endpoints.

### Notification system

`src/Shiparr/notifications.py` integrates with the Shoutrrr CLI to send deployment event notifications:

- `NotificationManager` is initialized at startup with the loaded configuration (`LoadedConfig`) and the async session factory.
- For a given `Deployment`, `notify_for_deployment()`:
  - Resolves the associated `Repository` and `Project` from the DB.
  - Looks up configured notification URLs at both repository and project level (`notifications[event]` and `global_notifications[event]`).
  - If any URLs are found, calls `notify()` to send messages via `shoutrrr send -u … -m …` using `asyncio.create_subprocess_exec`.
- `format_message()` produces a concise, machine-readable text message including deployment ID, status, repository ID, and duration.

### Design and reference documentation

The file `Shiparr-guide.md` serves as an extended design document for this project. It contains:

- A more exhaustive architecture overview and data model description.
- The canonical configuration format for project YAML files and environment variables.
- Detailed REST API endpoint reference and Dashy widget schema.
- Additional operational notes (Docker image expectations, testing structure, and future roadmap).

When implementing larger changes or new features, consult `Shiparr-guide.md` alongside this `WARP.md` to ensure behavior remains consistent with the intended design.