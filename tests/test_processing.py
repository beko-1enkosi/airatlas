"""Processing tests create raw and derived artifacts only in temporary directories."""

import copy
import json
import runpy
import sys
from pathlib import Path

import pandas as pd
import pytest

from airatlas.processing.loader import (
    ProcessingInputError,
    discover_raw_batches,
    load_raw_batch,
)
from airatlas.processing.normalize import COLUMNS, normalize_measurement
from airatlas.processing.pipeline import (
    DataQualityConflictError,
    build_processed_snapshot,
    process_air_quality,
)
from airatlas.storage.raw import persist_raw_batch


@pytest.fixture
def measurement():
    return {
        "value": 12.3,
        "parameter": {
            "id": 2,
            "name": "pm25",
            "units": "ug/m3",
            "displayName": "PM2.5",
        },
        "period": {
            "label": "hour",
            "interval": "01:00:00",
            "datetimeFrom": {
                "utc": "2026-09-01T00:00:00Z",
                "local": "2026-09-01T02:00:00+02:00",
            },
            "datetimeTo": {
                "utc": "2026-09-01T01:00:00Z",
                "local": "2026-09-01T03:00:00+02:00",
            },
        },
        "coordinates": None,
        "flagInfo": {"hasFlags": False},
    }


def write_batch(root, records, *, start="2026-09-01", parameter="pm25", sensor_id=101):
    batch = {
        "location_id": 225448,
        "location_name": "Jabavu-NAQI",
        "sensor_id": sensor_id,
        "parameter": parameter,
        "datetime_from": start,
        "datetime_to": "2026-09-03",
        "returned": len(records),
        "found": len(records),
        "incomplete": False,
        "meta": {"found": len(records)},
        "results": records,
    }
    return Path(persist_raw_batch(batch, root)["path"])


def test_loading_and_deterministic_discovery(tmp_path, measurement):
    late = write_batch(tmp_path, [measurement], start="2026-09-02")
    early = write_batch(tmp_path, [measurement])
    (tmp_path / "unrelated.json").write_text("broken")
    assert discover_raw_batches(tmp_path) == [early, late]
    assert load_raw_batch(early, tmp_path)["measurements"] == [measurement]


@pytest.mark.parametrize("content", ["{broken", "[]", "{}"])
def test_invalid_raw_identifies_file(tmp_path, measurement, content):
    path = write_batch(tmp_path, [measurement])
    path.write_text(content)
    with pytest.raises(ProcessingInputError) as error:
        build_processed_snapshot(tmp_path)
    assert path.name in str(error.value)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize(
    "field", ["location_id", "sensor_id", "datetime_from", "parameter"]
)
def test_missing_batch_provenance_fails(tmp_path, measurement, field):
    path = write_batch(tmp_path, [measurement])
    batch = json.loads(path.read_text())
    del batch["retrieval"][field]
    path.write_text(json.dumps(batch))
    with pytest.raises(ProcessingInputError, match="envelope/provenance"):
        build_processed_snapshot(tmp_path)


def test_normalization_and_provenance(tmp_path, measurement):
    path = write_batch(tmp_path, [measurement])
    frame, report = build_processed_snapshot(tmp_path)
    row = frame.iloc[0]
    assert frame.columns.tolist() == COLUMNS
    assert row["source"] == "openaq"
    assert row["location_id"] == 225448
    assert row["sensor_id"] == 101
    assert row["location_name"] == "Jabavu-NAQI"
    assert row["parameter_id"] == 2
    assert row["unit"] == "ug/m3"
    assert row["value"] == 12.3
    assert row["period_label"] == "hour"
    assert row["period_interval"] == "01:00:00"
    assert row["datetime_from_utc"] == pd.Timestamp("2026-09-01T00:00:00Z")
    assert row["datetime_to_utc"] == pd.Timestamp("2026-09-01T01:00:00Z")
    assert str(frame["datetime_from_utc"].dt.tz) == "UTC"
    assert str(frame["datetime_to_utc"].dt.tz) == "UTC"
    assert row["datetime_from_local"] == measurement["period"]["datetimeFrom"]["local"]
    assert pd.isna(row["latitude"]) and pd.isna(row["longitude"])
    assert row["source_file"] == path.relative_to(tmp_path).as_posix()
    assert row["retrieval_datetime_from"] == "2026-09-01"
    assert row["retrieval_datetime_to"] == "2026-09-03"
    assert report["final_processed_row_count"] == 1


