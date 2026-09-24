# AirAtlas

AirAtlas is a Data Engineering portfolio project for building an end-to-end air-quality data platform using public environmental data. It acquires OpenAQ air-quality data, builds validated observations, adds historical Open-Meteo weather context, loads the enriched dataset into PostgreSQL, and builds tested dbt analytics marts.

## Problem statement

Air-quality and weather observations come from separate sources and can vary in format, completeness, and time resolution. Bringing them into a reliable, queryable pipeline with consistent, validated datasets will make it easier to explore environmental conditions and support repeatable analysis.

## Project goals

- Build a reproducible workflow from public source data to analysis-ready datasets.
- Preserve raw observations and document validation and cleaning decisions.
- Transform data into partitioned Parquet files and analytical database models.
- Develop practical skills in data quality, orchestration, testing, and documentation.
- Eventually serve curated data through an API and dashboard. These are output layers; Data Engineering is the core focus.

## Implemented pipeline

Airflow 3 orchestrates the existing scripts and dbt build; `airatlas.pipeline_runs` provides lightweight persistent run auditing.

```text
OpenAQ API v3
  -> South African location discovery
  -> 6 configured MVP monitoring locations
  -> PM2.5 + PM10 sensor discovery
  -> Historical / checkpoint-based incremental retrieval
  -> Pagination + bounded retries + rate-limit handling
  -> Immutable raw JSON
  -> Validation + normalization
  -> Deduplication + quality checks
  -> Processed CSV + quality report
  -> Curated partitioned Parquet
       + Open-Meteo historical weather -> immutable raw weather cache
  -> Location/hour weather enrichment
  -> Weather-enriched Parquet
  -> PostgreSQL analytical warehouse
  -> dbt sources -> staging views -> intermediate observation view
  -> Analytics marts
```

The approved stations are in [config/mvp_locations.json](config/mvp_locations.json). Raw JSON preserves source measurement objects with location, sensor, window, and retrieval provenance. Identical repeated batches are reused; conflicting content never silently replaces a snapshot.

## Planned architecture

```text
dbt analytics marts
  -> FastAPI / dashboard serving layer
```

M7 serving and dashboard work remain planned. See the [architecture document](docs/architecture.md) for current and future responsibilities.

## Repository structure

```text
AirAtlas/
|-- .github/workflows/ci.yml
|-- airflow/
|   |-- dags/airatlas_pipeline.py
|   `-- requirements.txt
|-- config/mvp_locations.json
|-- data/
|   |-- raw/.gitkeep
|   |-- processed/.gitkeep
|   `-- curated/.gitkeep
|-- dbt/
|   |-- dbt_project.yml
|   |-- profiles.yml
|   |-- models/
|   |   |-- staging/
|   |   |-- intermediate/
|   |   `-- marts/
|   `-- tests/
|-- docs/
|   |-- architecture.md
|   `-- development.md
|-- scripts/
|   |-- discover_openaq_locations.py
|   |-- backfill_openaq_measurements.py
|   |-- ingest_incremental_openaq.py
|   |-- process_air_quality.py
|   |-- build_curated_air_quality.py
|   |-- enrich_air_quality_weather.py
|   `-- load_postgres_warehouse.py
|-- sql/example_queries.sql
|-- src/airatlas/
|   |-- __init__.py
|   |-- ingestion/
|   |-- storage/
|   |-- processing/
|   |-- curation/
|   |-- weather/
|   |-- warehouse/
|   `-- orchestration/
|-- tests/
|-- .env.example
|-- .gitignore
|-- pyproject.toml
`-- README.md
```

`ingestion/` retrieves OpenAQ data; `storage/` preserves raw batches; `processing/` validates and deduplicates observations; `curation/` publishes Parquet; `weather/` retrieves and joins hourly weather; `warehouse/` loads PostgreSQL. `dbt/` contains source declarations, analytical models and SQL tests; `sql/` provides warehouse and mart query examples. `airflow/` contains the DAG and isolated runtime requirements; `orchestration/` coordinates commands and run audits. `scripts/` provides terminal entry points, and `tests/` covers the pipeline offline using temporary datasets. Generated data and local credentials are ignored by Git; the tree shows tracked placeholders, not generated datasets.

## Current status and milestones

**M1 — Foundation: complete**

**M2 — Data Acquisition: complete**

**M3 — Processing & Quality: complete**

**M4 — Weather & Warehouse: complete**

**M5 — Analytics with dbt: complete**

**M6 — Orchestration: complete**

M1 provides Python packaging, a development environment, Ruff, pytest, GitHub Actions CI, and documentation. M2 adds OpenAQ API v3 integration, South African location discovery, six approved MVP stations, PM2.5/PM10 historical backfill and incremental retrieval, automatic pagination, bounded retries, rate-limit handling, and deterministic raw JSON persistence.

