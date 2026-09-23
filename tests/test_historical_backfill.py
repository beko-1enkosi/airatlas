"""Offline historical backfill and CLI behaviour."""

import copy
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from airatlas.ingestion.historical_backfill import backfill_historical_measurements
from airatlas.ingestion.openaq import OpenAQClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return json.loads((ROOT / "config/mvp_locations.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    client = Mock(spec=OpenAQClient)
    client.get_all_location_sensors.return_value = {
        "meta": {"found": 4},
        "results": [
            {"id": 101, "name": "Unhelpful name", "parameter": {"name": "pm25"}},
            {"id": 102, "parameter": {"name": "pm10"}},
            {"id": 103, "name": "pm25", "parameter": {"name": "no2"}},
            {"id": 104, "parameter": {"name": "so2"}},
        ],
    }
    client.get_all_sensor_measurements.return_value = {
        "meta": {"found": 1, "page": 1, "limit": 1000},
        "results": [
            {
                "value": 12.3,
                "parameter": {"name": "pm25", "units": "ug/m3"},
                "period": {"datetimeFrom": {"utc": "2026-09-01T00:00:00Z"}},
                "flagInfo": {"hasFlags": False},
            }
        ],
    }
    return client


def test_sensor_selection_requests_and_source_preservation(client, config):
    source = client.get_all_sensor_measurements.return_value
    original = copy.deepcopy(source)
    location = config["locations"][0]
    result = backfill_historical_measurements(
        client, config, "2026-09-01", "2026-09-02", location_id=location["id"]
    )
    client.get_all_location_sensors.assert_called_once_with(location["id"])
    params = {
        "datetime_from": "2026-09-01",
        "datetime_to": "2026-09-02",
        "limit": 1000,
        "page": 1,
    }
    assert client.get_all_sensor_measurements.call_args_list == [
        call(101, params=params),
        call(102, params=params),
    ]
    assert [sensor["parameter"] for sensor in result["sensors"]] == ["pm25", "pm10"]
    for sensor in result["sensors"]:
        assert sensor["location_id"] == location["id"]
        assert sensor["location_name"] == location["name"]
        assert sensor["sensor_id"] in {101, 102}
        assert sensor["datetime_from"] == "2026-09-01"
        assert sensor["datetime_to"] == "2026-09-02"
        assert sensor["meta"] == original["meta"]
        assert sensor["results"] == original["results"]
        assert sensor["returned"] == 1
        assert sensor["incomplete"] is False
    assert source == original
    assert result["locations"][0]["missing_parameters"] == []


def test_all_configured_locations_and_missing_sensors(client, config):
    client.get_all_location_sensors.side_effect = [
        {"results": []},
        {"results": [{"id": 101, "parameter": {"name": "pm25"}}]},
        *[
            {"results": [{"id": 100, "parameter": None}]}
            for _ in config["locations"][2:]
        ],
    ]
    result = backfill_historical_measurements(
        client, config, "2026-09-01", "2026-09-02"
    )
    assert client.get_all_location_sensors.call_args_list == [
        call(location["id"]) for location in config["locations"]
    ]
    assert result["locations"][0]["missing_parameters"] == ["pm25", "pm10"]
    assert result["locations"][1]["missing_parameters"] == ["pm10"]
    assert len(result["locations"]) == len(config["locations"])
    assert len(result["sensors"]) == 1


@pytest.mark.parametrize(
    ("found", "incomplete"),
    [(2, True), ("2", True), (1, False), ("1", False), (None, None), (">1000", None)],
)
def test_measurement_completeness(client, config, found, incomplete):
    client.get_all_sensor_measurements.return_value["meta"]["found"] = found
    result = backfill_historical_measurements(
        client,
        config,
        "2026-09-01",
        "2026-09-02",
        location_id=config["locations"][0]["id"],
    )
    assert all(
        sensor["found"] == found and sensor["incomplete"] is incomplete
        for sensor in result["sensors"]
    )
    assert client.get_all_sensor_measurements.call_count == 2


def test_empty_history_continues(client, config):
    full = client.get_all_sensor_measurements.return_value
    client.get_all_sensor_measurements.side_effect = [
        {"meta": {"found": 0}, "results": []},
        full,
    ]
    result = backfill_historical_measurements(
        client,
        config,
        "2026-09-01",
        "2026-09-02",
        location_id=config["locations"][0]["id"],
    )
    empty, populated = result["sensors"]
    assert empty["results"] == []
    assert empty["returned"] == 0
    assert empty["incomplete"] is False
    assert populated["returned"] == 1


def test_absent_measurement_meta(client, config):
    client.get_all_sensor_measurements.return_value = {"results": []}
    result = backfill_historical_measurements(
        client,
        config,
        "2026-09-01",
        "2026-09-02",
        location_id=config["locations"][0]["id"],
    )
    assert all(
        sensor["meta"] is None and sensor["incomplete"] is None
        for sensor in result["sensors"]
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-02-30", "2026-09-02"),
        ("2026-09-01", "not-a-date"),
        ("20260901", "2026-09-02"),
        ("2026-09-01T00:00:00Z", "2026-09-02"),
        ("2026-09-03", "2026-09-02"),
    ],
)
def test_invalid_dates_fail_before_http(client, config, start, end):
    with pytest.raises(ValueError, match="dates|later"):
        backfill_historical_measurements(client, config, start, end)
    client.get_all_location_sensors.assert_not_called()
    client.get_all_sensor_measurements.assert_not_called()


def test_unknown_location_rejected(client, config):
    with pytest.raises(ValueError, match="approved MVP"):
        backfill_historical_measurements(
            client, config, "2026-09-01", "2026-09-02", location_id=-1
        )
    client.get_all_location_sensors.assert_not_called()


def test_cli_summary_without_payloads(client, config, monkeypatch, capsys, tmp_path):
    location_id = config["locations"][0]["id"]
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", lambda: client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backfill",
            "--date-from",
            "2026-09-01",
            "--date-to",
            "2026-09-02",
            "--location-id",
            str(location_id),
            "--output-dir",
            str(tmp_path),
        ],
    )
    runpy.run_path(
        str(ROOT / "scripts/backfill_openaq_measurements.py"), run_name="__main__"
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["locations_considered"] == 1
    assert summary["persistence"]["batches_written"] == 2
    assert len(list(tmp_path.rglob("*.json"))) == 2
    assert summary["matching_sensors_queried"] == 2
    assert summary["measurements_returned"] == 2
    assert summary["incomplete_responses"] == summary["empty_responses"] == 0
    assert {sensor["parameter"] for sensor in summary["sensors"]} == {"pm25", "pm10"}
    assert all("results" not in sensor for sensor in summary["sensors"])


def test_cli_unknown_location_before_client(monkeypatch, capsys):
    factory = Mock()
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", factory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backfill",
            "--date-from",
            "2026-09-01",
            "--date-to",
            "2026-09-02",
            "--location-id",
            "-1",
        ],
    )
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(ROOT / "scripts/backfill_openaq_measurements.py"), run_name="__main__"
        )
    assert error.value.code == 2
    assert "approved MVP" in capsys.readouterr().err
    factory.assert_not_called()


def test_equal_dates_rejected_before_http(client, config):
    with pytest.raises(
        ValueError, match="date_to must be strictly later than date_from"
    ) as error:
        backfill_historical_measurements(client, config, "2026-09-01", "2026-09-01")
    assert "For a one-day window, use 2026-09-01 to 2026-09-02." in str(error.value)
    client.get_all_location_sensors.assert_not_called()
    client.get_all_sensor_measurements.assert_not_called()
