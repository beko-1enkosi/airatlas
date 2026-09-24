# AirAtlas

AirAtlas is an end-to-end **Data Engineering air-quality platform** built with public environmental data. It collects air-quality observations from OpenAQ, enriches them with historical weather from Open-Meteo, stores the result in PostgreSQL, transforms it with dbt, and orchestrates the full pipeline with Apache Airflow.

The project focuses on **PM2.5** and **PM10** measurements from South African monitoring locations.

## What AirAtlas does

- Collects PM2.5 and PM10 measurements from the OpenAQ API
- Preserves immutable raw API responses as JSON
- Validates, normalizes, deduplicates, and quality-checks observations
- Publishes processed CSV and partitioned Parquet datasets
- Adds temperature, humidity, precipitation, and wind context from Open-Meteo
- Loads enriched observations into PostgreSQL
- Builds tested analytical models with dbt
- Orchestrates the full workflow with Apache Airflow
- Records lightweight pipeline-run audit information in PostgreSQL

## Pipeline

```text
OpenAQ API
    ↓
Raw JSON
    ↓
Validation + normalization
    ↓
Processed CSV
    ↓
Curated Parquet
    ↓
Open-Meteo weather enrichment
    ↓
Weather-enriched Parquet
    ↓
PostgreSQL warehouse
    ↓
dbt staging
    ↓
dbt intermediate model
    ↓
Analytics marts
```

Apache Airflow orchestrates these stages in order:

```text
validate_run_config
        ↓
acquire_air_quality
        ↓
process_air_quality
        ↓
build_curated_air_quality
        ↓
enrich_air_quality_weather
        ↓
load_postgres_warehouse
        ↓
build_dbt_analytics
```

## Data layers

| Layer | Purpose |
| --- | --- |
| Raw | Immutable source responses from OpenAQ and Open-Meteo |
| Processed | Validated, normalized, deduplicated observations |
| Curated | Partitioned Parquet prepared for analytical use |
| Warehouse | Queryable PostgreSQL tables with air-quality and weather context |
| Analytics | Tested dbt models and marts for reporting and analysis |

## PostgreSQL warehouse

AirAtlas stores its main analytical data in:

```text
airatlas.locations
airatlas.observations
airatlas.pipeline_runs
```

`locations` stores monitoring-location metadata.

`observations` stores PM2.5 and PM10 measurements together with optional weather context.

`pipeline_runs` stores one lightweight audit record per Airflow DAG run, including the requested time window, run status, current or failed stage, timestamps, and observation count where available.

Weather context is optional. An air-quality observation remains valid even when no matching weather record exists.

## dbt analytics

dbt transforms the PostgreSQL warehouse into reusable analytical models.

```text
sources
   ↓
staging
   ↓
intermediate
   ↓
marts
```

The main marts are:

```text
fct_air_quality_observations
agg_daily_air_quality
agg_location_air_quality
agg_pollution_weather
```

PM2.5 and PM10 remain separate throughout the analytical layer, and measurement units are preserved.

## Technology stack

- **Python** — ingestion, processing, validation, enrichment, and loading
- **OpenAQ API** — air-quality observations
- **Open-Meteo API** — historical weather context
- **Pandas / PyArrow** — transformation and Parquet publishing
- **PostgreSQL** — analytical warehouse
- **dbt** — analytical transformations and data tests
- **Apache Airflow** — orchestration, scheduling, retries, and failure propagation
- **pytest** — automated testing
- **Ruff** — linting and formatting
- **GitHub Actions** — continuous integration

## Repository structure

```text
AirAtlas/
├── airflow/
│   └── dags/
├── config/
├── data/
│   ├── raw/
│   ├── processed/
│   └── curated/
├── dbt/
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   └── tests/
├── docs/
├── scripts/
├── sql/
├── src/airatlas/
│   ├── ingestion/
│   ├── storage/
│   ├── processing/
│   ├── curation/
│   ├── weather/
│   ├── warehouse/
│   └── orchestration/
└── tests/
```

## Key design decisions

**Raw data is preserved.** Original API responses are kept so transformed datasets can be rebuilt and traced back to their source.

**Duplicates are controlled.** AirAtlas uses a natural observation key based on location, sensor, pollutant, and UTC measurement period.

**Weather is contextual, not required.** Missing weather does not remove a valid air-quality observation.

**Parquet is used for analytics-ready files.** Curated observations are partitioned for efficient analytical reads.

**PostgreSQL is the warehouse.** Relational constraints, indexes, and transactional refreshes protect warehouse consistency.

**dbt owns analytical transformations.** Aggregation logic is kept in tested warehouse models instead of being duplicated elsewhere.

**Airflow orchestrates existing production scripts.** Pipeline logic remains in the existing Python components while Airflow controls order, retries, scheduling, and failures.

## Development

Create and activate the project environment, then install the package:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the quality checks:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Run the dbt project:

```bash
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt
```

Airflow is run from a separate Linux/WSL2 environment rather than the Windows project virtual environment.

## Demo summary

AirAtlas demonstrates a complete Data Engineering workflow:

```text
public APIs
→ ingestion
→ raw storage
→ data quality
→ transformation
→ Parquet
→ weather enrichment
→ PostgreSQL
→ dbt analytics
→ Airflow orchestration
```

The goal is not only to display environmental data, but to build a reliable, reproducible pipeline that turns public source data into tested, queryable analytical datasets.