@pytest.mark.parametrize("name", ["pm25", "pm10", " PM25 "])
def test_supported_parameters(tmp_path, measurement, name):
    measurement["parameter"]["name"] = name
    write_batch(tmp_path, [measurement], parameter=name.strip().lower())
    frame, _ = build_processed_snapshot(tmp_path)
    assert frame.iloc[0]["parameter"] == name.strip().lower()


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("parameter", "name"), "no2", "invalid_parameter"),
        (("parameter", "name"), "pm10", "parameter_mismatch"),
        (("parameter", "units"), None, "missing_unit"),
        (("parameter", "units"), " ", "missing_unit"),
        (("parameter", "id"), False, "invalid_identifier"),
        (("value",), None, "invalid_value"),
        (("value",), "12.3", "invalid_value"),
        (("value",), True, "invalid_value"),
        (("value",), float("nan"), "invalid_value"),
        (("value",), float("inf"), "invalid_value"),
        (("period", "datetimeFrom", "utc"), "bad", "invalid_timestamp"),
        (("period", "datetimeFrom", "utc"), "2026-09-01T00:00:00", "invalid_timestamp"),
        (("period", "datetimeTo", "utc"), "2026-09-01T00:00:00Z", "invalid_period"),
        (("period", "datetimeTo", "utc"), "2026-08-31T00:00:00Z", "invalid_period"),
        (("period",), None, "missing_required_field"),
    ],
)
def test_invalid_records_rejected(tmp_path, measurement, path, value, reason):
    target = measurement
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    # JSON permits non-finite tokens in Python, but record validation rejects them.
    batch_path = write_batch(tmp_path, [])
    envelope = json.loads(batch_path.read_text())
    envelope["measurements"] = [measurement]
    envelope["retrieval"]["returned"] = 1
    batch_path.write_text(json.dumps(envelope))
    frame, report = build_processed_snapshot(tmp_path)
    assert frame.empty
    assert report["rejection_counts_by_reason"] == {reason: 1}
    assert report["invalid_observations_rejected"] == 1


@pytest.mark.parametrize("identifier", [0, -1, True, "101", None])
def test_invalid_identifier(measurement, identifier):
    retrieval = {"location_id": identifier, "sensor_id": 101}
    assert (
        normalize_measurement(measurement, retrieval, "batch.json")[2]
        == "invalid_identifier"
    )


def test_negative_and_quality_counts(tmp_path, measurement):
    measurement["value"] = -0.5
    invalid = copy.deepcopy(measurement)
    invalid["value"] = None
    write_batch(tmp_path, [measurement, invalid, measurement])
    frame, report = build_processed_snapshot(tmp_path)
    assert frame.iloc[0]["value"] == -0.5
    assert report == {
        "raw_files_discovered": 1,
        "raw_measurement_records_read": 3,
        "valid_observations_before_deduplication": 2,
        "invalid_observations_rejected": 1,
        "rejection_counts_by_reason": {"invalid_value": 1},
        "identical_duplicates_removed": 1,
        "final_processed_row_count": 1,
        "negative_measurement_count": 1,
        "counts_by_parameter": {"pm25": 1, "pm10": 0},
        "observed_units_by_parameter": {"pm25": ["ug/m3"], "pm10": []},
    }


def test_overlap_deduplication(tmp_path, measurement):
    first = write_batch(tmp_path, [measurement])
    write_batch(tmp_path, [measurement], start="2026-09-02")
    frame, report = build_processed_snapshot(tmp_path)
    assert len(frame) == 1
    assert frame.iloc[0]["source_file"] == first.relative_to(tmp_path).as_posix()
    assert report["identical_duplicates_removed"] == 1


