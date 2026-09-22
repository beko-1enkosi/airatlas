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

Python packaging, local development setup, and Ruff linting and formatting are available. The remaining tools are planned and have not been added. A dashboard technology has not been selected.

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
├── pyproject.toml
└── README.md
```

- `src/`: future Python application code, with a minimal `airatlas` package placeholder.
- `tests/`: future automated tests.
- `data/`: local datasets; `raw/` will hold source observations, `processed/` cleaned intermediate data, and `curated/` analysis-ready outputs. Generated datasets are excluded from Git.
- `docs/`: future design notes and project documentation.
- `scripts/`: future development and maintenance utilities.

The `.gitkeep` files preserve empty directories in Git. `.env.example` contains only commented configuration placeholders.

## Current status and milestone

**M1 — Foundation · Issue #3 — Configure Ruff**

The repository skeleton, Python package metadata, local development instructions, and Ruff configuration are in place. AirAtlas can be installed in editable mode with Ruff as a development dependency. The package remains a placeholder with no application logic or runtime dependencies. There is no pipeline, test suite, or CI yet; those belong to separate issues.

## Local Development Setup

Use **Python 3.12** for local development. The current package metadata allows Python 3.12 and newer; future integrations may narrow that range. Install Python and Git before starting.

1. Clone the repository into an `AirAtlas` directory:

   ```bash
   git clone https://github.com/beko-1enkosi/airatlas.git AirAtlas
   cd AirAtlas
   ```

2. Check your Python version and create an isolated environment for this project:

   ```bash
   python --version
   python -m venv .venv
   ```

   Make sure `python` selects Python 3.12. If it does not, use `py -3.12 -m venv .venv` on Windows or `python3.12 -m venv .venv` on Linux/macOS, with Python 3.12 installed.

3. Activate the environment using the command for your shell:

   **Windows PowerShell**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   **Linux/macOS (bash or zsh)**

   ```bash
   source .venv/bin/activate
   ```

   If PowerShell blocks activation, you can use `.\.venv\Scripts\python.exe` in place of `python` in the commands below without activating the environment.

4. Upgrade pip and install AirAtlas from the repository root:

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

   An editable installation links the environment to the code in `src/airatlas`, so edits to Python source files are available without reinstalling the package. Project metadata and dependency changes require running the install command again. The `[dev]` extra installs optional development tools, currently Ruff, alongside AirAtlas. No application dependencies are currently declared.

5. Verify the installation:

   ```bash
   python -c "import airatlas; print('AirAtlas package import successful')"
   ```

The `.venv/` directory and generated `*.egg-info/` package metadata stay local and are ignored by Git. Run `deactivate` when finished if you activated the environment. Testing and CI instructions will be added in later M1 issues.

## Code quality

With the development environment active, run these commands from the repository root. Ruff handles both linting, which finds potential code-quality problems, and formatting, which keeps Python code consistently styled. Its configuration in `pyproject.toml` targets Python 3.12, uses an 88-character line-length target, and prefers double quotes.

Check linting:

```bash
python -m ruff check .
```

Automatically fix safe lint issues:

```bash
python -m ruff check . --fix
```

Format Python code:

```bash
python -m ruff format .
```

Check formatting without changing files:

```bash
python -m ruff format --check .
```

Ruff's `.ruff_cache/` directory is generated locally and ignored by Git.

## Roadmap

1. **Foundation (M1):** repository initialization, development environment setup, and Ruff configuration are complete; testing and CI remain for separate issues.
2. **Data acquisition:** ingest public air-quality and weather observations and preserve raw data.
3. **Data processing:** validate, clean, transform, and store partitioned Parquet datasets.
4. **Analytical modeling:** load PostgreSQL and develop dbt models.
5. **Orchestration and quality:** schedule workflows with Airflow and expand automated checks.
6. **Serving and presentation:** expose curated data through an API and dashboard, and document the completed platform.

All roadmap work beyond repository initialization, development environment setup, and Ruff configuration is planned.
