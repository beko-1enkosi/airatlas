"""Offline incremental-window and checkpoint-safety regression tests."""

import copy
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from airatlas.ingestion.incremental import ingest_incremental_measurements
from airatlas.ingestion.openaq import OpenAQClient, OpenAQClientError

ROOT = Path(__file__).resolve().parents[1]
START = "2026-09-01T00:00:00Z"
END = "2026-09-01T01:00:00Z"


@pytest.fixture
def config():
    return json.loads((ROOT / "config/mvp_locations.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    client = Mock(spec=OpenAQClient)
    client.get_all_location_sensors.return_value = {
        "meta": {"found": 3},
        "results": [
            {"id": 101, "parameter": {"name": "pm25"}},
            {"id": 102, "parameter": {"name": "pm10"}},
            {"id": 103, "parameter": {"name": "no2"}},
        ],
    }
    client.get_all_sensor_measurements.return_value = {
        "meta": {"found": 1},
        "results": [
            {
                "id": "source-record",
                "value": 12.3,
                "datetime": {"utc": START},
                "extra": {"preserved": True},
            }
        ],
    }
    return client


def test_narrow_window_provenance_and_candidate(client, config):
    original = copy.deepcopy(client.get_all_sensor_measurements.return_value)
    location = config["locations"][0]
    result = ingest_incremental_measurements(
        client, config, START, END, location_id=location["id"]
    )
    params = {"datetime_from": START, "datetime_to": END, "limit": 1000, "page": 1}
    assert client.get_all_sensor_measurements.call_args_list == [
        call(101, params=params),
        call(102, params=params),
    ]
    assert result["checkpoint"] == START
    assert result["next_checkpoint_candidate"] == END
    assert result["checkpoint_safe"] is True
    assert result["status"] == "complete"
    assert result["location_ids"] == [location["id"]]
    assert [sensor["parameter"] for sensor in result["sensors"]] == ["pm25", "pm10"]
    for sensor in result["sensors"]:
        assert sensor["location_id"] == location["id"]
        assert sensor["location_name"] == location["name"]
        assert sensor["sensor_id"] in {101, 102}
        assert sensor["results"] == original["results"]
        assert sensor["meta"] == original["meta"]
    assert client.get_all_sensor_measurements.return_value == original


def test_all_configured_locations(client, config):
    result = ingest_incremental_measurements(client, config, START, END)
    ids = [location["id"] for location in config["locations"]]
    assert client.get_all_location_sensors.call_args_list == [
        call(location_id) for location_id in ids
    ]
    assert result["location_ids"] == ids
    assert client.get_all_sensor_measurements.call_count == 2 * len(ids)
    assert result["checkpoint_safe"] is True


def test_timezone_offsets_normalized(client, config):
    result = ingest_incremental_measurements(
        client,
        config,
        "2026-09-01T02:00:00+02:00",
        "2026-09-01T03:00:00+02:00",
        location_id=config["locations"][0]["id"],
    )
    assert result["checkpoint"] == START
    assert result["next_checkpoint_candidate"] == END
    assert (
        client.get_all_sensor_measurements.call_args.kwargs["params"]["datetime_from"]
        == START
    )
    assert (
        client.get_all_sensor_measurements.call_args.kwargs["params"]["datetime_to"]
        == END
    )


@pytest.mark.parametrize(
    ("checkpoint", "end"),
    [
        (START, START),
        (END, START),
        (START, "2026-09-01T02:00:00+02:00"),
        ("2026-09-01T00:00:00", END),
        (START, "2026-09-01T01:00:00"),
        ("2026-09-01", END),
        (START, "invalid"),
    ],
)
def test_invalid_window_before_requests(client, config, checkpoint, end):
    with pytest.raises(ValueError, match="timezone|strictly later"):
        ingest_incremental_measurements(client, config, checkpoint, end)
    client.get_all_location_sensors.assert_not_called()
    client.get_all_sensor_measurements.assert_not_called()


def test_empty_complete_window_advances_candidate(client, config):
    client.get_all_sensor_measurements.return_value = {
        "meta": {"found": 0},
        "results": [],
    }
    result = ingest_incremental_measurements(client, config, START, END)
    assert all(sensor["returned"] == 0 for sensor in result["sensors"])
    assert result["checkpoint_safe"] is True
    assert result["next_checkpoint_candidate"] == END


@pytest.mark.parametrize("found", [2, "2", None, ">1000"])
def test_one_incomplete_or_unknown_response_is_unsafe(client, config, found):
    complete = copy.deepcopy(client.get_all_sensor_measurements.return_value)
    other = copy.deepcopy(complete)
    other["meta"]["found"] = found
    client.get_all_sensor_measurements.side_effect = [complete, other]
    result = ingest_incremental_measurements(
        client, config, START, END, location_id=config["locations"][0]["id"]
    )
    assert result["checkpoint_safe"] is False
    assert result["status"] == "not_complete"
    assert result["unsafe_reasons"]
    assert result["next_checkpoint_candidate"] == END
    assert client.get_all_sensor_measurements.call_count == 2


@pytest.mark.parametrize("found", [4, None])
def test_sensor_discovery_incomplete_or_unknown(client, config, found):
    client.get_all_location_sensors.return_value["meta"]["found"] = found
    result = ingest_incremental_measurements(client, config, START, END)
    assert result["checkpoint_safe"] is False
    assert any("sensor discovery" in reason for reason in result["unsafe_reasons"])


def test_missing_required_sensor(client, config):
    client.get_all_location_sensors.return_value = {
        "meta": {"found": 1},
        "results": [{"id": 101, "parameter": {"name": "pm25"}}],
    }
    result = ingest_incremental_measurements(client, config, START, END)
    assert all(
        location["missing_parameters"] == ["pm10"] for location in result["locations"]
    )
    assert result["checkpoint_safe"] is False
    assert all(sensor["parameter"] == "pm25" for sensor in result["sensors"])


def test_unknown_location_before_requests(client, config):
    with pytest.raises(ValueError, match="approved MVP"):
        ingest_incremental_measurements(client, config, START, END, location_id=-1)
    client.get_all_location_sensors.assert_not_called()


def test_http_failure_does_not_return_candidate(client, config):
    client.get_all_sensor_measurements.side_effect = OpenAQClientError(
        "HTTP communication failed"
    )
    with pytest.raises(OpenAQClientError):
        ingest_incremental_measurements(client, config, START, END)
    assert client.get_all_sensor_measurements.call_count == 1


def test_cli_summary(client, config, monkeypatch, capsys):
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", lambda: client)
    location_id = config["locations"][0]["id"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incremental",
            "--checkpoint",
            START,
            "--datetime-to",
            END,
            "--location-id",
            str(location_id),
        ],
    )
    runpy.run_path(
        str(ROOT / "scripts/ingest_incremental_openaq.py"), run_name="__main__"
    )
    output = json.loads(capsys.readouterr().out)
    assert output["locations_considered"] == 1
    assert output["measurements_by_parameter"] == {"pm25": 1, "pm10": 1}
    assert output["total_measurements"] == 2
    assert output["checkpoint_safe"] is True
    assert output["next_checkpoint_candidate"] == END
    assert output["location_ids"] == [location_id]
    assert "source-record" not in json.dumps(output)


@pytest.mark.parametrize(
    "args",
    [
        ["--checkpoint", START, "--datetime-to", START],
        ["--checkpoint", START, "--datetime-to", END, "--location-id", "-1"],
    ],
)
def test_cli_invalid_input_before_client(args, monkeypatch, capsys):
    factory = Mock()
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", factory)
    monkeypatch.setattr(sys, "argv", ["incremental", *args])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(ROOT / "scripts/ingest_incremental_openaq.py"), run_name="__main__"
        )
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err
    factory.assert_not_called()