@pytest.mark.parametrize("change", ["value", "unit", "metadata"])
def test_conflicts_fail_before_replacing_snapshot(tmp_path, measurement, change):
    raw, output = tmp_path / "raw", tmp_path / "processed"
    write_batch(raw, [measurement])
    result = process_air_quality(raw, output)
    before = Path(result["csv_path"]).read_bytes()
    if change == "value":
        measurement["value"] = 99
    elif change == "unit":
        measurement["parameter"]["units"] = "mg/m3"
    else:
        measurement["parameter"]["id"] = 99
    write_batch(raw, [measurement], start="2026-09-02")
    with pytest.raises(DataQualityConflictError, match="location=225448, sensor=101"):
        process_air_quality(raw, output)
    assert Path(result["csv_path"]).read_bytes() == before


def test_outputs_reproducible_sorted_and_raw_unchanged(tmp_path, measurement):
    raw, output = tmp_path / "raw", tmp_path / "processed"
    second = copy.deepcopy(measurement)
    second["period"]["datetimeFrom"]["utc"] = "2026-09-01T01:00:00Z"
    second["period"]["datetimeTo"]["utc"] = "2026-09-01T02:00:00Z"
    path = write_batch(raw, [second, measurement])
    original = path.read_bytes()
    result = process_air_quality(raw, output)
    csv_path, report_path = Path(result["csv_path"]), Path(result["report_path"])
    assert csv_path == output / "openaq/air_quality_observations.csv"
    frame = pd.read_csv(csv_path)
    assert frame.columns.tolist() == COLUMNS
    assert frame["datetime_from_utc"].tolist() == sorted(frame["datetime_from_utc"])
    assert json.loads(report_path.read_text()) == result["quality"]
    before = csv_path.read_bytes(), report_path.read_bytes()
    process_air_quality(raw, output)
    assert before == (csv_path.read_bytes(), report_path.read_bytes())
    assert path.read_bytes() == original
    assert not list(output.rglob("*.tmp"))


def test_empty_batch_writes_header_and_zero_report(tmp_path):
    write_batch(tmp_path / "raw", [])
    result = process_air_quality(tmp_path / "raw", tmp_path / "out")
    assert pd.read_csv(result["csv_path"]).empty
    assert result["quality"]["raw_files_discovered"] == 1
    assert result["quality"]["final_processed_row_count"] == 0


def test_no_input_clear_error(tmp_path):
    with pytest.raises(ProcessingInputError, match="No OpenAQ measurement"):
        process_air_quality(tmp_path / "raw", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_overlapping_roots_rejected(tmp_path, measurement):
    write_batch(tmp_path, [measurement])
    with pytest.raises(ProcessingInputError, match="overlap"):
        process_air_quality(tmp_path, tmp_path / "processed")


def test_cli_overrides(tmp_path, measurement, monkeypatch, capsys):
    raw, output = tmp_path / "raw", tmp_path / "processed"
    write_batch(raw, [measurement])
    monkeypatch.setattr(
        sys,
        "argv",
        ["process_air_quality.py", "--raw-dir", str(raw), "--output-dir", str(output)],
    )
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/process_air_quality.py"),
        run_name="__main__",
    )
    result = json.loads(capsys.readouterr().out)
    assert result["quality"]["final_processed_row_count"] == 1
    assert Path(result["csv_path"]).exists()


def test_offset_timestamps_and_source_units(tmp_path, measurement):
    measurement["period"]["datetimeFrom"]["utc"] = "2026-09-01T02:00:00+02:00"
    measurement["parameter"]["units"] = "\u00b5g/m\u00b3"
    measurement["coordinates"] = {"latitude": -26.2, "longitude": 28.0}
    write_batch(tmp_path, [measurement])
    frame, report = build_processed_snapshot(tmp_path)
    assert frame.iloc[0]["datetime_from_utc"] == pd.Timestamp("2026-09-01T00:00:00Z")
    assert frame.iloc[0]["latitude"] == -26.2
    assert report["observed_units_by_parameter"]["pm25"] == ["\u00b5g/m\u00b3"]


def test_failed_write_cleans_temporary_files(tmp_path, measurement, monkeypatch):
    raw, output = tmp_path / "raw", tmp_path / "out"
    write_batch(raw, [measurement])

    def fail(*args, **kwargs):
        raise OSError("Simulated write failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail)
    with pytest.raises(OSError, match="Simulated"):
        process_air_quality(raw, output)
    assert not list(output.rglob("*.tmp"))
    assert not list(output.rglob("*.csv"))
