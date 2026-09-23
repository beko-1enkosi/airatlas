"""Curated builds use temporary processed inputs and output roots only."""

import json
import runpy
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pytest

from airatlas.curation import parquet
from airatlas.curation.parquet import CurationInputError, build_curated_air_quality
from airatlas.processing.normalize import COLUMNS


@pytest.fixture
def observations():
    base = dict.fromkeys(COLUMNS)
    base.update(
        source="openaq",
        location_id=225448,
        location_name="NA",
        sensor_id=101,
        parameter="pm25",
        unit="ug/m3",
        value=-0.5,
        period_label="hour",
        period_interval="01:00:00",
        datetime_from_utc="2026-09-01T23:00:00Z",
        datetime_to_utc="2026-09-02T00:00:00Z",
        source_file="openaq/measurements/batch.json",
        retrieval_datetime_from="2026-09-01",
        retrieval_datetime_to="2026-09-03",
    )
    second = {
        **base,
        "sensor_id": 102,
        "parameter": "pm10",
        "parameter_id": 1,
        "location_id": 225404,
        "location_name": "Table View-NAQI",
        "value": 12.3,
        "datetime_from_utc": "2026-09-01T01:00:00+02:00",
        "datetime_to_utc": "2026-09-01T02:00:00+02:00",
    }
    third = {
        **base,
        "datetime_from_utc": "2026-09-02T00:00:00.000000001Z",
        "datetime_to_utc": "2026-09-02T01:00:00.000000001Z",
        "value": 0.0,
    }
    frame = pd.DataFrame([third, second, base], columns=COLUMNS)
    # Match Issue #14 CSV serialization: nullable IDs stay integers, not floats.
    for column in ("location_id", "sensor_id", "parameter_id"):
        frame[column] = frame[column].astype("Int64")
    return frame


def save(tmp_path, frame):
    path = tmp_path / "processed" / "openaq" / "air_quality_observations.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def read(result):
    return ds.dataset(
        result["output_location"], format="parquet", partitioning="hive"
    ).to_table()


def test_parquet_schema_partitions_and_manifest(tmp_path, observations):
    input_file = save(tmp_path, observations)
    before = input_file.read_bytes()
    result = build_curated_air_quality(input_file, tmp_path / "curated")
    table = read(result)
    frame = table.to_pandas()
    assert table.num_rows == 3
    assert len(pd.read_parquet(result["output_location"], engine="pyarrow")) == 3
    assert set(table.column_names) == set(COLUMNS) | {"measurement_date_utc"}
    for column in ("datetime_from_utc", "datetime_to_utc"):
        assert table.schema.field(column).type == pa.timestamp("ns", tz="UTC")
        assert str(frame[column].dt.tz) == "UTC"
    assert set(frame["parameter"]) == {"pm25", "pm10"}
    assert (
        frame["measurement_date_utc"].tolist()
        == frame["datetime_to_utc"].dt.strftime("%Y-%m-%d").tolist()
    )
    dataset = Path(result["output_location"])
    assert {
        path.relative_to(dataset).as_posix() for path in dataset.rglob("*.parquet")
    } == {
        "parameter=pm10/measurement_date_utc=2026-09-01/part-00000.parquet",
        "parameter=pm25/measurement_date_utc=2026-09-02/part-00000.parquet",
    }
    assert frame["latitude"].isna().all()
    assert frame["longitude"].isna().all()
    assert frame["datetime_from_local"].isna().all()
    assert frame["parameter_id"].isna().sum() == 2
    assert "NA" in frame["location_name"].tolist()
    assert table.schema.field("latitude").type == pa.float64()
    assert table.schema.field("parameter_id").type == pa.int64()
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["row_count"] == 3
    assert manifest["counts_by_parameter"] == {"pm25": 2, "pm10": 1}
    assert manifest["location_count"] == 2
    assert manifest["sensor_count"] == 2
    assert manifest["partition_columns"] == ["parameter", "measurement_date_utc"]
    assert manifest["partition_count"] == 2
    assert manifest["earliest_measurement_start_utc"] == "2026-08-31T23:00:00+00:00"
    assert (
        manifest["latest_measurement_end_utc"] == "2026-09-02T01:00:00.000000001+00:00"
    )
    assert manifest["columns"] == COLUMNS + ["measurement_date_utc"]
    assert manifest["processed_input_file"] == input_file.name
    assert str(tmp_path) not in json.dumps(manifest)
    assert input_file.read_bytes() == before


def test_rebuild_deterministic_and_removes_stale_partitions(tmp_path, observations):
    path = save(tmp_path, observations)
    output = tmp_path / "curated"
    first = build_curated_air_quality(path, output)
    original = read(first).sort_by([("datetime_to_utc", "ascending")])
    files = sorted(p.relative_to(output) for p in output.rglob("*.parquet"))
    manifest = Path(first["manifest_path"]).read_bytes()
    save(tmp_path, observations.iloc[::-1])
    second = build_curated_air_quality(path, output)
    assert read(second).sort_by([("datetime_to_utc", "ascending")]).equals(original)
    assert sorted(p.relative_to(output) for p in output.rglob("*.parquet")) == files
    assert Path(second["manifest_path"]).read_bytes() == manifest
    save(tmp_path, observations.loc[observations["parameter"] == "pm25"])
    third = build_curated_air_quality(path, output)
    assert read(third).num_rows == 2
    assert not list(output.rglob("parameter=pm10"))
    assert not list(output.glob(".airatlas-curation-*"))


