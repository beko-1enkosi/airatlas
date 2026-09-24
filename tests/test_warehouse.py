"""Offline warehouse contract tests: temporary Parquet and transactional DB fakes."""

import copy
import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg
import pyarrow as pa
import pytest

from airatlas.curation.parquet import _write_dataset
from airatlas.warehouse import loader, schema
from airatlas.warehouse.loader import (
    WarehouseError,
    load_postgres_warehouse,
    prepare_input,
)


@pytest.fixture
def records():
    row = dict.fromkeys(schema.OBSERVATION_COLUMNS)
    row.update(
        location_id=225448,
        location_name="Jabavu-NAQI",
        sensor_id=101,
        parameter="pm25",
        parameter_id=2,
        unit="ug/m3",
        value=12.3,
        period_label="hour",
        period_interval="01:00:00",
        datetime_from_utc=datetime(2024, 1, 1, 9, tzinfo=UTC),
        datetime_to_utc=datetime(2024, 1, 1, 10, tzinfo=UTC),
        measurement_date_utc="2024-01-01",
        source="openaq",
        source_file="openaq/measurements/batch.json",
        retrieval_datetime_from="2024-01-01",
        retrieval_datetime_to="2024-01-02",
        weather_hour_utc=datetime(2024, 1, 1, 10, tzinfo=UTC),
        temperature_2m_c=22.0,
        relative_humidity_2m_pct=50.0,
        precipitation_mm=0.0,
        wind_speed_10m_kmh=12.0,
        weather_source="open_meteo",
        weather_latitude=-26.2,
        weather_longitude=28.0,
    )
    unmatched = {
        **row,
        "sensor_id": 102,
        "parameter": "pm10",
        "parameter_id": None,
        "value": -0.1,
    }
    for column in (
        "temperature_2m_c",
        "relative_humidity_2m_pct",
        "precipitation_mm",
        "wind_speed_10m_kmh",
        "weather_source",
        "weather_latitude",
        "weather_longitude",
    ):
        unmatched[column] = None
    return [row, unmatched]


def parquet_input(tmp_path, records, drop=()):
    fields = []
    for name, declaration in schema.OBSERVATION_TYPES.items():
        if name in drop:
            continue
        prefix = declaration.split()[0]
        dtype = {
            "BIGINT": pa.int64(),
            "DOUBLE": pa.float64(),
            "TIMESTAMPTZ": pa.timestamp("ns", tz="UTC"),
        }.get(prefix, pa.string())
        fields.append(pa.field(name, dtype))
    table = pa.Table.from_pylist(records, schema=pa.schema(fields))
    path = tmp_path / "enriched"
    # Flat Parquet is also valid input; normal Hive datasets are tested below.
    import pyarrow.parquet as pq

    path.mkdir(exist_ok=True)
    pq.write_table(table, path / "part.parquet")
    return path


class FakeDatabase:
    """Model connection-context commit/rollback and only the SQL used by the loader."""

    def __init__(self):
        self.locations, self.observations = [], []
        self.commits = self.rollbacks = 0
        self.statements = []
        self.fail_insert = False
        self.validation_result = None
        self.fail_commit = False

    def __enter__(self):
        self.before = copy.deepcopy((self.locations, self.observations))
        return self

    def __exit__(self, kind, error, traceback):
        if kind is not None or self.fail_commit:
            self.locations, self.observations = self.before
            self.rollbacks += 1
            if kind is None:
                raise psycopg.OperationalError("sensitive server failure")
        else:
            self.commits += 1

    def cursor(self):
        database = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql):
                database.statements.append(sql)
                if sql == "DELETE FROM airatlas.observations":
                    database.observations = []
                elif sql == "DELETE FROM airatlas.locations":
                    assert not database.observations
                    database.locations = []

            def executemany(self, sql, rows):
                database.statements.append(sql)
                if sql == schema.INSERT_LOCATIONS:
                    database.locations.extend(rows)
                else:
                    assert sql == schema.INSERT_OBSERVATIONS
                    assert database.locations
                    if database.fail_insert:
                        raise psycopg.DataError("secret database detail")
                    database.observations.extend(rows)

            def fetchone(self):
                return database.validation_result or (
                    len(database.observations),
                    len(database.locations),
                    0,
                    0,
                    0,
                )

        return Cursor()


