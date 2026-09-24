# AirAtlas architecture

## Purpose and status

AirAtlas is a Data Engineering portfolio project for collecting, processing, storing, and eventually serving public environmental data. **M1 - Foundation**, **M2 - Data Acquisition**, **M3 - Processing & Quality**, **M4 - Weather & Warehouse**, and **M5 - Analytics with dbt** are complete. Orchestration and serving remain planned.

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
       + Open-Meteo historical hours -> raw weather cache
  -> Weather-enriched Parquet
  -> PostgreSQL airatlas schema (Python-owned source warehouse)
  -> dbt sources -> staging views -> intermediate view
  -> Analytics mart tables
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

## Historical weather enrichment

Open-Meteo's public Historical Weather API supplies hourly temperature (Celsius), relative humidity (%), precipitation (mm), and wind speed (km/h), requested in UTC without an API key. Transient HTTP/network errors have bounded retries; permanent errors fail immediately. Source metadata, units, array lengths, timestamps, and structural values are validated before use.

Coordinates come first from consistent non-null curated pairs, then confirmed MVP configuration coordinates. Pairs differing by more than 0.00001 degrees fail; acceptable rounding differences select a deterministic pair. Missing coordinates fail before requests. The current six-location configuration has no coordinates, so they must come from curated observations unless confirmed values are supplied later. Names are never geocoded or used to guess coordinates.

Each represented location requests only the inclusive date span needed by its measurement-period ends. A cache under `data/raw/open_meteo/hourly/location_id=<id>/` uses dates plus a request-identity hash covering coordinates, variables, timezone, and units. Original response metadata, grid coordinates, hourly units and arrays are preserved. Valid identical requests reuse immutable files; corrupt caches fail rather than silently refreshing. Publication uses the same temporary-file/hard-link approach as OpenAQ raw storage.

Weather timestamps are UTC-aware. Air-quality period end is floored to the UTC hour and left-joined with weather on `(location_id, weather_hour_utc)`, never nearest-neighbour matching. Unmatched air-quality rows remain present. Missing weather values stay null; all-null weather hours count as unavailable, while partially populated hours count as matched. Lookup coordinates have separate weather column names.

The derived `data/curated/open_meteo_air_quality/air_quality_weather/` dataset preserves all air-quality columns and uses the existing pollutant/UTC-date partitions. A staged rebuild is read back before publication and leaves original curated air quality unchanged. Its manifest reports counts, match percentage (0 to 100), locations/sensors, coverage, variables, and columns. Rebuild/publication limitations are the same as M3.

## PostgreSQL analytical warehouse

The warehouse provides relational SQL access to the enriched analytical snapshot through direct Psycopg 3 calls. It reads only weather-enriched Parquet; raw, processed, and curated files remain unchanged. `AIRATLAS_DATABASE_URL` comes from the process environment; private `.env` files are not automatically loaded and connection details are not included in error summaries.

- `airatlas.locations` has one row per stable OpenAQ location ID (primary key), its name, and available air-quality/weather coordinates.
- `airatlas.observations` retains observation identity, source units/value, both period boundaries, local timestamp strings, UTC date, source/retrieval provenance, and nullable weather context. Its location ID references `locations`.
- A database unique constraint protects `(location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc)`. Pollutants are constrained to PM2.5/PM10. Indexes on `(location_id, datetime_to_utc)`, `(parameter, datetime_to_utc)`, and `measurement_date_utc` support time-series and daily filtering.

UTC columns use `TIMESTAMPTZ`; partition dates use `DATE`; IDs use `BIGINT`; measurements use `DOUBLE PRECISION`; source/local timestamp strings remain `TEXT`. SQL nulls preserve missing coordinates, parameter IDs, and weather values. PostgreSQL has microsecond timestamp precision: finer input timestamps are rejected before connection rather than rounded into changed natural keys. Conflicting non-null location metadata is also rejected rather than arbitrarily choosing dimension values.

Unmatched observations allow null weather source, hour, measurements and coordinates. The enrichment join may retain an aligned requested hour without a match, which is also valid. A matched source must be `open_meteo` with an hour aligned to period end; measurements and coordinates may still be null. Weather values without a source are rejected. No missing value is replaced with zero.

Input schema, typed mappings, supported pollutants, natural keys, dates and hour alignment are checked before connection. Empty input is refused to avoid clearing a warehouse accidentally. Missing optional provenance fields become null; required schema fields cannot be manufactured. SQL column mappings are explicit and independent of Parquet column order.

Schema/table/index creation is idempotent and part of the refresh transaction; it is not a migration system. A narrow compatibility repair drops the old `weather_hour_utc NOT NULL` restriction inside this transaction; other incompatible schemas require investigation. The loader locks the two AirAtlas tables against other writers, deletes observations then locations, inserts locations then batched observations, and checks row/location counts, duplicates, supported pollutants and foreign-key references. Only then does the connection context commit. Failures roll back the refresh; table definitions and indexes remain stable. Repeated loads replace the snapshot rather than append. Operations are scoped to the two `airatlas` tables, with no schema drops or cascade refreshes.

