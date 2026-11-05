# AirAtlas

**A clearer picture of the air we share.**

An end-to-end data engineering platform exploring air quality across South Africa through reliable data pipelines, historical weather context, interactive visualisations, and an AI-powered guide.

![AirAtlas landing page](docs/images/airatlas-landing.png)

**[Explore the live dashboard](https://airatlas-three.vercel.app/)** · **[Explore the public API](https://airatlas-api.vercel.app/docs)** · **[View the source code](https://github.com/beko-1enkosi/airatlas)**

## Overview

AirAtlas turns public environmental observations into structured, tested, and accessible information. It ingests air-quality measurements from [OpenAQ](https://openaq.org/), validates and transforms them, enriches the results with historical weather data from [Open-Meteo](https://open-meteo.com/), and publishes analytics through a PostgreSQL warehouse and a responsive dashboard.

The interface makes it easier to explore monitoring locations, compare particulate-matter measurements, examine historical trends, and understand the data with **Ask Air**, a friendly AI assistant.

The engineering pipeline is the foundation; the dashboard and assistant are ways to make its outputs useful.

## Data at a glance

| Metric | Historical warehouse snapshot |
| --- | ---: |
| Air-quality observations | **5,093** |
| Monitoring locations | **6** |
| PM2.5 observations | **2,234** |
| PM10 observations | **2,859** |
| Observations with matched weather context | **100%** |
| Recorded observation period | **26 March 2019 – 1 November 2026 (UTC)** |

These figures describe the loaded dataset at the time of the snapshot. Coverage is **not continuous** across the date range, and the stations do **not** all report during the same periods. The latest stored observation should not be interpreted as a live air-quality reading.

## Features

- **End-to-end ingestion:** Collects PM2.5 and PM10 measurements from OpenAQ and preserves source responses as raw JSON.
- **Data quality:** Normalises timestamps and units, validates measurements, handles duplicates, and reports processing outcomes.
- **Analytics-ready storage:** Produces validated CSV files and partitioned Parquet datasets.
- **Weather enrichment:** Matches air-quality observations with historical temperature, relative humidity, precipitation, and wind information from Open-Meteo.
- **PostgreSQL warehouse:** Stores locations and observations, including optional weather context, with transactional loading.
- **dbt analytics:** Builds tested staging, intermediate, and mart models for trends, comparisons, and weather context.
- **Interactive dashboard:** Provides overview metrics, a monitoring-location map, historical trend charts, location comparisons, weather context, and data-health information.
- **Ask Air:** Uses OpenRouter to explain air quality and answer questions using carefully selected, read-only AirAtlas data. Responses are designed to be accessible and beginner-friendly.
- **Quality and orchestration:** Includes an Apache Airflow DAG, automated Python tests, frontend tests, Ruff checks, and GitHub Actions CI.

## Architecture

```mermaid
flowchart TD
    A[OpenAQ API] --> B[Raw JSON]
    B --> C[Validation and processing]
    C --> D[Curated Parquet]
    W[Open-Meteo historical weather] --> E[Weather enrichment]
    D --> E
    E --> F[(Neon PostgreSQL)]
    F --> G[dbt analytical models]
    G --> H[FastAPI]
    H --> I[React dashboard on Vercel]
    I -->|Ask Air questions| H
    H -->|Bounded contextual requests| J[OpenRouter]
```

The pipeline is implemented as reusable Python stages. **Apache Airflow** defines their execution order and captures pipeline-run audit information. The cloud-hosted API is read-only; it serves the warehouse but does not run the ingestion pipeline on every request.

## Data engineering workflow

| Stage | Responsibility |
| --- | --- |
| Ingest | Retrieve OpenAQ measurements and preserve raw API responses. |
| Process | Validate, normalise, deduplicate, and publish structured observations. |
| Curate | Write analytics-ready, partitioned Parquet files. |
| Enrich | Match historical Open-Meteo observations by location and time. |
| Load | Transactionally load curated observations and location metadata into PostgreSQL. |
| Model | Use dbt to construct and test analytical datasets. |
| Serve | Expose a read-only FastAPI and an interactive React dashboard. |

The main warehouse tables are `airatlas.locations`, `airatlas.observations`, and `airatlas.pipeline_runs`.

Key dbt marts include:

- `fct_air_quality_observations`
- `agg_daily_air_quality`
- `agg_location_air_quality`
- `agg_pollution_weather`

Analytical queries keep **PM2.5 and PM10 separate**, preserve measurement units, and use observation-weighted aggregation where appropriate.

## Ask Air

Ask Air is a conversational guide embedded in the dashboard. It can explain concepts such as PM2.5, PM10, historical readings, weather coverage, and the monitoring locations included in AirAtlas.

Questions are sent to a **FastAPI endpoint**, which selects a limited amount of relevant warehouse context and calls **OpenRouter** from the server. The OpenRouter API key is never shipped to the browser. Responses are rendered as safe Markdown; user questions are handled as plain text.

Ask Air does not generate SQL or have permission to change warehouse data. Its answers depend on the available historical snapshot and the configured AI provider. Users should avoid submitting personal or sensitive information. Public availability requires the backend's OpenRouter configuration.

## Technology stack

| Area | Technologies |
| --- | --- |
| Data acquisition | Python, OpenAQ API, Open-Meteo API, HTTPX |
| Processing and storage | Pandas, PyArrow, CSV, JSON, Parquet |
| Database and modelling | PostgreSQL, Neon, SQL, dbt |
| Orchestration | Apache Airflow |
| Backend | FastAPI, Pydantic, Psycopg, Uvicorn |
| Frontend | React, Vite, Recharts, Leaflet |
| AI integration | OpenRouter |
| Testing and CI | pytest, Ruff, Node test runner, GitHub Actions |
| Deployment | Vercel (frontend and API), Neon (database) |

## Project structure

```text
airatlas/
├── app.py                      # Vercel FastAPI entry point
├── airflow/dags/               # Pipeline orchestration
├── config/                     # Pipeline configuration
├── data/                       # Local raw and processed data (not committed)
├── dbt/                        # Staging, intermediate, marts, tests
├── docs/
│   └── images/
│       └── airatlas-landing.png
├── frontend/                    # React dashboard and Ask Air UI
├── scripts/                     # Pipeline commands
├── src/airatlas/
│   ├── api/                     # Read-only serving and Ask Air endpoint
│   ├── ingestion/
│   ├── processing/
│   ├── curation/
│   ├── weather/
│   ├── warehouse/
│   └── orchestration/
├── tests/                       # Python test suite
├── pyproject.toml
└── README.md
```

## Running locally

### Prerequisites

- Python **3.12+**
- Node.js **22.12+** and npm
- Access to a PostgreSQL database for data-backed API endpoints
- API credentials for the external services you intend to use

### 1. Clone and install

```bash
git clone https://github.com/beko-1enkosi/airatlas.git
cd airatlas
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 2. Configure the backend

Copy `.env.example` to `.env` and supply your own credentials. The main variables are:

```dotenv
AIRATLAS_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/airatlas?sslmode=require
AIRATLAS_FRONTEND_ORIGIN=http://localhost:5173
AIRATLAS_DBT_SCHEMA=airatlas_analytics
OPENAQ_API_KEY=your-openaq-key
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
```

These are **placeholders**, not working credentials. dbt additionally uses the `AIRATLAS_DB_*` connection variables documented in `.env.example`. Never commit `.env` or place database or OpenRouter credentials in `frontend/.env.local`.

### 3. Start the API

```bash
set -a
source .env
set +a
python -m uvicorn airatlas.api.app:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://localhost:8000`, with interactive documentation at `http://localhost:8000/docs`.

### 4. Start the frontend

Open another terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

The local dashboard runs at `http://localhost:5173`. Its `VITE_API_BASE_URL` points to the local API; it is a **public browser setting**, not a secret.

### 5. Run quality checks

From the repository root, in the Python environment:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

For frontend checks:

```bash
cd frontend
npm test
npm run build
```

To build dbt models against a configured database:

```bash
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt
```

The scripts in `scripts/` implement the ingestion, processing, curation, enrichment, and warehouse-loading stages. Building the full warehouse requires source data and valid external service/database configuration; cloning the repository alone does not reproduce the historical snapshot.

## Deployment

AirAtlas uses two Vercel projects connected to the same repository:

- **Frontend:** `frontend/` as the project root, with `VITE_API_BASE_URL` set to the public backend URL.
- **API:** repository root, exposing the existing FastAPI application through `app.py`.

The API needs server-side `AIRATLAS_DATABASE_URL` and `AIRATLAS_FRONTEND_ORIGIN`. Ask Air also needs `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` on the **backend only**. The PostgreSQL warehouse is hosted on Neon.

All secrets must be configured through environment variables rather than committed to source control.

## Data interpretation and limitations

- **Historical, not live:** The dashboard currently serves a loaded historical dataset. Automated cloud ingestion/refresh is not yet enabled.
- **Uneven time coverage:** Stations have different reporting windows; a network-wide date range does not mean every location has observations throughout that interval.
- **Care with comparisons:** Averages across stations may represent different periods and should not be interpreted as a like-for-like comparison without aligning dates and units.
- **Weather context is descriptive:** Matched weather conditions do not establish that weather caused a measured pollution level.
- **Pipeline health is distinct from data availability:** An absent latest orchestration run does not mean that existing warehouse observations are invalid.
- **AI answers can be imperfect:** Ask Air uses limited trusted context, but generated explanations should still be checked against the underlying observations.

## Data sources

- [OpenAQ](https://openaq.org/) — public air-quality measurements and monitoring-location metadata.
- [Open-Meteo](https://open-meteo.com/) — historical weather context.

AirAtlas is an independent data engineering project and is not affiliated with either data provider. Source datasets retain their respective attribution and usage conditions.

---

**Built to make environmental data easier to explore, understand, and question.** ☁️
