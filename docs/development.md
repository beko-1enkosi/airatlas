# Development guide

## Prerequisites

- Git.
- Python 3.12 recommended for local development and used by CI.
- pip, normally included with Python.

The package currently allows Python 3.12 and newer. Future integrations may narrow that range. Check `python --version` before creating the environment.

## Local setup

Clone the repository and create a virtual environment to keep project tools separate from other Python projects:

```bash
git clone https://github.com/beko-1enkosi/airatlas.git
cd airatlas
python -m venv .venv
```

If `python` does not select Python 3.12, use `py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS, with Python 3.12 installed.

Activate the environment for your shell.

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS (bash or zsh):**

```bash
source .venv/bin/activate
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of `python` in subsequent commands without activating the environment.

From the repository root, install the project and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Editable installation links the environment to `src/airatlas`, so Python source edits are available without reinstalling. Rerun installation after changing project metadata or dependencies. The `[dev]` extra installs Ruff and pytest; httpx is the application HTTP dependency. `pyproject.toml` is the configuration source for packaging and these tools.

Run `deactivate` when finished if you activated the environment. Virtual environments, package metadata, and tool caches are ignored by Git. `.env.example` contains an empty OpenAQ key placeholder. Automated tests require no real credentials; live acquisition reads `OPENAQ_API_KEY` from the process environment and does not automatically load `.env` files.

## Code quality

Run commands from the repository root with the development environment active. Linting finds potential code-quality problems; formatting keeps Python code consistently styled.

```bash
# Check linting
python -m ruff check .

# Apply safe lint fixes; review the resulting changes
python -m ruff check . --fix

# Format Python code
python -m ruff format .

# Check formatting without modifying files
python -m ruff format --check .
```

Ruff targets Python 3.12, uses an 88-character line-length target, and prefers double quotes. Its rules cover core Python style/errors, unused imports and undefined names, import sorting, modern syntax, and common bug patterns.

## Testing

```bash
python -m pytest
```

pytest automatically discovers tests under `tests/` using the configuration in `pyproject.toml`. The suite covers package import, MVP configuration, discovery, historical/incremental windows, authentication, pagination, retries, and raw persistence. HTTP tests use mocks and storage tests use pytest temporary directories, never the real `data/raw/` directory. No live OpenAQ access is needed.

## M2 acquisition workflow

Set a real OpenAQ API key in your local process environment, using the placeholder below as a template. Never commit the key or share terminal output containing it.

**Windows PowerShell:**

```powershell
$env:OPENAQ_API_KEY = "<your-openaq-api-key>"
```

**Linux/macOS:**

```bash
export OPENAQ_API_KEY="<your-openaq-api-key>"
```

Inspect South African locations (terminal output only):

```bash
python scripts/discover_openaq_locations.py
```

Historical retrieval uses dates with the end strictly later than the start. For a one-day window:

```bash
python scripts/backfill_openaq_measurements.py --date-from 2026-09-01 --date-to 2026-09-02 --location-id 225448
```

Incremental retrieval requires an explicit previous checkpoint and a later timezone-aware timestamp:

```bash
python scripts/ingest_incremental_openaq.py --checkpoint 2026-09-01T00:00:00Z --datetime-to 2026-09-01T01:00:00Z --location-id 225448
```

These example windows are illustrative, not a guarantee of available observations. Both ingestion commands load `config/mvp_locations.json`, select PM2.5/PM10 using sensor metadata, and retrieve all pages. Omit `--location-id` to process all six stations; other station IDs are rejected. Date values are passed unchanged to OpenAQ, while incremental timestamps normalize to UTC.

Both commands now persist complete raw JSON batches beneath the repository's `data/raw/`, which is ignored by Git. Add `--output-dir <directory>` to choose another raw root, for example a temporary location for manual validation. Their terminal summaries report counts, batches written/reused, and output root, without dumping measurements.

Rerunning identical batches reuses their deterministic files. Different content at the same path raises a conflict and preserves the existing snapshot. Do not automatically delete or overwrite raw files to bypass a conflict. Complete empty responses are valid raw batches. Atomic publication requires a filesystem with hard-link support; file-level errors are surfaced and temporary files are cleaned up during normal exception handling.

Incremental persistence refuses unsafe runs, including missing required sensors or unresolved completeness. The next checkpoint is only a candidate, scoped to the queried locations; no durable checkpoint/state file is written. A future caller must advance state only after successful persistence. Inclusive boundaries and overlapping windows can repeat records; raw persistence preserves them rather than performing analytical deduplication.

## M2 outcome

AirAtlas now retrieves configured South African OpenAQ PM2.5/PM10 measurements with pagination and bounded retries, and preserves complete source batches as deterministic raw JSON. Weather integration, cleaning, transformations, analytical storage, orchestration, and serving remain future work.

## Continuous integration

The workflow in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) automatically runs on repository pushes, including feature branches, and pull requests. It uses an Ubuntu runner with Python 3.12 to:

1. Upgrade pip and install AirAtlas with `.[dev]`.
2. Check Ruff linting.
3. Validate Ruff formatting without changing files.
4. Run pytest using automatic discovery.

A failed installation or check fails the job. CI uses read-only repository permissions, requires no custom secrets, and performs no deployment. Review hosted results in the repository's Actions tab; local checks alone do not confirm a hosted run.

## Git workflow

Use Git incrementally with focused changes and clear Conventional Commit messages, such as `docs: clarify local setup` or `test: add validation cases`. Review `git diff` and run the relevant checks before committing.

Branches may be used for larger features, experiments, risky changes, or work that benefits from isolation. Small, low-risk maintenance or documentation changes may be committed directly to `main` when appropriate for this solo project; a new branch is not required for every small edit.

See the [architecture](architecture.md) for future system direction, or return to the [project overview](../README.md).
