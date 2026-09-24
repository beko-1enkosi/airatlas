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

Editable installation links the environment to `src/airatlas`, so Python source edits are available without reinstalling. Rerun installation after changing project metadata or dependencies. The `[dev]` extra installs Ruff, pytest, dbt Core and dbt-postgres; application dependencies include httpx for HTTP, Pandas for processing, PyArrow for Parquet, and Psycopg 3 for PostgreSQL. `pyproject.toml` is the configuration source for packaging and these tools.

Run `deactivate` when finished if you activated the environment. Virtual environments, package metadata, and tool caches are ignored by Git. `.env.example` contains an empty OpenAQ key placeholder and an example PostgreSQL URL. Automated tests require no real credentials; live acquisition reads `OPENAQ_API_KEY` from the process environment and does not automatically load `.env` files.

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

pytest automatically discovers tests under `tests/` using the configuration in `pyproject.toml`. The suite covers package import, MVP configuration, discovery, historical/incremental windows, authentication, pagination, retries, raw persistence, processing quality, and curated Parquet rebuilds. HTTP tests use mocks; data tests use pytest temporary directories, never the real repository data layers. Weather tests are also offline. Warehouse tests use temporary Parquet and fake Psycopg connections; the main suite needs no live APIs or PostgreSQL server.

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

AirAtlas now retrieves configured South African OpenAQ PM2.5/PM10 measurements with pagination and bounded retries, and preserves complete source batches as deterministic raw JSON. M3 extends these raw batches into processed and curated observations. M4 adds weather enrichment and PostgreSQL storage; orchestration and serving remain future work.

## M3 processing and curation workflow

After acquiring raw batches, run from the repository root:

```bash
python scripts/process_air_quality.py
python scripts/build_curated_air_quality.py
```

The first command reads immutable raw JSON, validates and normalizes observations, removes identical overlaps, and fails on conflicting source observations. Invalid records are excluded with counted reasons. It writes `data/processed/openaq/air_quality_observations.csv` and `quality_report.json`. Inspect rejection, duplicate, negative-value, and parameter/unit counts before analysis. Negative concentrations are retained; no unit conversion or scientific range policy is applied.

The second command reads that CSV and writes Parquet beneath `data/curated/openaq/air_quality/`, partitioned by `parameter` and `measurement_date_utc` (the UTC date of period end). UTC timestamp types and optional nulls are retained. `data/curated/openaq/air_quality_manifest.json` summarizes counts, time coverage, schema columns, and partitions. Duplicate processed observations fail rather than being silently removed again.

For temporary or custom locations:

```bash
python scripts/process_air_quality.py --raw-dir <raw-root> --output-dir <processed-root>
python scripts/build_curated_air_quality.py --input-file <processed-root>/openaq/air_quality_observations.csv --output-dir <curated-root>
```

Use separate raw, processed, and curated roots. The curation builder owns `<curated-root>/openaq/`; keep unrelated files outside that namespace. Both commands print summaries rather than full datasets. Neither needs an API key or network access.

Raw data stays unchanged. Processed CSV, quality reports, curated Parquet, and manifests under `data/` are generated and Git-ignored. Processed and curated outputs are rebuildable snapshots. A curation rebuild validates staged Parquet before replacing the dataset and manifest, so repeated builds do not append duplicate files or retain obsolete partitions. Run only one builder at a time; this is not a transactional store for concurrent readers. A process interruption during publication may require recovery from the retained backup directory.

No raw files causes a clear processing input error. Complete empty raw batches may produce a zero-row CSV; curation rejects empty input and preserves any previous snapshot. Check command success and the manifest before using an existing dataset after a failed rebuild.

**M3 outcome:** AirAtlas transforms immutable OpenAQ batches into validated, deduplicated observations, reports quality outcomes, and publishes an analysis-ready partitioned Parquet dataset. M3 is complete; M4 adds weather and warehouse capabilities below. Orchestration, APIs, and dashboards remain planned.

## M4 weather and warehouse workflow

First enrich the M3 curated air-quality dataset:

```bash
python scripts/enrich_air_quality_weather.py
```

