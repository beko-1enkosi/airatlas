# AirAtlas

AirAtlas is a Data Engineering portfolio project for building an end-to-end air-quality data platform using public environmental data. It acquires OpenAQ air-quality data, builds validated observations, adds historical Open-Meteo weather context, and loads the enriched dataset into PostgreSQL.

## Problem statement

Air-quality and weather observations come from separate sources and can vary in format, completeness, and time resolution. Bringing them into a reliable, queryable pipeline with consistent, validated datasets will make it easier to explore environmental conditions and support repeatable analysis.

## Project goals

- Build a reproducible workflow from public source data to analysis-ready datasets.
- Preserve raw observations and document validation and cleaning decisions.
- Transform data into partitioned Parquet files and analytical database models.
- Develop practical skills in data quality, orchestration, testing, and documentation.
- Eventually serve curated data through an API and dashboard. These are output layers; Data Engineering is the core focus.

## Implemented pipeline

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
```

The approved stations are in [config/mvp_locations.json](config/mvp_locations.json). Raw JSON preserves source measurement objects with location, sensor, window, and retrieval provenance. Identical repeated batches are reused; conflicting content never silently replaces a snapshot.

## Planned architecture

```text
PostgreSQL warehouse
  -> dbt analytical models
  -> FastAPI / dashboard serving layer

Apache Airflow will orchestrate pipeline stages.
```

dbt analytical modeling, orchestration, and serving remain planned. See the [architecture document](docs/architecture.md) for current and future responsibilities.

## Repository structure

```text
AirAtlas/
|-- .github/workflows/ci.yml
|-- config/mvp_locations.json
|-- data/
|   |-- raw/.gitkeep
|   |-- processed/.gitkeep
|   `-- curated/.gitkeep
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
|   `-- warehouse/
|-- tests/
|-- .env.example
|-- .gitignore
|-- pyproject.toml
`-- README.md
```

`ingestion/` retrieves OpenAQ data; `storage/` preserves raw batches; `processing/` validates and deduplicates observations; `curation/` publishes Parquet; `weather/` retrieves and joins hourly weather; `warehouse/` loads PostgreSQL. `scripts/` provides terminal entry points, and `tests/` covers the pipeline offline using temporary datasets. Generated data and local credentials are ignored by Git; the tree shows tracked placeholders, not generated datasets.

## Current status and milestones

**M1 — Foundation: complete**

**M2 — Data Acquisition: complete**

**M3 — Processing & Quality: complete**

**M4 — Weather & Warehouse: complete**

M1 provides Python packaging, a development environment, Ruff, pytest, GitHub Actions CI, and documentation. M2 adds OpenAQ API v3 integration, South African location discovery, six approved MVP stations, PM2.5/PM10 historical backfill and incremental retrieval, automatic pagination, bounded retries, rate-limit handling, and deterministic raw JSON persistence.

AirAtlas can now discover South African OpenAQ sources, retrieve complete historical or incremental PM2.5/PM10 measurements for its configured stations, and preserve those source records in a raw data layer. Retrieval failures are surfaced rather than treated as complete. Incremental checkpoints are supplied explicitly and returned as candidates; durable checkpoint management is not implemented.

M3 adds raw JSON loading, a normalized observation schema, record validation and rejection reporting, duplicate removal and conflict detection, processed CSV and a quality report, and curated Parquet partitioned by pollutant and UTC measurement date. AirAtlas can now transform immutable raw batches into validated, deduplicated observations and publish an analysis-ready dataset. Source units and both measurement-period boundaries are retained; finite negative values are counted rather than scientifically classified or automatically removed.

M4 adds historical Open-Meteo ingestion with raw caching, temperature, relative humidity, precipitation and wind-speed enrichment by location and UTC hour, weather-enriched Parquet, and a PostgreSQL analytical warehouse. Transactional full refreshes, relational constraints, and analytical indexes support predictable repeat loads. AirAtlas can now enrich curated PM2.5/PM10 observations with historical weather context and publish a queryable warehouse. Coordinates must be present in curated observations or confirmed configuration; missing coordinates fail rather than being guessed.

## Development

Use **Python 3.12**. Follow the [development guide](docs/development.md) to clone the repository, create and activate a virtual environment, and understand the Git workflow. From the repository root with that environment active:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable installation uses the source in `src/airatlas`; `[dev]` adds Ruff and pytest.

## Quality commands

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

GitHub Actions runs installation and these checks on pushes and pull requests using Ubuntu and Python 3.12. CI validates code quality and tests; it does not deploy the project.

## Roadmap

1. **Foundation (M1) - complete:** repository structure, development environment, Ruff, pytest, CI, and documentation.
2. **Data Acquisition (M2) - complete:** OpenAQ discovery, configured PM2.5/PM10 retrieval, API reliability, and raw JSON persistence. Historical weather enrichment is implemented in M4.
3. **Processing & Quality (M3) - complete:** normalized observations, validation, quality reporting, deduplication, conflict detection, processed CSV, and partitioned Parquet.
4. **Weather & Warehouse (M4) - complete:** historical weather enrichment and transactional PostgreSQL snapshot loading. dbt modeling remains planned.
5. **Orchestration and quality:** schedule workflows with Airflow and expand automated checks.
6. **Serving and presentation:** expose curated data through an API and dashboard, and document the completed platform.

dbt modeling, orchestration, APIs, and dashboards remain planned; no M5/later functionality is implemented.
