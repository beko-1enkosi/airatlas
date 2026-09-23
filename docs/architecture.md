# AirAtlas architecture

## Purpose and status

AirAtlas is a Data Engineering portfolio project for collecting, processing, storing, and eventually serving public environmental data. **M1 - Foundation** and **M2 - Data Acquisition** are complete. Processing, analytical storage, orchestration, weather integration, and serving remain planned.

## Implemented acquisition flow

```text
OpenAQ API v3
  -> South African location discovery (iso=ZA)
  -> Six approved locations in config/mvp_locations.json
  -> PM2.5 / PM10 sensor discovery
  -> Explicit historical dates or incremental timestamp window
  -> Sequential pagination, bounded retries, rate-limit handling
  -> Raw JSON snapshots under data/raw/
```

Python and httpx implement the HTTP boundary. Location IDs resolve to sensor IDs because measurements are sensor-based. Original measurement objects are retained without an analytics schema conversion. Discovery remains terminal-only; the backfill and incremental scripts persist measurement batches.

Pagination preserves page metadata, stops at a known total or a short/empty page for unknown totals, and raises on inconsistent or repeated pages or the page-count guard. Transient failures receive at most three retries after the initial attempt. HTTP 429 uses a valid reset delay capped at 60 seconds; other retry delays use bounded exponential backoff. Permanent failures are not retried.

## Raw source layer

```text
data/raw/openaq/measurements/
  location_id=<OpenAQ ID>/
    parameter=<parameter>/
      sensor_id=<OpenAQ sensor ID>/
        <requested-start>__<requested-end>.json
```

Dates use names such as `20260901__20260902.json`; UTC timestamps use names such as `20260901T000000Z__20260901T010000Z.json`. Fractional seconds are retained when supplied. Stable IDs identify sources; station names are descriptive metadata.

Each JSON envelope records source/resource/schema version, location and sensor identity, parameter, requested window, counts, completeness, available page metadata, and the original measurements. Rate-limit counters are excluded from stored snapshots because they vary between otherwise identical requests. JSON preserves nested source objects and requires no new storage dependencies. It is not a cleaned or transformed analytics dataset.

Only complete batches are accepted, including complete empty windows. An existing path with identical JSON content is reused even if whitespace or key ordering differs. Different source content or provenance raises `RawPersistenceConflictError`; raw snapshots are never silently overwritten. Overlapping windows may contain repeated measurements; persistence does not deduplicate records across windows.

Files are written to a temporary file in the destination directory, flushed, and published atomically with a hard link that cannot overwrite an existing target. Temporary files are then removed. This requires a filesystem supporting hard links. Atomicity is per file, not a multi-file transaction: an interrupted run can leave completed batches that an identical rerun reuses. Changing source history at an existing window produces a conflict requiring explicit investigation.

## Incremental checkpoint safety

The caller supplies a timezone-aware checkpoint and later upper boundary. They are normalized to UTC. The next candidate equals the requested upper boundary, including for complete empty windows. Required sensor discovery and measurement retrieval must be complete, and both required pollutants must be present.

Unsafe incremental runs are refused by persistence. A persistence error prevents the CLI from reporting successful persistence. A safe candidate applies only to the queried location set, especially when `--location-id` is used. Checkpoint state is not saved; a future state/orchestration layer must commit it only after successful persistence. Source identifiers and timestamps remain available for future idempotent processing of repeated boundary records.

## Data layers and future architecture

| Layer | Current state and intended purpose |
| --- | --- |
| `data/raw/` | Implemented local source-preserving OpenAQ JSON snapshots; generated files are ignored by Git. |
| `data/processed/` | Placeholder for future validated, cleaned, and transformed intermediate data. |
| `data/curated/` | Placeholder for future analysis-ready outputs. |

Planned flow: raw air-quality data plus future Open-Meteo weather data -> validation/cleaning -> Pandas -> partitioned Parquet -> PostgreSQL -> dbt models -> FastAPI/dashboard. Apache Airflow will orchestrate stages. The dashboard is an output layer; its technology has not been selected.

There are no processed datasets, Parquet outputs, database integrations, dbt models, Airflow DAGs, weather integration, API endpoints, or dashboard functionality yet.

## Foundation tooling

Python uses a `src/` package layout and setuptools with editable installation. Python 3.12 is the recommended baseline. Ruff handles linting/formatting; pytest exercises offline ingestion and temporary-directory storage. GitHub Actions runs installation and checks on pushes and pull requests, without deployment.

See the [development guide](development.md) or [project overview](../README.md).
