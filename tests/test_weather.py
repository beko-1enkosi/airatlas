"""Offline historical weather/cache/enrichment tests; all datasets use tmp_path."""

import json
import runpy
import sys
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.dataset as ds
import pytest

from airatlas.curation.parquet import build_curated_air_quality
from airatlas.processing.normalize import COLUMNS
from airatlas.weather import enrichment
from airatlas.weather.client import (
    ENDPOINT,
    SETTINGS,
    UNITS,
    VARIABLES,
    OpenMeteoClient,
    WeatherError,
    validate_response,
)
from airatlas.weather.enrichment import (
    METRICS,
    MissingLocationCoordinatesError,
    enrich_air_quality_weather,
    normalize_weather,
    resolve_coordinates,
)
from airatlas.weather.storage import get_cached_weather


def response_payload(temperature=15.0):
    return {
        "latitude": -26.25,
        "longitude": 28.0,
        "elevation": 1650.0,
        "generationtime_ms": 1.2,
        "timezone": "GMT",
        "utc_offset_seconds": 0,
        "hourly_units": {"time": "iso8601", **UNITS},
        "hourly": {
            "time": ["2024-01-01T10:00"],
            "temperature_2m": [temperature],
            "relative_humidity_2m": [55],
            "precipitation": [0.4],
            "wind_speed_10m": [12.5],
        },
    }


def client_for(handler):
    return OpenMeteoClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: pytest.fail("Unexpected retry sleep"),
    )


def test_request_contract():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_payload())

    client = client_for(handler)
    assert (
        client.get_hourly(-26.2, 28, "2024-01-01", "2024-01-01") == response_payload()
    )
    request = requests[0]
    assert str(request.url).split("?")[0] == ENDPOINT
    assert dict(request.url.params) == {
        "latitude": "-26.2",
        "longitude": "28.0",
        "start_date": "2024-01-01",
        "end_date": "2024-01-01",
        "hourly": ",".join(VARIABLES),
        **SETTINGS,
    }
    assert "x-api-key" not in request.headers
    assert client.requests_made == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_retries(status):
    codes = iter([status, status, 200])
    delays = []
    client = OpenMeteoClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(next(codes), json=response_payload())
        ),
        sleep=delays.append,
    )
    client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")
    assert client.requests_made == 3
    assert delays == [0.5, 1.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_errors_not_retried(status):
    client = client_for(lambda _: httpx.Response(status))
    with pytest.raises(WeatherError, match=f"HTTP {status}.*not retryable"):
        client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")
    assert client.requests_made == 1


@pytest.mark.parametrize("network", [False, True])
def test_retry_exhaustion(network):
    delays = []

    def handler(request):
        if network:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(503)

    client = OpenMeteoClient(
        transport=httpx.MockTransport(handler), sleep=delays.append
    )
    with pytest.raises(WeatherError, match="retries exhausted"):
        client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")
    assert client.requests_made == 4
    assert delays == [0.5, 1.0, 2.0]


def test_429_wait_is_bounded():
    delays = []
    codes = iter([429, 200])
    client = OpenMeteoClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                next(codes), headers={"Retry-After": "1000"}, json=response_payload()
            )
        ),
        sleep=delays.append,
    )
    client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")
    assert delays == [60]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "length",
        "unit",
        "timezone",
        "duplicate",
        "bad_time",
        "off_hour",
        "outside_range",
    ],
)
def test_invalid_responses_fail(mutation):
    payload = response_payload()
    if mutation == "missing":
        del payload["hourly"]["precipitation"]
    elif mutation == "length":
        payload["hourly"]["precipitation"] = []
    elif mutation == "unit":
        payload["hourly_units"]["temperature_2m"] = "F"
    elif mutation == "timezone":
        payload["utc_offset_seconds"] = 7200
    elif mutation == "duplicate":
        for key in payload["hourly"]:
            payload["hourly"][key] *= 2
    else:
        payload["hourly"]["time"] = [
            {
                "bad_time": "bad",
                "off_hour": "2024-01-01T10:30",
                "outside_range": "2024-01-02T10:00",
            }[mutation]
        ]
    client = client_for(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(WeatherError):
        client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")
    assert client.requests_made == 1


def test_invalid_json():
    client = client_for(lambda _: httpx.Response(200, content=b"invalid"))
    with pytest.raises(WeatherError, match="invalid JSON"):
        client.get_hourly(-26, 28, "2024-01-01", "2024-01-01")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("temperature_2m", float("inf")),
        ("temperature_2m", "12"),
        ("temperature_2m", True),
        ("relative_humidity_2m", -1),
        ("relative_humidity_2m", 101),
        ("precipitation", -0.1),
        ("wind_speed_10m", -0.1),
    ],
)
def test_invalid_values(variable, value):
    payload = response_payload()
    payload["hourly"][variable] = [value]
    with pytest.raises(WeatherError, match="structural weather value"):
        validate_response(payload)