Examples in `sql/example_queries.sql` cover recent observations, averages by location, weather comparisons and daily trends. They group by pollutant and unit, avoiding incompatible concentration averages. These are descriptive observation-weighted summaries, not causal or duration-weighted analyses.

## dbt analytics

The Python warehouse loader owns `airatlas.locations` and `airatlas.observations`. dbt declares these as sources under `airatlas_warehouse` and reads them without refreshing or mutating them. With the default target `airatlas_analytics`, folder schemas keep each dbt layer separate:

- **Staging views** in `airatlas_analytics_staging`: `stg_locations` and `stg_observations` expose explicit warehouse columns without aggregation, unit conversion or filtering out missing weather.
- **Intermediate view** in `airatlas_analytics_intermediate`: `int_air_quality_weather` left-joins canonical location metadata while retaining observation provenance. `has_weather_context` is true when `weather_source` is present; individual weather values may still be null.
- **Mart tables** in `airatlas_analytics_marts`: rebuilt from dbt model references, with no incremental state or snapshots.

| Mart | Grain | Purpose |
| --- | --- | --- |
| `fct_air_quality_observations` | Location ID, sensor ID, parameter, UTC period start and end | All validated observations, source provenance and nullable weather; no aggregation. |
| `agg_daily_air_quality` | UTC period-end date x location x pollutant x unit | Counts, mean/minimum/maximum concentration and weather coverage. |
| `agg_location_air_quality` | Location x pollutant x unit | Concentration statistics, earliest/latest period end and weather coverage across the snapshot. |
| `agg_pollution_weather` | UTC period-end date x location x pollutant x unit, matched observations only | Pollution and weather means with non-null weather sample counts. |

Location names are descriptive attributes, not grouping identity. PM2.5 and PM10 and their source units remain separate. Means are observation-weighted, not time-weighted. Weather averages describe the weather sampled by matched observations; repeated hours may have multiple observations. Precipitation is an average of sampled hourly amounts, **not a daily rainfall total**. These models support association/context analysis without health classification or causal claims.

Built-in tests check required fields, accepted pollutants and location relationships. Singular SQL tests protect natural-key uniqueness, source-to-fact row counts, aggregate grains, positive counts, valid ranges and weather-matched group counts. Nullable weather hours and measurements are intentionally not required by `not_null` tests. The project contains 7 models, 2 sources and 89 data tests.

## Local PostgreSQL validation

For M5 completion, the developer verified the production loader and dbt against a real **local PostgreSQL 17** database named `airatlas`, using a deterministic enriched Parquet fixture. This is local development evidence, not a production/cloud deployment or a claim of live source coverage.

- The loader wrote 2 locations and 6 observations (4 PM2.5, 2 PM10; 5 weather-matched, 1 unmatched). The requested fixture spans period start `2026-09-01T10:00:00+00:00` through period end `2026-09-02T11:00:00+00:00`.
- A second refresh retained 6 observations, not 12. PostgreSQL inspection confirmed nullable `weather_hour_utc`, natural-key uniqueness, the location foreign key, pollutant/period checks and analytical indexes.
- `dbt debug` passed. `dbt build` executed all 7 models and 89 data tests: **PASS=96, WARN=0, ERROR=0, SKIP=0, TOTAL=96**. Source tables remained in `airatlas`, with models in the separate staging, intermediate and marts schemas.
- Representative queries returned 6 fact rows, 5 daily rows, 4 location rows and 4 weather-context rows. Jabavu-NAQI PM2.5 on September 1 had 2 observations averaging 12.7; Table View-NAQI PM2.5 averaged 8.7 across 2 observations. Pollutant and unit remained visible in each aggregate.
- `dbt docs generate` produced the catalog successfully. Generated files under `dbt/target/` remain ignored.

## Data layers and future architecture

| Layer | Implemented purpose |
| --- | --- |
| `data/raw/` | Immutable OpenAQ JSON and cache-first Open-Meteo JSON source evidence, with request provenance. |
| `data/processed/` | Rebuildable validated, normalized, deduplicated CSV observations and a quality report. |
| `data/curated/` | Rebuildable air-quality and weather-enriched Parquet datasets, plus manifests. |
| PostgreSQL `airatlas` | Queryable relational analytical storage rebuilt transactionally from enriched Parquet. |
| dbt analytics schemas | Tested staging/intermediate views and observation, daily, location and weather-context mart tables. |

All generated filesystem layers are Git-ignored. Processing and curation do not alter their inputs.

Planned flow: dbt analytics marts -> API/dashboard. Apache Airflow will orchestrate stages. The dashboard is an output layer; its technology has not been selected. Airflow DAGs, API endpoints, and dashboard functionality do not exist yet.

## Foundation tooling

Python uses a `src/` package layout and setuptools with editable installation. Python 3.12 is the recommended baseline. Ruff handles linting/formatting; pytest exercises offline ingestion, processing, and temporary-directory JSON/CSV/Parquet storage. Warehouse unit tests use fake Psycopg connections, so CI requires no PostgreSQL service. CI also runs database-free dbt parsing. Real local PostgreSQL execution passed the M5 completion gate, as recorded above; it remains separate from CI. GitHub Actions runs installation and checks on pushes and pull requests, without deployment.

See the [development guide](development.md) or [project overview](../README.md).
