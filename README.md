# AirAtlas

AirAtlas is a Data Engineering portfolio project for building an end-to-end air-quality data platform using public environmental data. It will initially work with sources such as OpenAQ air-quality data and Open-Meteo weather data.

## Problem statement

Air-quality and weather observations come from separate sources and can vary in format, completeness, and time resolution. Bringing them into a reliable, queryable pipeline with consistent, validated datasets will make it easier to explore environmental conditions and support repeatable analysis.

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

This architecture is planned. No pipeline stages or integrations are implemented yet. See the [architecture document](docs/architecture.md) for data layers and intended technology roles.

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

Current foundation tooling includes Python packaging, Ruff linting and formatting, pytest, and GitHub Actions CI. The pipeline roles above are planned. A dashboard technology has not been selected.

## Repository structure

```text
AirAtlas/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── airatlas/
│       └── __init__.py
├── tests/
│   └── test_package.py
├── data/
│   ├── raw/
│   │   └── .gitkeep
│   ├── processed/
│   │   └── .gitkeep
│   └── curated/
│       └── .gitkeep
├── docs/
│   ├── architecture.md
│   └── development.md
├── scripts/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

- `.github/workflows/`: GitHub Actions CI configuration.
- `src/`: future Python application code, with a minimal `airatlas` package placeholder.
- `tests/`: automated tests, currently one package-import smoke test.
- `data/`: local datasets; `raw/` will hold source observations, `processed/` cleaned intermediate data, and `curated/` analysis-ready outputs. Generated datasets are excluded from Git.
- `docs/`: planned architecture and development instructions.
- `scripts/`: future development and maintenance utilities.

The `.gitkeep` files preserve empty directories in Git. `.env.example` contains only commented configuration placeholders.

## Current status and milestone

**M1 — Foundation: complete**

The foundation includes the Python `src/` project structure, setuptools packaging, editable development environment, Ruff linting and formatting, pytest with a package-import smoke test, GitHub Actions CI, and project documentation.

The package remains a placeholder with no application logic or runtime dependencies. Ingestion, source integrations, transformations, Parquet output, PostgreSQL, dbt, Airflow, FastAPI, and the dashboard are planned for later milestones.

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
2. **Data acquisition:** ingest public air-quality and weather observations and preserve raw data.
3. **Data processing:** validate, clean, transform, and store partitioned Parquet datasets.
4. **Analytical modeling:** load PostgreSQL and develop dbt models.
5. **Orchestration and quality:** schedule workflows with Airflow and expand automated checks.
6. **Serving and presentation:** expose curated data through an API and dashboard, and document the completed platform.

All roadmap work after M1 is planned and has not yet been implemented.