AirAtlas can now discover South African OpenAQ sources, retrieve complete historical or incremental PM2.5/PM10 measurements for its configured stations, and preserve those source records in a raw data layer. Retrieval failures are surfaced rather than treated as complete. Incremental checkpoints are supplied explicitly and returned as candidates; durable checkpoint management is not implemented.

M3 adds raw JSON loading, a normalized observation schema, record validation and rejection reporting, duplicate removal and conflict detection, processed CSV and a quality report, and curated Parquet partitioned by pollutant and UTC measurement date. AirAtlas can now transform immutable raw batches into validated, deduplicated observations and publish an analysis-ready dataset. Source units and both measurement-period boundaries are retained; finite negative values are counted rather than scientifically classified or automatically removed.

M4 adds historical Open-Meteo ingestion with raw caching, temperature, relative humidity, precipitation and wind-speed enrichment by location and UTC hour, weather-enriched Parquet, and a PostgreSQL analytical warehouse. Transactional full refreshes, relational constraints, and analytical indexes support predictable repeat loads. AirAtlas can now enrich curated PM2.5/PM10 observations with historical weather context and publish a queryable warehouse. Coordinates must be present in curated observations or confirmed configuration; missing coordinates fail rather than being guessed.

M5 adds PostgreSQL source definitions, staging views, a reusable intermediate model with `has_weather_context`, and four table marts for observation-level, daily, location-level, and weather-context analysis. YAML model/column documentation and source/model tests protect required fields, relationships, pollutant values, natural keys, row counts, and aggregate grains. Pollutants and units stay separate; weather-unmatched observations remain valid fact rows.

The M5 completion gate was verified by the developer against **local PostgreSQL 17**: the production warehouse loader retained 6 observations across two identical refreshes, and `dbt debug`, `dbt build`, representative mart queries, and `dbt docs generate` succeeded. The build passed all **7 models and 89 data tests** (96 passes, no warnings, errors or skips). This also validates the M4 warehouse against a real development database; it is not a cloud/production deployment. See the [architecture validation summary](docs/architecture.md#local-postgresql-validation).

AirAtlas can now transform its PostgreSQL warehouse into tested, documented analytical dbt models for observation-level, daily, location-level and weather-context analysis.

M6 adds the `airatlas_pipeline` DAG, scheduled daily at midnight UTC with historical and incremental modes, `catchup=False`, and `max_active_runs=1`. Stages reuse existing production scripts, inherit environment-based secrets, and have one retry after five minutes; configuration validation has no retries. Upstream failures block downstream work. One audit row per DAG run records its requested window, optional location, status, stages, timestamps, available observation count and bounded safe error summary. Detailed task history and logs remain Airflow's responsibility.

The developer verified **Airflow 3.3.2 in WSL2**: DAG import validation passed, all seven tasks were discovered, and the complete pipeline executed successfully through acquisition, processing, curation, weather enrichment, PostgreSQL loading and dbt build. Pipeline auditing was also validated. This is user-verified local execution, not a production deployment.

## Development

Use **Python 3.12**. Follow the [development guide](docs/development.md) to clone the repository, create and activate a virtual environment, and understand the Git workflow. From the repository root with that environment active:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable installation uses the source in `src/airatlas`; `[dev]` adds Ruff, pytest, dbt Core and the PostgreSQL adapter. The [development guide](docs/development.md#m5-dbt-workflow) covers database configuration and dbt commands.

Airflow runs in a separate WSL2/Linux environment, not the Windows project `.venv`. See the [M6 workflow](docs/development.md#m6-airflow-workflow).

## Quality commands

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

GitHub Actions runs installation and these checks on pushes and pull requests using Ubuntu and Python 3.12. CI also parses the dbt project with harmless placeholders and no database connection. Parsing does not prove SQL execution; CI does not deploy the project.

## Roadmap

1. **Foundation (M1) - complete:** repository structure, development environment, Ruff, pytest, CI, and documentation.
2. **Data Acquisition (M2) - complete:** OpenAQ discovery, configured PM2.5/PM10 retrieval, API reliability, and raw JSON persistence. Historical weather enrichment is implemented in M4.
3. **Processing & Quality (M3) - complete:** normalized observations, validation, quality reporting, deduplication, conflict detection, processed CSV, and partitioned Parquet.
4. **Weather & Warehouse (M4) - complete:** historical weather enrichment and transactional PostgreSQL snapshot loading, validated locally on PostgreSQL 17.
5. **Analytics with dbt (M5) - complete:** sources, staging/intermediate views, four analytics marts, tests, generated dbt documentation, and real local PostgreSQL validation.
6. **Orchestration (M6) - complete:** daily/manual Airflow execution, stage retries and PostgreSQL run auditing, validated end to end in WSL2.
7. **Serving and presentation (M7, planned):** expose curated data through an API and dashboard, and document the completed platform.

APIs and dashboards remain future M7 work; no serving layer is implemented.
