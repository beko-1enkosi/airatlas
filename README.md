# AirAtlas

AirAtlas is a Data Engineering portfolio project for building an end-to-end air-quality data platform using public environmental data. It will initially work with sources such as OpenAQ air-quality data and Open-Meteo weather data.

## Problem statement

Air-quality and weather observations come from separate sources and can vary in format, completeness, and time resolution. Bringing them into a consistent, validated dataset will make it easier to explore environmental conditions and support repeatable analysis.

## Project goals

- Build a reproducible workflow from public source data to analysis-ready datasets.
- Preserve raw observations and document validation and cleaning decisions.
- Transform data into partitioned Parquet files and analytical database models.
- Develop practical skills in data quality, orchestration, testing, and documentation.
- Eventually serve curated data through an API and dashboard. These are output layers; Data Engineering is the core focus.

## Planned architecture

```text
Public air-quality and weather data
  → Python ingestion
  → Raw data storage
  → Validation and cleaning
  → Pandas transformations
  → Partitioned Parquet
  → PostgreSQL
  → dbt transformations
  → API / dashboard serving layer

Apache Airflow will orchestrate the pipeline stages.
```

This architecture is planned. No pipeline stages or integrations are implemented yet.

## Planned technology stack

| Technology | Intended role |
| --- | --- |
| Python | Ingestion, validation, and processing |
| Pandas | Tabular data transformations |
| Parquet | Partitioned file storage |
| PostgreSQL | Analytical data storage |
| dbt | SQL transformations and data models |
| Apache Airflow | Workflow scheduling and orchestration |
| FastAPI | Serving curated data through an API |
| pytest | Automated tests |
| Ruff | Python linting and formatting |
| GitHub Actions | Automated checks |

None of these tools are installed or configured by this initialization issue. A dashboard technology has not been selected.

## Repository structure

```text
AirAtlas/
├── src/
│   └── airatlas/
│       └── __init__.py
├── tests/
│   └── .gitkeep
├── data/
│   ├── raw/
│   │   └── .gitkeep
│   ├── processed/
│   │   └── .gitkeep
│   └── curated/
│       └── .gitkeep
├── docs/
│   └── .gitkeep
├── scripts/
│   └── .gitkeep
├── .env.example
├── .gitignore
└── README.md
```

- `src/`: future Python application code, with a minimal `airatlas` package placeholder.
- `tests/`: future automated tests.
- `data/`: local datasets; `raw/` will hold source observations, `processed/` cleaned intermediate data, and `curated/` analysis-ready outputs. Generated datasets are excluded from Git.
- `docs/`: future design notes and project documentation.
- `scripts/`: future development and maintenance utilities.

The `.gitkeep` files preserve empty directories in Git. `.env.example` contains only commented configuration placeholders.

## Current status and milestone

**M1 — Foundation · Issue #1 — Initialize repository**

The repository skeleton, README, ignore rules, and configuration placeholders are in place. There is no application logic, data, Python environment, dependency manifest, test suite, or automation yet. This issue completes repository initialization only; the rest of M1 remains ahead.

## Setup and development

Setup and development instructions will be added during M1. The next M1 issue will handle the Python environment and dependencies. There is currently nothing to install or run.

## Roadmap

1. **Foundation (M1):** initialize the repository, then establish the Python environment and development tooling in separate issues.
2. **Data acquisition:** ingest public air-quality and weather observations and preserve raw data.
3. **Data processing:** validate, clean, transform, and store partitioned Parquet datasets.
4. **Analytical modeling:** load PostgreSQL and develop dbt models.
5. **Orchestration and quality:** schedule workflows with Airflow and expand automated checks.
6. **Serving and presentation:** expose curated data through an API and dashboard, and document the completed platform.

All roadmap work beyond repository initialization is planned.
