"""Serving HTTP contracts and parameterized read-only SQL; no live PostgreSQL."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from airatlas.api import database, queries
from airatlas.api.app import app

TIME = datetime(2026, 9, 1, 10, tzinfo=UTC)
SUMMARY = {
    "monitored_locations": 2,
    "observation_count": 3,
    "weather_coverage": 66.67,
    "earliest_observation": TIME,
    "latest_observation": TIME,
    "averages": [
        {
            "parameter": "pm25",
            "unit": "µg/m³",
            "average_value": 12,
            "observation_count": 2,
        },
        {
            "parameter": "pm25",
            "unit": "mg/m³",
            "average_value": 0.02,
            "observation_count": 1,
        },
    ],
}
LOCATION = {
    "location_id": 225448,
    "location_name": "Jabavu-NAQI",
    "latitude": None,
    "longitude": None,
}
OBSERVATION = {
    "sensor_id": 1,
    "parameter": "pm25",
    "unit": "µg/m³",
    "value": -1,
    "datetime_from_utc": TIME,
    "datetime_to_utc": datetime(2026, 9, 1, 11, tzinfo=UTC),
    "has_weather_context": False,
    "weather_hour_utc": None,
    "temperature_2m_c": None,
    "relative_humidity_2m_pct": None,
    "precipitation_mm": None,
    "wind_speed_10m_kmh": None,
    "weather_source": None,
}


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client, monkeypatch):
    monkeypatch.setattr("airatlas.api.app.query", lambda _: [{"connected": 1}])
    assert client.get("/api/health").json() == {
        "service": "AirAtlas",
        "status": "ok",
        "database": "connected",
    }


def test_summary_preserves_multiple_units_and_utc(client, monkeypatch):
    monkeypatch.setattr(queries, "summary", lambda: SUMMARY)
    response = client.get("/api/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["monitored_locations"] == 2
    assert len(data["averages"]) == 2
    assert data["averages"][0]["unit"] == "µg/m³"
    assert data["latest_observation"].endswith("Z")


def test_locations_keep_missing_coordinates(client, monkeypatch):
    monkeypatch.setattr(
        queries, "locations", lambda: [{**LOCATION, "parameters": ["pm25", "pm10"]}]
    )
    assert client.get("/api/locations").json()[0]["latitude"] is None


def test_detail_preserves_unmatched_observation(client, monkeypatch):
    monkeypatch.setattr(
        queries,
        "location_detail",
        lambda _: {**LOCATION, "latest": [OBSERVATION], "recent": [OBSERVATION]},
    )
    data = client.get("/api/locations/225448").json()
    assert data["latest"][0]["value"] == -1
    assert data["latest"][0]["weather_source"] is None


def test_location_not_found(client, monkeypatch):
    monkeypatch.setattr(queries, "location_detail", lambda _: None)
    assert client.get("/api/locations/123").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/trends?parameter=no2",
        "/api/weather-context?parameter=no2",
        "/api/comparison/locations?parameter=pm25%27",
        "/api/locations/-1",
        "/api/trends?date_from=garbage",
        "/api/trends?date_from=2026-09-02&date_to=2026-09-01",
        "/api/trends?location_id=0",
        "/api/trends?limit=2001",
        "/api/trends?limit=0",
        "/api/trends?date_from=0",
        "/api/trends?date_to=20260901",
        "/api/trends?location_id=9999999999999999999999",
        "/api/locations/9999999999999999999999",
    ],
)
def test_invalid_filters_fail_before_database(client, monkeypatch, path):
    def unexpected(*args):
        pytest.fail("Invalid request must not reach SQL")

    monkeypatch.setattr(queries, "series", unexpected)
    monkeypatch.setattr(queries, "comparison", unexpected)
    monkeypatch.setattr(queries, "location_detail", unexpected)
    assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "endpoint,kind", [("trends", "trends"), ("weather-context", "weather")]
)
def test_inclusive_date_filter_and_empty_results(client, monkeypatch, endpoint, kind):
    fake = MagicMock(return_value={"rows": [], "truncated": False, "limit": 1000})
    monkeypatch.setattr(queries, "series", fake)
    response = client.get(
        f"/api/{endpoint}?parameter=pm10&location_id=225448&date_from=2026-09-01&date_to=2026-09-01"
    )
    assert response.status_code == 200
    fake.assert_called_once_with(
        kind, "pm10", 225448, date(2026, 9, 1), date(2026, 9, 1), 1000
    )
    assert response.json()["rows"] == []


@pytest.mark.parametrize("status", [None, "running", "succeeded", "failed"])
def test_data_health_states(client, monkeypatch, status):
    run = (
        None
        if status is None
        else {
            "run_id": "manual__test",
            "run_mode": "historical",
            "status": status,
            "requested_start": TIME,
            "requested_end": TIME,
            "location_id": None,
            "current_stage": "build_dbt_analytics",
            "failed_stage": "build_dbt_analytics" if status == "failed" else None,
            "started_at": TIME,
            "finished_at": None if status == "running" else TIME,
            "observations_loaded": 3,
            "error_summary": "not for the browser",
        }
    )
    monkeypatch.setattr(
        queries, "data_health", lambda: {"latest_run": run, "summary": SUMMARY}
    )
    response = client.get("/api/data-health")
    assert response.status_code == 200
    assert "error_summary" not in response.text
    assert (
        response.json()["latest_run"] is None
        if status is None
        else response.json()["latest_run"]["status"] == status
    )


def test_database_error_is_safe(client, monkeypatch):
    def failed():
        raise database.DatabaseUnavailable("postgresql://private:secret@host")

    monkeypatch.setattr(queries, "summary", failed)
    response = client.get("/api/summary")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "postgresql" not in response.text


def test_bad_response_does_not_expose_internal_data(client, monkeypatch):
    monkeypatch.setattr(queries, "summary", lambda: {"password": "secret"})
    response = client.get("/api/summary")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_cors_only_local_configured_origin(client, monkeypatch):
    monkeypatch.setattr("airatlas.api.app.query", lambda _: [])
    assert (
        client.get("/api/health", headers={"Origin": "http://localhost:5173"}).headers[
            "access-control-allow-origin"
        ]
        == "http://localhost:5173"
    )
    assert (
        "access-control-allow-origin"
        not in client.get(
            "/api/health", headers={"Origin": "https://elsewhere.example"}
        ).headers
    )


def test_missing_database_configuration(monkeypatch):
    monkeypatch.delenv("AIRATLAS_DATABASE_URL", raising=False)
    with pytest.raises(database.DatabaseUnavailable, match="Data service unavailable"):
        database.query("SELECT 1")


def test_read_only_transaction_and_bound_parameters(monkeypatch):
    connection = MagicMock()
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(database.psycopg, "connect", connect)
    monkeypatch.setenv("AIRATLAS_DATABASE_URL", "postgresql://placeholder")
    database.query("SELECT %s", (17,))
    statements = connection.execute.call_args_list
    assert statements[0].args == ("SET TRANSACTION READ ONLY",)
    assert "statement_timeout" in statements[1].args[0]
    assert statements[-1].args == ("SELECT %s", (17,))


def test_driver_message_is_not_exposed(monkeypatch):
    monkeypatch.setenv("AIRATLAS_DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(
        database.psycopg,
        "connect",
        MagicMock(side_effect=psycopg.OperationalError("secret DSN")),
    )
    with pytest.raises(database.DatabaseUnavailable) as error:
        database.query("SELECT 1")
    assert "secret" not in str(error.value)


def test_series_parameter_binding_and_truncation(monkeypatch):
    fake = MagicMock(return_value=[{"unit": "a"}, {"unit": "b"}, {"unit": "c"}])
    monkeypatch.setattr(queries, "query", fake)
    result = queries.series("trends", "pm25", 225448, date(2026, 9, 1), None, 2)
    assert result == {
        "rows": [{"unit": "a"}, {"unit": "b"}],
        "truncated": True,
        "limit": 2,
    }
    statement, values = fake.call_args.args
    assert values == (None, "pm25", 225448, 225448, date(2026, 9, 1), 3)
    assert "agg_daily_air_quality" in statement.as_string()
    assert "225448" not in statement.as_string()


def test_schema_setting_is_quoted(monkeypatch):
    monkeypatch.setenv("AIRATLAS_DBT_SCHEMA", 'custom"schema')
    assert (
        '"custom""schema_marts"'
        in queries.statement("SELECT 1 FROM {marts}.example").as_string()
    )


def test_summary_uses_weighted_mart_rollup_by_unit(monkeypatch):
    fake = MagicMock(side_effect=[[{"observation_count": 3}], []])
    monkeypatch.setattr(queries, "query", fake)
    queries.summary()
    sql = fake.call_args_list[1].args[0].as_string()
    assert "average_value * observation_count" in sql
    assert "GROUP BY parameter, unit" in sql


def test_latest_readings_have_deterministic_ties(monkeypatch):
    fake = MagicMock(side_effect=[[LOCATION], [], []])
    monkeypatch.setattr(queries, "query", fake)
    result = queries.location_detail(225448)
    assert result["recent"] == []
    assert "DISTINCT ON (parameter, unit)" in fake.call_args_list[1].args[0].as_string()
    assert "sensor_id ASC" in fake.call_args_list[1].args[0].as_string()


def test_audit_query_has_no_error_text_or_secrets(monkeypatch):
    fake = MagicMock(return_value=[])
    monkeypatch.setattr(queries, "query", fake)
    monkeypatch.setattr(queries, "summary", lambda: SUMMARY)
    assert queries.data_health()["latest_run"] is None
    sql = fake.call_args.args[0]
    assert "error_summary" not in sql
    assert "LIMIT 1" in sql


def test_empty_summary_is_explicit(client, monkeypatch):
    monkeypatch.setattr(
        queries,
        "summary",
        lambda: {
            "monitored_locations": 0,
            "observation_count": 0,
            "weather_coverage": None,
            "earliest_observation": None,
            "latest_observation": None,
            "averages": [],
        },
    )
    result = client.get("/api/summary")
    assert result.status_code == 200
    assert result.json()["averages"] == []
    assert result.json()["weather_coverage"] is None


@pytest.mark.parametrize("kind", ["trends", "weather-context"])
def test_populated_series_preserves_mart_values(client, monkeypatch, kind):
    row = {
        "measurement_date_utc": date(2026, 9, 1),
        "location_id": 225448,
        "location_name": "Jabavu-NAQI",
        "parameter": "pm25",
        "unit": "µg/m³",
        "observation_count": 2,
    }
    if kind == "trends":
        row.update(
            average_value=12.7,
            minimum_value=10,
            maximum_value=15.4,
            weather_context_count=1,
            weather_context_percentage=50,
        )
    else:
        row.update(
            average_pollution_value=12.7,
            average_temperature_2m_c=21,
            average_relative_humidity_2m_pct=None,
            average_precipitation_mm=None,
            average_wind_speed_10m_kmh=12,
            temperature_observation_count=2,
            humidity_observation_count=0,
            precipitation_observation_count=0,
            wind_observation_count=2,
        )
    monkeypatch.setattr(
        queries,
        "series",
        lambda *args: {"rows": [row], "truncated": False, "limit": 1000},
    )
    response = client.get(f"/api/{kind}")
    assert response.status_code == 200
    assert response.json()["rows"][0]["unit"] == "µg/m³"
    assert response.json()["rows"][0]["measurement_date_utc"] == "2026-09-01"