def cached(client, root, latitude=-26.2):
    return get_cached_weather(
        client,
        root,
        location_id=225448,
        location_name="Test source",
        latitude=latitude,
        longitude=28,
        start_date="2024-01-01",
        end_date="2024-01-01",
    )


def test_raw_cache_and_normalization(tmp_path):
    client = client_for(lambda _: httpx.Response(200, json=response_payload()))
    envelope, hit = cached(client, tmp_path)
    assert not hit
    assert envelope["response"] == response_payload()
    assert envelope["request"]["latitude"] == -26.2
    assert envelope["request"]["location_id"] == 225448
    assert envelope["location_name"] == "Test source"
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    assert (
        files[0]
        .relative_to(tmp_path)
        .as_posix()
        .startswith("open_meteo/hourly/location_id=225448/2024-01-01__2024-01-01__")
    )
    assert json.loads(files[0].read_text(encoding="utf-8")) == envelope
    before = files[0].read_bytes()
    again, hit = cached(client, tmp_path)
    assert hit and again == envelope and client.requests_made == 1
    assert files[0].read_bytes() == before
    assert not list(tmp_path.rglob("*.tmp"))
    frame = normalize_weather(envelope)
    assert str(frame["weather_time_utc"].dt.tz) == "UTC"
    assert frame.iloc[0]["weather_time_utc"] == pd.Timestamp("2024-01-01T10:00Z")
    assert frame[METRICS].iloc[0].tolist() == [15.0, 55.0, 0.4, 12.5]
    assert frame.iloc[0]["weather_latitude"] == -26.2
    assert frame.iloc[0]["weather_source"] == "open_meteo"
    cached(client, tmp_path, latitude=-26.3)
    assert len(list(tmp_path.rglob("*.json"))) == 2
    assert client.requests_made == 2


def test_corrupt_cache_is_not_refreshed(tmp_path):
    client = client_for(lambda _: httpx.Response(200, json=response_payload()))
    cached(client, tmp_path)
    path = next(tmp_path.rglob("*.json"))
    path.write_text("invalid")
    with pytest.raises(WeatherError, match="Invalid raw weather cache"):
        cached(client, tmp_path)
    assert client.requests_made == 1
    assert path.read_text() == "invalid"


def test_cache_failed_publication_cleans_temp(tmp_path, monkeypatch):
    import airatlas.weather.storage as storage

    def fail(*args):
        raise OSError("simulated")

    monkeypatch.setattr(storage.os, "link", fail)
    with pytest.raises(OSError, match="simulated"):
        cached(
            client_for(lambda _: httpx.Response(200, json=response_payload())), tmp_path
        )
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.json"))


@pytest.fixture
def air_quality():
    row = dict.fromkeys(COLUMNS)
    row.update(
        source="openaq",
        location_id=225448,
        location_name="Station A",
        sensor_id=101,
        parameter="pm25",
        value=12.3,
        unit="ug/m3",
        latitude=-26.2,
        longitude=28.0,
        datetime_from_utc="2024-01-01T09:37:00Z",
        datetime_to_utc="2024-01-01T10:37:00Z",
        source_file="openaq/measurements/a.json",
    )
    second = {
        **row,
        "location_id": 225404,
        "location_name": "Station B",
        "sensor_id": 102,
        "parameter": "pm10",
        "latitude": -33.9,
        "longitude": 18.4,
        "datetime_from_utc": "2024-01-01T09:00:00Z",
        "datetime_to_utc": "2024-01-01T10:00:00Z",
    }
    third = {
        **row,
        "datetime_from_utc": "2024-01-01T10:30:00Z",
        "datetime_to_utc": "2024-01-01T11:30:00Z",
    }
    return pd.DataFrame([third, second, row], columns=COLUMNS)


def input_dataset(tmp_path, frame):
    csv = tmp_path / "processed/air_quality_observations.csv"
    csv.parent.mkdir(exist_ok=True)
    frame.to_csv(csv, index=False)
    result = build_curated_air_quality(csv, tmp_path / "curated")
    return Path(result["output_location"])


def enrich(tmp_path, input_dir, client, **kwargs):
    return enrich_air_quality_weather(
        client, input_dir, tmp_path / "raw", tmp_path / "curated", **kwargs
    )


def table_at(summary):
    return ds.dataset(
        summary["output_location"], format="parquet", partitioning="hive"
    ).to_table()