Open-Meteo needs no API key. The command resolves each location's coordinates from curated observations or confirmed MVP configuration, requests only the required historical dates, and reuses valid raw cache files for identical requests. The current configuration contains no coordinates: missing curated coordinates must be resolved with confirmed metadata before enrichment can run. Do not guess or geocode station names.

Weather is matched to location and UTC period-end hour. Missing weather keeps the observation with null fields. The summary and `data/curated/open_meteo_air_quality/air_quality_weather_manifest.json` report match coverage. Use `--input-dir`, `--raw-weather-dir`, and `--output-dir` for custom roots. Original air-quality Parquet stays unchanged; raw weather JSON and enriched Parquet remain Git-ignored.

Install and start PostgreSQL separately, then create a database (for example, `airatlas`) and a role allowed to create the `airatlas` schema and own its tables/indexes. AirAtlas does not install PostgreSQL or create the database. For an existing AirAtlas schema, the loader role needs appropriate schema/table privileges, including SELECT, INSERT, DELETE and table locking. Rerun `python -m pip install -e ".[dev]"` to install Psycopg after updating dependencies.

Set the connection string in the process environment using placeholders:

**Windows PowerShell:**

```powershell
$env:AIRATLAS_DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/airatlas"
```

**Linux/macOS:**

```bash
export AIRATLAS_DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/airatlas"
```

Use your own local credentials, percent-encoding reserved characters in URL components when needed. Keep real secrets out of committed files, shared output and saved shell history. `.env.example` is a template; AirAtlas does not automatically read a private `.env`. The CLI never accepts a password argument or prints the DSN.

Load the warehouse:

```bash
python scripts/load_postgres_warehouse.py
# Optional alternate enriched input:
python scripts/load_postgres_warehouse.py --input-dir <enriched-parquet-directory>
```

The default input is `data/curated/open_meteo_air_quality/air_quality_weather/`. This is a **full refresh** of `airatlas.locations` and `airatlas.observations`, including rows from earlier loads that are absent in the new snapshot. It leaves unrelated tables alone and preserves files in all data layers. It creates missing AirAtlas structures, loads locations before observations, validates counts and constraints, and commits once. A failure rolls back. Repeat loads do not accumulate observations; the loader applies a narrow compatibility repair for the old non-null weather-hour constraint. Other incompatible schema definitions require explicit investigation, not automatic migrations.

Empty input, missing required columns, duplicate observation keys, conflicting non-null location metadata, and timestamps finer than PostgreSQL's microsecond precision fail clearly before connecting. Missing weather and optional source fields remain SQL nulls. An unmatched row may have a null weather hour or retain the aligned join hour. Matched weather requires `open_meteo` and a valid aligned hour; individual weather values may be null. Values without a weather source are rejected. The summary reports loaded locations/observations, pollutant counts, weather coverage, and earliest/latest boundaries.

Open [sql/example_queries.sql](../sql/example_queries.sql) in your PostgreSQL SQL client, or run `\i sql/example_queries.sql` from a connected `psql` session started at the repository root. The examples show latest observations, location averages, weather comparisons, and daily trends without combining different source units.

Automated tests use fake connections and do not prove a live database deployment. When `AIRATLAS_DATABASE_URL` points to a suitable development database, an optional smoke test can load a small enriched fixture twice and inspect counts and example queries. Remember that each run replaces the two AirAtlas tables; use a development database for fixtures.

**M4 outcome:** AirAtlas can enrich curated PM2.5 and PM10 observations with historical weather context and publish them into a queryable PostgreSQL warehouse. M4 is complete and its production loader has now been validated on local PostgreSQL 17 during M5, including repeat loading without duplicate accumulation. Scheduling, APIs, and dashboards remain future work.

## M5 dbt workflow

Activate the development environment and install `.[dev]` as above. dbt starts after the Python warehouse loader: first load the enriched Parquet snapshot using `AIRATLAS_DATABASE_URL`. dbt does not ingest files or replace the loader.

The committed `dbt/profiles.yml` reads separate connection components from the process environment. Point these at the same database as the loader. The loader's `AIRATLAS_DATABASE_URL` remains unchanged; dbt does not derive its settings from that URL or automatically read a private `.env` file.