@pytest.mark.parametrize("column", sorted(parquet.REQUIRED))
def test_missing_required_columns(tmp_path, observations, column):
    path = save(tmp_path, observations.drop(columns=column))
    with pytest.raises(CurationInputError, match="Missing required"):
        build_curated_air_quality(path, tmp_path / "curated")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("parameter", "no2", "Only pm25 and pm10"),
        ("parameter", None, "Only pm25 and pm10"),
        ("datetime_from_utc", "2026-09-01T00:00:00", "timezone-aware"),
        ("datetime_to_utc", "broken", "timezone-aware"),
        ("datetime_to_utc", "2025-01-01T00:00:00Z", "later than"),
        ("value", "inf", "finite numeric"),
        ("unit", None, "source unit"),
        ("location_id", "1.5", "positive integer"),
    ],
)
def test_invalid_input_fails(tmp_path, observations, column, value, message):
    observations[column] = observations[column].astype(object)
    observations.loc[0, column] = value
    path = save(tmp_path, observations)
    with pytest.raises(CurationInputError, match=message):
        build_curated_air_quality(path, tmp_path / "curated")
    assert not (tmp_path / "curated").exists()


def test_duplicates_rejected(tmp_path, observations):
    path = save(tmp_path, pd.concat([observations, observations.iloc[[0]]]))
    with pytest.raises(CurationInputError, match="Duplicate logical"):
        build_curated_air_quality(path, tmp_path / "curated")


def test_empty_input_preserves_existing_snapshot(tmp_path, observations):
    path = save(tmp_path, observations)
    output = tmp_path / "curated"
    result = build_curated_air_quality(path, output)
    original = read(result)
    save(tmp_path, observations.iloc[:0])
    with pytest.raises(CurationInputError, match="no observations"):
        build_curated_air_quality(path, output)
    assert read(result).equals(original)


def test_optional_columns_and_extra_provenance(tmp_path, observations):
    observations = observations.drop(columns=["latitude", "parameter_id"])
    observations["extra_provenance"] = "NA"
    result = build_curated_air_quality(
        save(tmp_path, observations), tmp_path / "curated"
    )
    table = read(result)
    assert "latitude" not in table.column_names
    assert table["extra_provenance"].to_pylist() == ["NA"] * 3


@pytest.mark.parametrize("operation", ["write", "readback", "backup", "publish"])
def test_failed_rebuild_preserves_previous_dataset(
    tmp_path, observations, monkeypatch, operation
):
    path = save(tmp_path, observations)
    output = tmp_path / "curated"
    result = build_curated_air_quality(path, output)
    original = read(result)
    manifest = Path(result["manifest_path"]).read_bytes()

    def fail(*args, **kwargs):
        raise OSError("simulated failure")

    if operation == "write":
        monkeypatch.setattr(parquet, "_write_dataset", fail)
    elif operation == "readback":
        monkeypatch.setattr(parquet, "_validate_written", fail)
    else:
        rename = Path.rename

        def fail_publish(self, target):
            if (
                operation == "publish"
                and self.name.startswith(".airatlas-curation-stage-")
            ) or (operation == "backup" and self == output / "openaq"):
                fail()
            return rename(self, target)

        monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(OSError, match="simulated failure"):
        build_curated_air_quality(path, output)
    assert read(result).equals(original)
    assert Path(result["manifest_path"]).read_bytes() == manifest
    assert not list(output.glob(".airatlas-curation-*"))


def test_readback_detects_lost_rows(tmp_path, observations, monkeypatch):
    original = parquet._write_dataset

    def truncate(table, destination):
        original(table.slice(0, 1), destination)

    monkeypatch.setattr(parquet, "_write_dataset", truncate)
    with pytest.raises(CurationInputError, match="read-back differs"):
        build_curated_air_quality(save(tmp_path, observations), tmp_path / "curated")
    assert not (tmp_path / "curated/openaq").exists()


def test_input_output_overlap_refused(tmp_path, observations):
    path = save(tmp_path, observations)
    before = path.read_bytes()
    with pytest.raises(CurationInputError, match="overlap"):
        build_curated_air_quality(path, tmp_path / "processed")
    assert path.read_bytes() == before


def test_unrelated_files_preserved(tmp_path, observations):
    output = tmp_path / "curated"
    (output / "openaq").mkdir(parents=True)
    other = output / "openaq/other.txt"
    other.write_text("keep")
    with pytest.raises(CurationInputError, match="unrelated"):
        build_curated_air_quality(save(tmp_path, observations), output)
    assert other.read_text() == "keep"


def test_cli_overrides(tmp_path, observations, monkeypatch, capsys):
    path = save(tmp_path, observations)
    output = tmp_path / "custom-curated"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_curated_air_quality.py",
            "--input-file",
            str(path),
            "--output-dir",
            str(output),
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1] / "scripts/build_curated_air_quality.py"
        ),
        run_name="__main__",
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["processed_rows_read"] == summary["curated_rows_written"] == 3
    assert summary["partition_count"] == 2
    assert Path(summary["output_location"]).is_relative_to(output)