@pytest.fixture
def database(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setenv(
        "AIRATLAS_DATABASE_URL", "postgresql://USER:TEST_PLACEHOLDER@localhost/airatlas"
    )
    monkeypatch.setattr(loader.psycopg, "connect", lambda *args, **kwargs: database)
    return database


def test_missing_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("AIRATLAS_DATABASE_URL", raising=False)
    with pytest.raises(WarehouseError, match="Set AIRATLAS_DATABASE_URL"):
        load_postgres_warehouse(tmp_path)


def test_mapping_and_hive_input(tmp_path, records):
    path = parquet_input(tmp_path, records)
    import pyarrow.dataset as ds

    table = ds.dataset(path, format="parquet").to_table()
    hive = tmp_path / "hive"
    _write_dataset(table, hive)
    original = {p: p.read_bytes() for p in hive.rglob("*.parquet")}
    locations, observations, summary = prepare_input(hive)
    assert locations == [(225448, "Jabavu-NAQI", None, None, -26.2, 28.0)]
    rows = [
        dict(zip(schema.OBSERVATION_COLUMNS, values, strict=True))
        for values in observations
    ]
    assert rows[0]["location_id"] == 225448 and rows[0]["sensor_id"] == 101
    assert type(rows[0]["datetime_to_utc"]) is datetime
    assert rows[0]["datetime_to_utc"].utcoffset().total_seconds() == 0
    assert rows[0]["value"] == 12.3
    assert rows[0]["weather_hour_utc"] == records[0]["weather_hour_utc"]
    assert rows[0]["weather_source"] == "open_meteo"
    assert rows[0]["temperature_2m_c"] == 22.0
    assert rows[1]["parameter_id"] is None
    assert rows[1]["temperature_2m_c"] is None and rows[1]["weather_source"] is None
    assert rows[1]["value"] == -0.1
    assert rows[0]["measurement_date_utc"].isoformat() == "2024-01-01"
    assert summary["weather_matched_rows"] == summary["weather_unmatched_rows"] == 1
    assert all(p.read_bytes() == content for p, content in original.items())


@pytest.mark.parametrize("retain_join_hour", [False, True])
def test_unmatched_weather_loads_as_sql_nulls(
    tmp_path, records, database, retain_join_hour
):
    unmatched = records[1]
    if not retain_join_hour:
        unmatched["weather_hour_utc"] = None
    summary = load_postgres_warehouse(parquet_input(tmp_path, [unmatched]))
    row = dict(zip(schema.OBSERVATION_COLUMNS, database.observations[0], strict=True))
    for column in loader.WEATHER_COLUMNS:
        assert row[column] == unmatched[column]
        if column != "weather_hour_utc" or not retain_join_hour:
            assert row[column] is None
    assert row["value"] == -0.1
    assert summary["weather_unmatched_rows"] == 1
    assert summary["weather_matched_rows"] == 0
    assert database.commits == 1


def test_all_null_weather_hour_arrow_type(tmp_path, records):
    import pyarrow.parquet as pq

    unmatched = records[1]
    unmatched["weather_hour_utc"] = None
    path = parquet_input(tmp_path, [unmatched])
    table = pq.read_table(path / "part.parquet")
    index = table.schema.get_field_index("weather_hour_utc")
    table = table.set_column(index, "weather_hour_utc", pa.nulls(1))
    pq.write_table(table, path / "part.parquet")
    _, observations, summary = prepare_input(path)
    assert observations[0][index] is None
    assert summary["weather_unmatched_rows"] == 1


def test_partial_matched_weather_is_valid(tmp_path, records, database):
    records[0]["temperature_2m_c"] = None
    records[0]["weather_latitude"] = None
    records[0]["weather_longitude"] = None
    summary = load_postgres_warehouse(parquet_input(tmp_path, [records[0]]))
    row = dict(zip(schema.OBSERVATION_COLUMNS, database.observations[0], strict=True))
    assert row["temperature_2m_c"] is None
    assert row["weather_latitude"] is None and row["weather_longitude"] is None
    assert row["relative_humidity_2m_pct"] == 50.0
    assert summary["weather_matched_rows"] == 1


@pytest.mark.parametrize(
    ("record_index", "column", "value", "message"),
    [
        (0, "weather_hour_utc", None, "Weather context requires"),
        (0, "weather_source", "", "Weather context requires"),
        (1, "temperature_2m_c", 20.0, "Weather values require"),
        (1, "weather_latitude", -26.2, "Weather values require"),
        (1, "weather_hour_utc", datetime(2024, 1, 1, 9, tzinfo=UTC), "weather hour"),
    ],
)
def test_inconsistent_weather_context_rejected(
    tmp_path, records, database, record_index, column, value, message
):
    records[record_index][column] = value
    with pytest.raises(WarehouseError, match=message):
        load_postgres_warehouse(parquet_input(tmp_path, records))
    assert not database.statements  # Invalid input fails before any database mutation.


@pytest.mark.parametrize(
    "column",
    [
        "location_id",
        "parameter",
        "unit",
        "measurement_date_utc",
        "weather_hour_utc",
        "weather_source",
        "temperature_2m_c",
    ],
)
def test_missing_columns(tmp_path, records, column):
    with pytest.raises(WarehouseError, match="Missing required enriched columns"):
        prepare_input(parquet_input(tmp_path, records, drop=[column]))


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("parameter", "no2", "pm25/pm10"),
        ("sensor_id", 0, "positive BIGINT"),
        ("unit", "", "must not be empty"),
        ("value", None, "cannot be null"),
        ("datetime_to_utc", datetime(2023, 1, 1, tzinfo=UTC), "end must be later"),
        ("measurement_date_utc", "2024-01-02", "Partition date"),
        ("weather_hour_utc", datetime(2024, 1, 1, 9, tzinfo=UTC), "weather hour"),
        (
            "datetime_to_utc",
            pd.Timestamp("2024-01-01T10:00:00.000000001Z"),
            "microsecond",
        ),
    ],
)
def test_invalid_input(tmp_path, records, column, value, message):
    records[0][column] = value
    with pytest.raises(WarehouseError, match=message):
        prepare_input(parquet_input(tmp_path, records))