def test_coordinates(air_quality):
    actual = resolve_coordinates(
        air_quality, [{"id": 225448, "latitude": 1, "longitude": 1}]
    )
    assert actual == {225448: (-26.2, 28.0), 225404: (-33.9, 18.4)}
    air_quality["latitude"] = None
    air_quality["longitude"] = None
    config = [
        {"id": 225448, "latitude": -26.2, "longitude": 28},
        {"id": 225404, "coordinates": {"latitude": -33.9, "longitude": 18.4}},
    ]
    assert resolve_coordinates(air_quality, config) == actual
    with pytest.raises(MissingLocationCoordinatesError, match="225404"):
        resolve_coordinates(air_quality, config[:1])


def test_coordinate_conflict(air_quality):
    air_quality.loc[0, "latitude"] = -25.0
    with pytest.raises(WeatherError, match="Conflicting curated"):
        resolve_coordinates(air_quality, [])


def test_missing_coordinates_before_requests(tmp_path, air_quality):
    air_quality["latitude"] = None
    air_quality["longitude"] = None
    client = client_for(lambda _: pytest.fail("No request should occur"))
    with pytest.raises(MissingLocationCoordinatesError):
        enrich(tmp_path, input_dataset(tmp_path, air_quality), client)
    assert client.requests_made == 0
    assert not (tmp_path / "raw").exists()


def test_enrichment_location_hour_manifest_and_rebuild(tmp_path, air_quality):
    source = input_dataset(tmp_path, air_quality)
    original = {p: p.read_bytes() for p in source.rglob("*.parquet")}
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=response_payload(
                22 if float(request.url.params["latitude"]) < -30 else 15
            ),
        )

    client = client_for(handler)
    result = enrich(tmp_path, source, client)
    table = table_at(result)
    frame = table.to_pandas()
    assert len(frame) == len(air_quality)
    matched = frame.loc[frame["weather_source"].notna()].set_index("location_id")
    assert matched.loc[225448, "temperature_2m_c"] == 15
    assert matched.loc[225404, "temperature_2m_c"] == 22
    assert matched.loc[225448, "weather_hour_utc"] == pd.Timestamp("2024-01-01T10:00Z")
    unmatched = frame.loc[frame["weather_source"].isna()]
    assert len(unmatched) == 1 and unmatched[METRICS].isna().all().all()
    assert str(frame["weather_hour_utc"].dt.tz) == "UTC"
    assert set(COLUMNS) <= set(table.column_names)
    assert result["weather_matched_rows"] == 2
    assert result["weather_unmatched_rows"] == 1
    assert result["weather_match_percentage"] == pytest.approx(200 / 3)
    assert result["weather_rows_available"] == 2
    assert result["location_count"] == result["sensor_count"] == 2
    assert result["pm25_rows"] == 2 and result["pm10_rows"] == 1
    assert result["weather_variables"] == VARIABLES
    assert result["weather_api_requests"] == 2 and result["weather_cache_hits"] == 0
    for request in requests:
        assert (
            request.url.params["start_date"]
            == request.url.params["end_date"]
            == "2024-01-01"
        )
    dataset = Path(result["output_location"])
    assert {p.relative_to(dataset).as_posix() for p in dataset.rglob("*.parquet")} == {
        f"parameter={p}/measurement_date_utc=2024-01-01/part-00000.parquet"
        for p in ["pm25", "pm10"]
    }
    manifest_path = dataset.parent / "air_quality_weather_manifest.json"
    manifest = manifest_path.read_bytes()
    assert str(tmp_path) not in manifest.decode()
    assert json.loads(manifest)["weather_matched_rows"] == 2
    second = enrich(tmp_path, source, client)
    assert second["weather_api_requests"] == 0 and second["weather_cache_hits"] == 2
    assert table_at(second).equals(table)
    assert manifest_path.read_bytes() == manifest
    assert len(list(dataset.rglob("*.parquet"))) == 2
    assert not list((tmp_path / "curated").glob(".airatlas-curation-*"))
    assert all(p.read_bytes() == content for p, content in original.items())


@pytest.mark.parametrize("empty", [False, True])
def test_unavailable_weather_preserves_all_observations(tmp_path, air_quality, empty):
    payload = response_payload()
    for key in payload["hourly"]:
        if empty:
            payload["hourly"][key] = []
        elif key != "time":
            payload["hourly"][key] = [None]
    result = enrich(
        tmp_path,
        input_dataset(tmp_path, air_quality),
        client_for(lambda _: httpx.Response(200, json=payload)),
    )
    frame = table_at(result).to_pandas()
    assert len(frame) == 3
    assert frame[METRICS].isna().all().all()
    assert result["weather_matched_rows"] == 0
    assert result["weather_unmatched_rows"] == 3
    assert result["weather_match_percentage"] == 0


