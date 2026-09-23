# AirAtlas architecture

## Purpose and status

AirAtlas is a Data Engineering portfolio project for collecting, processing, storing, and eventually serving public environmental data. **M1 - Foundation**, **M2 - Data Acquisition**, and **M3 - Processing & Quality** are complete. Analytical database storage, orchestration, weather integration, and serving remain planned.

## Implemented flow

```text
OpenAQ API v3
  -> South African location discovery (iso=ZA)
  -> Six approved locations in config/mvp_locations.json
  -> PM2.5 / PM10 sensor discovery
  -> Explicit historical dates or incremental timestamp window
  -> Sequential pagination, bounded retries, rate-limit handling
  -> Immutable raw JSON under data/raw/
  -> Pandas normalization, validation, deduplication and conflict detection
  -> Processed CSV + quality report under data/processed/
  -> Curated partitioned Parquet under data/curated/
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

Unsafe incremental runs are refused by persistence. A persistence error prevents the CLI from reporting successful persistence. A safe candidate applies only to the queried location set, especially when `--location-id` is used. Checkpoint state is not saved; a future state/orchestration layer must commit it only after successful persistence. Source identifiers and timestamps support deduplication of repeated boundary observations in the processed layer.

## Processing and quality

The processor discovers OpenAQ measurement envelopes beneath the raw root in sorted order. Invalid JSON or missing batch provenance fails clearly. Within valid batches, invalid records are excluded and counted by reason. Accepted records require positive location/sensor IDs, matching PM2.5/PM10 parameters, source units, finite values, and timezone-aware period boundaries with end after start. UTC start and end timestamps, local source timestamps, and relative raw-file provenance are retained. Units are preserved without conversion. Finite negative values remain present and are counted, not declared scientifically valid.

The observation key is location ID, sensor ID, parameter, UTC period start, and UTC period end. Repeated matching source observations become one row; conflicting source content raises an error. The full snapshot is sorted deterministically and written as `data/processed/openaq/air_quality_observations.csv`. `quality_report.json` records input, rejection, duplicate, final-row, negative-value, parameter, and observed-unit counts. No raw batches is an explicit input error; complete empty batches produce a header-only CSV and zero-row report. Processed files are staged and replaced atomically per file.

## Curated Parquet

Curation reads only the processed CSV. It checks the required schema, supported pollutants, typed values, UTC periods, and absence of duplicate natural keys; it never silently deduplicates again. Optional nulls and provenance columns survive. PyArrow stores UTC boundaries as nanosecond timestamps, IDs as integers, and numeric measurements as doubles. No unit conversion or further environmental interpretation occurs.

```text
data/curated/openaq/
  air_quality/
    parameter=pm25/
      measurement_date_utc=2026-09-02/
        part-00000.parquet
    parameter=pm10/
      measurement_date_utc=2026-09-02/
        part-00000.parquet
  air_quality_manifest.json
```

`measurement_date_utc` is the UTC calendar date of **period end**, not start or local time. Partition columns are represented in the directory names and reconstructed when reading the dataset with Hive partitioning. The original period timestamps remain in Parquet. Pollutant/date partitioning lets downstream readers select relevant subsets without using overly granular sensor/hour partitions. Parquet offers compressed columnar storage and typed columns for analysis.

Rows are sorted before writing fixed filenames. A staged dataset is read back and compared with the validated input, including values, nulls, and timestamp types. The manifest records schema version, source layer, input basename (no absolute machine path), row/pollutant/location/sensor counts, earliest period start, latest period end, partitions, and columns.

A rebuild replaces the dedicated `openaq/` curated namespace, including its manifest, removing stale partitions. An empty processed input raises without replacing an existing snapshot. Write or validation failures leave the old build intact; an ordinary publication failure rolls back the directory swap. Run one builder at a time. The swap is not a concurrent-reader or power-loss transaction: interruption can leave a backup requiring manual recovery. This keeps rebuilds simple without claiming database-style transactions.

## Data layers and future architecture

| Layer | Implemented purpose |
| --- | --- |
| `data/raw/` | Immutable OpenAQ JSON source evidence, including original measurement objects and retrieval provenance. |
| `data/processed/` | Rebuildable validated, normalized, deduplicated CSV observations and a quality report. |
| `data/curated/` | Rebuildable, analysis-ready partitioned Parquet derived from processed CSV, plus its manifest. |

All generated layers are Git-ignored. Processing and curation do not alter their inputs.

Planned flow: curated air-quality Parquet plus future Open-Meteo weather data -> PostgreSQL -> dbt models -> FastAPI/dashboard. Apache Airflow will orchestrate stages. The dashboard is an output layer; its technology has not been selected. Database integrations, dbt models, Airflow DAGs, weather integration, API endpoints, and dashboard functionality do not exist yet.

## Foundation tooling

Python uses a `src/` package layout and setuptools with editable installation. Python 3.12 is the recommended baseline. Ruff handles linting/formatting; pytest exercises offline ingestion, processing, and temporary-directory JSON/CSV/Parquet storage. GitHub Actions runs installation and checks on pushes and pull requests, without deployment.

See the [development guide](development.md) or [project overview](../README.md).