def test_duplicate_keys_rejected(tmp_path, records):
    with pytest.raises(WarehouseError, match="Duplicate natural"):
        prepare_input(parquet_input(tmp_path, records + [records[0]]))


def test_conflicting_location_metadata(tmp_path, records):
    records[1]["location_name"] = "Different name"
    with pytest.raises(WarehouseError, match="Conflicting location_name"):
        prepare_input(parquet_input(tmp_path, records))


def test_empty_input_does_not_connect(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRATLAS_DATABASE_URL", "configured")
    monkeypatch.setattr(
        loader.psycopg, "connect", lambda *a, **k: pytest.fail("No DB call")
    )
    with pytest.raises(WarehouseError, match="empty"):
        load_postgres_warehouse(parquet_input(tmp_path, []))


def test_schema_constraints_and_indexes():
    sql = "\n".join(schema.SCHEMA_STATEMENTS)
    assert "CREATE SCHEMA IF NOT EXISTS airatlas" in sql
    assert "airatlas.locations" in sql and "airatlas.observations" in sql
    assert "PRIMARY KEY" in sql and "REFERENCES airatlas.locations(location_id)" in sql
    assert "observations_natural_key UNIQUE" in sql
    assert (
        "location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc" in sql
    )
    assert sql.count("CREATE INDEX IF NOT EXISTS") == 3
    assert "(location_id, datetime_to_utc)" in sql
    assert "(parameter, datetime_to_utc)" in sql
    assert "(measurement_date_utc)" in sql
    assert "TIMESTAMPTZ" in sql
    assert "DROP TABLE" not in sql and "DROP SCHEMA" not in sql
    assert "CASCADE" not in sql and "public." not in sql
    assert schema.OBSERVATION_TYPES["weather_hour_utc"] == "TIMESTAMPTZ"
    assert (
        "ALTER TABLE airatlas.observations ALTER COLUMN weather_hour_utc DROP NOT NULL"
        in sql
    )


def test_dsn_forwarded_and_repeated_refresh(tmp_path, records, database, monkeypatch):
    calls = []

    def connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        return database

    monkeypatch.setattr(loader.psycopg, "connect", connect)
    path = parquet_input(tmp_path, records)
    first = load_postgres_warehouse(path)
    second = load_postgres_warehouse(path)
    assert first == second
    assert first["observations_loaded"] == len(database.observations) == 2
    assert first["locations_loaded"] == len(database.locations) == 1
    assert database.commits == 2 and database.rollbacks == 0
    assert calls[0][0].endswith("@localhost/airatlas")
    assert calls[0][1]["autocommit"] is False
    assert "TEST_PLACEHOLDER" not in json.dumps(first)
    assert database.statements.count("DELETE FROM airatlas.observations") == 2


def test_refresh_preserves_pipeline_audit_history(tmp_path, records, database):
    database.pipeline_runs = {"existing_run": {"status": "succeeded"}}
    history = copy.deepcopy(database.pipeline_runs)
    path = parquet_input(tmp_path, records)
    load_postgres_warehouse(path)
    load_postgres_warehouse(path)
    assert database.pipeline_runs == history
    deletes = {sql for sql in database.statements if sql.startswith("DELETE")}
    assert deletes == {
        "DELETE FROM airatlas.observations",
        "DELETE FROM airatlas.locations",
    }
    assert not any(
        "TRUNCATE" in sql
        or "DROP TABLE" in sql
        or "DROP SCHEMA" in sql
        or "CASCADE" in sql
        or "pipeline_runs" in sql
        for sql in database.statements
    )


@pytest.mark.parametrize(
    "failure",
    ["insert", "commit", "count", "locations", "duplicates", "pollutants", "orphans"],
)
def test_failure_rolls_back_previous_snapshot(tmp_path, records, database, failure):
    path = parquet_input(tmp_path, records)
    load_postgres_warehouse(path)
    original = copy.deepcopy((database.locations, database.observations))
    if failure == "insert":
        database.fail_insert = True
    elif failure == "commit":
        database.fail_commit = True
    else:
        result = [2, 1, 0, 0, 0]
        result[
            {
                "count": 0,
                "locations": 1,
                "duplicates": 2,
                "pollutants": 3,
                "orphans": 4,
            }[failure]
        ] += 1
        database.validation_result = tuple(result)
    with pytest.raises(WarehouseError):
        load_postgres_warehouse(path)
    assert (database.locations, database.observations) == original
    assert database.commits == 1 and database.rollbacks == 1


def test_database_failure_is_redacted(tmp_path, records, database, monkeypatch):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError(
            "postgresql://USER:TEST_PLACEHOLDER@localhost/airatlas"
        )

    monkeypatch.setattr(loader.psycopg, "connect", fail)
    with pytest.raises(WarehouseError) as error:
        load_postgres_warehouse(parquet_input(tmp_path, records))
    assert "TEST_PLACEHOLDER" not in str(error.value)
    assert "postgresql://" not in str(error.value)
    assert error.value.__suppress_context__


def test_cli_summary(tmp_path, records, database, monkeypatch, capsys):
    path = parquet_input(tmp_path, records)
    monkeypatch.setattr(
        sys, "argv", ["load_postgres_warehouse.py", "--input-dir", str(path)]
    )
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/load_postgres_warehouse.py"),
        run_name="__main__",
    )
    result = json.loads(capsys.readouterr().out)
    assert result["observations_loaded"] == 2
    assert result["pm25_rows"] == result["pm10_rows"] == 1


def test_column_order_and_multiple_locations(tmp_path, records):
    import pyarrow.parquet as pq

    records[1]["location_id"] = 225404
    records[1]["location_name"] = "Table View-NAQI"
    records[1]["latitude"] = -33.9
    records[1]["longitude"] = 18.4
    path = parquet_input(tmp_path, records)
    expected = prepare_input(path)
    table = pq.read_table(path / "part.parquet")
    pq.write_table(
        table.select(list(reversed(table.column_names))), path / "part.parquet"
    )
    assert prepare_input(path) == expected
    assert len(expected[0]) == 2
    assert expected[0][0] == (225404, "Table View-NAQI", -33.9, 18.4, None, None)


def test_optional_provenance_nulls(tmp_path, records):
    _, rows, _ = prepare_input(
        parquet_input(
            tmp_path, records, drop=["source_file", "period_label", "latitude"]
        )
    )
    first = dict(zip(schema.OBSERVATION_COLUMNS, rows[0], strict=True))
    assert first["source_file"] is None and first["period_label"] is None
    assert first["latitude"] is None
