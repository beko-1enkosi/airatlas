# AirAtlas architecture

## Purpose

AirAtlas will collect, process, store, transform, and serve public air-quality and weather data. Data Engineering is the core focus: the intended result is a reproducible path from source observations to reliable, queryable datasets. The API and dashboard will be serving/output layers.

**Status: planned architecture.** M1 provides the engineering foundation only; none of the data pipeline stages below are implemented.

## Planned data flow

```text
OpenAQ / public air-quality data + Open-Meteo weather data
                          |
                          v
                   Python ingestion
                          |
                          v
                    Raw data layer
                          |
                          v
                Validation and cleaning
                          |
                          v
                 Pandas transformations
                          |
                          v
                  Partitioned Parquet
                          |
                          v
                      PostgreSQL
                          |
                          v
                 dbt analytical models
                          |
                          v
                  FastAPI / dashboard

Apache Airflow will orchestrate the pipeline stages above.
```

Airflow will schedule and coordinate work; it is not a dataset storage or transformation layer. Source integrations, schemas, partition choices, and scheduling details will be defined in future implementation issues.

## Data layers

These directories currently contain only placeholders. Generated datasets are ignored by Git.

| Directory | Intended contents |
| --- | --- |
| `data/raw/` | Original source observations retained for traceability and reprocessing. |
| `data/processed/` | Validated, cleaned, and transformed intermediate datasets. |
| `data/curated/` | Analysis-ready datasets prepared for modeling and serving. |

## Planned technology stack

| Technology | Intended pipeline role |
| --- | --- |
| Python | Ingestion, validation, and processing code. Packaging exists; pipeline logic is planned. |
| Pandas | Tabular cleaning and transformations. |
| Parquet | Partitioned file storage for processed datasets. |
| PostgreSQL | Queryable analytical data storage. |
| dbt | SQL transformations and analytical models. |
| Apache Airflow | Workflow scheduling and orchestration. |
| FastAPI | API access to curated data. |

A dashboard is planned as an output layer; its technology has not been selected. No OpenAQ or Open-Meteo integration, transformation pipeline, Parquet output, database integration, dbt models, Airflow DAGs, API endpoints, or dashboard functionality exists yet.

## Current foundation tooling

- Python package under `src/airatlas/`, with setuptools packaging and editable installation.
- Ruff for linting and formatting, configured for Python 3.12.
- pytest with one package-import smoke test.
- GitHub Actions CI for installation, linting, formatting validation, and tests on pushes and pull requests.

## Architecture status

**M1 - Foundation: complete.** The repository now has the structure, development tools, checks, and documentation needed to begin pipeline work. Later milestones will implement the planned data flow incrementally.

See the [development guide](development.md) for setup and quality commands, or return to the [project overview](../README.md).
