"""Read-only Parquet input and one transactional full refresh of airatlas tables."""

import math
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.dataset as ds

from airatlas.curation.parquet import REQUIRED
from airatlas.processing.normalize import KEY
from airatlas.warehouse.schema import (
    INSERT_LOCATIONS,
    INSERT_OBSERVATIONS,
    LOCATION_COLUMNS,
    OBSERVATION_COLUMNS,
    OBSERVATION_TYPES,
    VALIDATE_SQL,
    ensure_schema,
)
from airatlas.weather.enrichment import WEATHER_COLUMNS


class WarehouseError(ValueError):
    """Warehouse configuration, input, or transactional refresh failed."""


def database_url():
    dsn = os.environ.get("AIRATLAS_DATABASE_URL", "")
    if not dsn.strip():
        raise WarehouseError(
            "Set AIRATLAS_DATABASE_URL in the process environment before loading PostgreSQL."
        )
    return dsn


def _sql_value(column, value):
    """Explicit SQL types; nulls remain None and no timestamp precision is lost."""
    if value is None or pd.isna(value):
        return None
    dtype = OBSERVATION_TYPES[column].split()[0]
    if dtype == "TIMESTAMPTZ":
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise WarehouseError(f"{column} requires a timezone-aware timestamp.")
        if isinstance(value, pd.Timestamp):
            if value.nanosecond:
                raise WarehouseError(
                    "PostgreSQL supports microsecond timestamps; finer precision would change observation identity."
                )
            value = value.to_pydatetime()
        return value.astimezone(UTC)
    if dtype == "BIGINT":
        if type(value) is not int or not 0 < value <= 2**63 - 1:
            raise WarehouseError(f"{column} requires a positive BIGINT identifier.")
        return value
    if dtype == "DOUBLE":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise WarehouseError(f"{column} requires a finite numeric value or null.")
        return float(value)
    if dtype == "DATE":
        try:
            parsed = date.fromisoformat(value) if isinstance(value, str) else value
            if type(parsed) is not date:
                raise ValueError
            return parsed
        except ValueError:
            raise WarehouseError("measurement_date_utc must be an ISO date.") from None
    if not isinstance(value, str):
        raise WarehouseError(f"{column} requires source text or null.")
    return value


def prepare_input(input_dir):
    """Return explicitly ordered location/observation tuples and a safe summary.

    Empty inputs fail before connecting, avoiding accidental snapshot deletion.
    Conflicting non-null location metadata fails rather than inventing a dimension
    value. All original per-observation fields remain in the observations table.
    """
    try:
        table = ds.dataset(
            Path(input_dir), format="parquet", partitioning="hive"
        ).to_table()
    except (ValueError, OSError):
        raise WarehouseError(
            "Cannot read weather-enriched curated Parquet input."
        ) from None
    missing = REQUIRED.union(WEATHER_COLUMNS, {"measurement_date_utc"}) - set(
        table.column_names
    )
    if missing:
        raise WarehouseError(
            f"Missing required enriched columns: {', '.join(sorted(missing))}."
        )
    if not table.num_rows:
        raise WarehouseError("Enriched input is empty; warehouse refresh refused.")
    for column in ("datetime_from_utc", "datetime_to_utc", "weather_hour_utc"):
        if not pa.types.is_timestamp(table.schema.field(column).type):
            raise WarehouseError(f"{column} must have a timestamp type.")
    records, seen, dimensions = [], set(), {}
    for source in table.to_pylist():
        row = {
            column: _sql_value(column, source.get(column))
            for column in OBSERVATION_COLUMNS
        }
        for column, dtype in OBSERVATION_TYPES.items():
            if "NOT NULL" in dtype and row[column] is None:
                raise WarehouseError(f"{column} cannot be null.")
        if row["parameter"] not in {"pm25", "pm10"} or row["source"] != "openaq":
            raise WarehouseError(
                "Warehouse accepts only OpenAQ pm25/pm10 observations."
            )
        if not row["unit"].strip():
            raise WarehouseError("Observation unit must not be empty.")
        if row["datetime_to_utc"] <= row["datetime_from_utc"]:
            raise WarehouseError("Observation period end must be later than start.")
        if row["measurement_date_utc"] != row["datetime_to_utc"].date() or row[
            "weather_hour_utc"
        ] != row["datetime_to_utc"].replace(minute=0, second=0, microsecond=0):
            raise WarehouseError(
                "Partition date or weather hour disagrees with period end."
            )
        key = tuple(row[column] for column in KEY)
        if key in seen:
            raise WarehouseError("Duplicate natural observation key in enriched input.")
        seen.add(key)
        dimension = dimensions.setdefault(
            row["location_id"], dict.fromkeys(LOCATION_COLUMNS)
        )
        for column in LOCATION_COLUMNS:
            value = row[column]
            if value is None:
                continue
            if dimension[column] is not None and dimension[column] != value:
                raise WarehouseError(
                    f"Conflicting {column} for location {row['location_id']}."
                )
            dimension[column] = value
        records.append(row)
    records.sort(key=lambda row: tuple(row[column] for column in KEY))
    locations = [
        tuple(dimensions[key][column] for column in LOCATION_COLUMNS)
        for key in sorted(dimensions)
    ]
    observations = [
        tuple(row[column] for column in OBSERVATION_COLUMNS) for row in records
    ]
    matched = sum(row["weather_source"] is not None for row in records)
    summary = {
        "input_observations": len(records),
        "locations_loaded": len(locations),
        "observations_loaded": len(records),
        "pm25_rows": sum(row["parameter"] == "pm25" for row in records),
        "pm10_rows": sum(row["parameter"] == "pm10" for row in records),
        "weather_matched_rows": matched,
        "weather_unmatched_rows": len(records) - matched,
        "earliest_observation": min(
            row["datetime_from_utc"] for row in records
        ).isoformat(),
        "latest_observation": max(
            row["datetime_to_utc"] for row in records
        ).isoformat(),
    }
    return locations, observations, summary


def load_postgres_warehouse(input_dir):
    """Refresh only airatlas.locations/observations; one commit after validation.

    Psycopg's connection context commits on success, rolls back on any exception,
    and closes the connection. DDL is included in the same transaction. Table
    locks serialize refresh writers while ordinary SELECTs can use committed data.
    Connection/server details are deliberately excluded from public errors.
    """
    dsn = database_url()
    locations, observations, summary = prepare_input(input_dir)
    try:
        with psycopg.connect(dsn, autocommit=False, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL TIME ZONE 'UTC'")
                ensure_schema(cursor)
                cursor.execute(
                    "LOCK TABLE airatlas.locations, airatlas.observations IN SHARE ROW EXCLUSIVE MODE"
                )
                cursor.execute("DELETE FROM airatlas.observations")
                cursor.execute("DELETE FROM airatlas.locations")
                cursor.executemany(INSERT_LOCATIONS, locations)
                for offset in range(0, len(observations), 1000):
                    cursor.executemany(
                        INSERT_OBSERVATIONS, observations[offset : offset + 1000]
                    )
                cursor.execute(VALIDATE_SQL)
                if cursor.fetchone() != (len(observations), len(locations), 0, 0, 0):
                    raise WarehouseError(
                        "Warehouse post-load validation failed; refresh rolled back."
                    )
    except psycopg.Error:
        raise WarehouseError(
            "PostgreSQL connection or refresh failed. No partial refresh was committed; check database availability, permissions, and schema compatibility."
        ) from None
    return summary