def test_partial_values_are_not_filled(tmp_path, air_quality):
    payload = response_payload()
    payload["hourly"]["precipitation"] = [None]
    result = enrich(
        tmp_path,
        input_dataset(tmp_path, air_quality),
        client_for(lambda _: httpx.Response(200, json=payload)),
    )
    assert result["weather_matched_rows"] == 2
    assert table_at(result).to_pandas()["precipitation_mm"].isna().all()


def test_failed_rebuild_keeps_old_snapshot(tmp_path, air_quality, monkeypatch):
    source = input_dataset(tmp_path, air_quality)
    client = client_for(lambda _: httpx.Response(200, json=response_payload()))
    result = enrich(tmp_path, source, client)
    original = table_at(result)

    def fail(*args):
        raise WeatherError("simulated validation failure")

    monkeypatch.setattr(enrichment, "_validate_written", fail)
    with pytest.raises(WeatherError, match="simulated"):
        enrich(tmp_path, source, client)
    assert table_at(result).equals(original)
    assert not list((tmp_path / "curated").glob(".airatlas-curation-*"))


def test_cli(tmp_path, air_quality, monkeypatch, capsys):
    import airatlas.weather.client as module

    source = input_dataset(tmp_path, air_quality)
    client = client_for(lambda _: httpx.Response(200, json=response_payload()))
    monkeypatch.setattr(module, "OpenMeteoClient", lambda: client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "enrich_air_quality_weather.py",
            "--input-dir",
            str(source),
            "--raw-weather-dir",
            str(tmp_path / "raw"),
            "--output-dir",
            str(tmp_path / "curated"),
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/enrich_air_quality_weather.py"
        ),
        run_name="__main__",
    )
    result = json.loads(capsys.readouterr().out)
    assert result["enriched_rows_written"] == 3
    assert result["weather_api_requests"] == 2


def test_date_ranges_are_derived_per_location(tmp_path, air_quality):
    air_quality.loc[0, "datetime_from_utc"] = "2024-01-03T10:30:00Z"
    air_quality.loc[0, "datetime_to_utc"] = "2024-01-03T11:30:00Z"
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=response_payload())

    enrich(tmp_path, input_dataset(tmp_path, air_quality), client_for(handler))
    by_latitude = {float(call["latitude"]): call for call in calls}
    assert by_latitude[-26.2]["start_date"] == "2024-01-01"
    assert by_latitude[-26.2]["end_date"] == "2024-01-03"
    assert (
        by_latitude[-33.9]["start_date"]
        == by_latitude[-33.9]["end_date"]
        == "2024-01-01"
    )


def test_coordinate_rounding_is_deterministic(air_quality):
    air_quality.loc[0, "latitude"] += 0.000001
    first = resolve_coordinates(air_quality, [])
    assert resolve_coordinates(air_quality.iloc[::-1], []) == first
    assert first[225448] == (-26.2, 28.0)


@pytest.mark.parametrize(
    ("latitude", "start", "end"),
    [
        (91, "2024-01-01", "2024-01-01"),
        (-26, "not-a-date", "2024-01-01"),
        (-26, "2024-01-02", "2024-01-01"),
    ],
)
def test_request_validation_before_network(latitude, start, end):
    client = client_for(lambda _: pytest.fail("No HTTP expected"))
    with pytest.raises(WeatherError):
        client.get_hourly(latitude, 28, start, end)
    assert client.requests_made == 0


def test_enrichment_rollback_after_publish_failure(tmp_path, air_quality, monkeypatch):
    source = input_dataset(tmp_path, air_quality)
    client = client_for(lambda _: httpx.Response(200, json=response_payload()))
    result = enrich(tmp_path, source, client)
    original = table_at(result)
    rename = Path.rename

    def fail(self, target):
        if self.name.startswith(".airatlas-curation-weather-"):
            raise OSError("publication failed")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="publication failed"):
        enrich(tmp_path, source, client)
    assert table_at(result).equals(original)
    assert not list((tmp_path / "curated").glob(".airatlas-curation-*"))


def test_readback_rejects_row_loss(tmp_path, air_quality, monkeypatch):
    original = enrichment._write_dataset

    def truncate(table, destination):
        original(table.slice(0, 1), destination)

    monkeypatch.setattr(enrichment, "_write_dataset", truncate)
    with pytest.raises(ValueError, match="read-back differs"):
        enrich(
            tmp_path,
            input_dataset(tmp_path, air_quality),
            client_for(lambda _: httpx.Response(200, json=response_payload())),
        )
    assert not (tmp_path / "curated/open_meteo_air_quality").exists()