| Variable | Meaning / default |
| --- | --- |
| `AIRATLAS_DB_HOST` | PostgreSQL host; default `localhost`. |
| `AIRATLAS_DB_PORT` | PostgreSQL port; default `5432`. |
| `AIRATLAS_DB_NAME` | Database; default `airatlas`. |
| `AIRATLAS_DB_USER` | Your database role; configure for live execution. |
| `AIRATLAS_DB_PASSWORD` | Role password; configure securely for live execution. |
| `AIRATLAS_DBT_SCHEMA` | Target prefix; default `airatlas_analytics`. |

PowerShell example (placeholders only; configure the real password securely in your local process environment):

```powershell
$env:AIRATLAS_DB_HOST = "localhost"
$env:AIRATLAS_DB_PORT = "5432"
$env:AIRATLAS_DB_NAME = "airatlas"
$env:AIRATLAS_DB_USER = "<database-role>"
$env:AIRATLAS_DB_PASSWORD = "<database-password>"
$env:AIRATLAS_DBT_SCHEMA = "airatlas_analytics"
```

On Linux/macOS, use `export VARIABLE="value"` for the same settings. Keep real credentials out of committed files, shared logs and saved shell history. The dbt role needs read access to `airatlas.locations` and `airatlas.observations`, plus permission to create/use its analytics schemas and rebuild its own models. Default model schemas end in `_staging`, `_intermediate` and `_marts`; dbt leaves source tables owned by the Python loader.

Run from the repository root:

```bash
dbt parse --project-dir dbt --profiles-dir dbt
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt
dbt docs generate --project-dir dbt --profiles-dir dbt
```

- **parse** validates project structure, configuration and model references without proving database execution. CI uses harmless connection placeholders for this step.
- **debug** checks configuration and the real PostgreSQL connection.
- **build** executes the staging/intermediate views, mart tables and data tests in dependency order. It requires a loaded source warehouse and replaces the derived marts; no incremental model state is used.
- **docs generate** queries database metadata and creates documentation/catalog artifacts. It does not host a documentation website.

The four marts and their grains are described in the [architecture guide](architecture.md#dbt-analytics). Use the mart examples in [sql/example_queries.sql](../sql/example_queries.sql) after building; adjust their schema prefix if you use a custom target. Preserve original source units, including Unicode units: replacement characters in a Windows terminal indicate a console-encoding problem and should not be written back into data.

`dbt/target/`, `dbt/logs/` and `dbt/dbt_packages/` are Git-ignored. Do not commit generated catalogs, raw/processed/curated datasets, temporary fixtures, database dumps or credentials.

**M5 validation and outcome:** The developer verified local PostgreSQL 17 using the production loader and a deterministic fixture: 2 locations, 6 observations, 5 weather matches and 1 unmatched row. A repeat refresh still contained 6 observations. `dbt debug`, `dbt build`, representative mart queries and `dbt docs generate` succeeded. The final build has **7 models, 2 sources and 89 data tests**, with **96 passes and no warnings, errors or skips**. The 89 tests intentionally allow nullable unmatched weather hours. These user-verified database results are separate from automated offline Python tests and CI parsing. M5 is complete; AirAtlas now publishes tested observation, daily, location and weather-context analytical models. No production/cloud deployment is implied.

## Continuous integration

The workflow in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) automatically runs on repository pushes, including feature branches, and pull requests. It uses an Ubuntu runner with Python 3.12 to:

1. Upgrade pip and install AirAtlas with `.[dev]`.
2. Check Ruff linting.
3. Validate Ruff formatting without changing files.
4. Run pytest using automatic discovery.
5. Parse dbt with harmless placeholders, without requiring PostgreSQL.

A failed installation or check fails the job. CI uses read-only repository permissions, requires no custom secrets, and performs no deployment. Review hosted results in the repository's Actions tab; local checks alone do not confirm a hosted run.

## Git workflow

Use Git incrementally with focused changes and clear Conventional Commit messages, such as `docs: clarify local setup` or `test: add validation cases`. Review `git diff` and run the relevant checks before committing.

Branches may be used for larger features, experiments, risky changes, or work that benefits from isolation. Small, low-risk maintenance or documentation changes may be committed directly to `main` when appropriate for this solo project; a new branch is not required for every small edit.

See the [architecture](architecture.md) for future system direction, or return to the [project overview](../README.md).
