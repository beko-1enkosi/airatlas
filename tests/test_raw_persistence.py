"""Raw storage tests use temporary output roots only."""

import copy
import json
import runpy
import sys
from pathlib import Path

import pytest

from airatlas.storage.raw import (
    RawPersistenceConflictError,
    RawPersistenceError,
    persist_raw_batch,
    persist_raw_run,
)


@pytest.fixture
def batch():
    return {
        "location_id": 225448,
        "location_name": "Jabavu-NAQI",
        "sensor_id": 101,
        "parameter": "pm25",
        "datetime_from": "2026-09-01T00:00:00Z",
        "datetime_to": "2026-09-01T01:00:00Z",
        "returned": 1,
        "found": 1,
        "incomplete": False,
        "meta": {"found": 1, "page": 1, "limit": 1000},
        "pagination": {
            "complete": True,
            "pages_fetched": 1,
            "requested_limit": 1000,
            "found": 1,
            "pages": [
                {
                    "page": 1,
                    "returned": 1,
                    "meta": {"found": 1},
                    "rate_limit": {"x-ratelimit-remaining": "50"},
                }
            ],
        },
        "results": [
            {
                "value": 12.3,
                "period": {"datetimeFrom": {"utc": "2026-09-01T00:00:00Z"}},
                "flagInfo": {"hasFlags": False},
            }
        ],
    }


def test_creation_provenance_and_source_preservation(batch, tmp_path):
    original = copy.deepcopy(batch)
    result = persist_raw_batch(batch, tmp_path)
    path = (
        tmp_path
        / "openaq/measurements/location_id=225448/parameter=pm25/sensor_id=101/20260901T000000Z__20260901T010000Z.json"
    )
    assert Path(result["path"]) == path
    assert result["status"] == "written"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["measurements"] == original["results"]
    assert stored["source_meta"] == original["meta"]
    for key in (
        "location_id",
        "location_name",
        "sensor_id",
        "parameter",
        "datetime_from",
        "datetime_to",
        "returned",
        "found",
    ):
        assert stored["retrieval"][key] == original[key]
    assert stored["retrieval"]["complete"] is True
    assert stored["retrieval"]["pages_fetched"] == 1
    assert stored["source_pages"][0]["meta"] == {"found": 1}
    assert batch == original
    assert not list(tmp_path.rglob("*.tmp"))


def test_idempotent_noop_and_semantic_json_equality(batch, tmp_path):
    first = persist_raw_batch(batch, tmp_path)
    path = Path(first["path"])
    # Whitespace and key ordering do not change JSON content.
    path.write_text(
        json.dumps(json.loads(path.read_text()), sort_keys=True), encoding="utf-8"
    )
    before = path.read_bytes()
    batch["pagination"]["pages"][0]["rate_limit"]["x-ratelimit-remaining"] = "49"
    second = persist_raw_batch(batch, tmp_path)
    assert first["path"] == second["path"]
    assert second["status"] == "reused"
    assert path.read_bytes() == before
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_conflict_preserves_original(batch, tmp_path):
    path = Path(persist_raw_batch(batch, tmp_path)["path"])
    before = path.read_bytes()
    batch["results"][0]["value"] = 99
    with pytest.raises(RawPersistenceConflictError):
        persist_raw_batch(batch, tmp_path)
    assert path.read_bytes() == before
    assert not list(tmp_path.rglob("*.tmp"))


def test_empty_complete_batch(batch, tmp_path):
    batch.update(results=[], returned=0, found=0, meta={"found": 0})
    batch["pagination"].update(
        found=0, pages=[{"page": 1, "returned": 0, "meta": {"found": 0}}]
    )
    path = Path(persist_raw_batch(batch, tmp_path)["path"])
    stored = json.loads(path.read_text())
    assert stored["measurements"] == []
    assert stored["retrieval"]["returned"] == 0


@pytest.mark.parametrize("incomplete", [True, None])
def test_incomplete_refused(batch, tmp_path, incomplete):
    batch["incomplete"] = incomplete
    with pytest.raises(RawPersistenceError, match="complete"):
        persist_raw_batch(batch, tmp_path)
    assert not list(tmp_path.iterdir())


def test_unresolved_pagination_refused(batch, tmp_path):
    batch["pagination"]["complete"] = False
    with pytest.raises(RawPersistenceError, match="Pagination"):
        persist_raw_batch(batch, tmp_path)


def test_unsafe_incremental_run(batch, tmp_path):
    with pytest.raises(RawPersistenceError, match="unsafe"):
        persist_raw_run({"checkpoint_safe": False, "sensors": [batch]}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_run_summary_override_and_no_checkpoint(batch, tmp_path):
    output = tmp_path / "custom-output"
    run = {
        "checkpoint": batch["datetime_from"],
        "checkpoint_safe": True,
        "next_checkpoint_candidate": batch["datetime_to"],
        "sensors": [batch],
    }
    first = persist_raw_run(run, output)
    second = persist_raw_run(run, output)
    assert first["batches_written"] == second["batches_reused"] == 1
    assert second["batches_written"] == first["batches_reused"] == 0
    assert first["measurements_represented"] == 1
    assert first["output_root"] == str(output.resolve())
    assert len(list(output.rglob("*.json"))) == 1
    assert all("checkpoint" not in path.name for path in output.rglob("*"))


def test_all_batches_prevalidated(batch, tmp_path):
    invalid = copy.deepcopy(batch)
    invalid.update(sensor_id=102, incomplete=True)
    with pytest.raises(RawPersistenceError):
        persist_raw_run({"sensors": [batch, invalid]}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_publication_failure_cleans_temporary(batch, tmp_path, monkeypatch):
    def fail_link(*args):
        raise OSError("simulated publication failure")

    monkeypatch.setattr("airatlas.storage.raw.os.link", fail_link)
    with pytest.raises(OSError):
        persist_raw_batch(batch, tmp_path)
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.json"))


def test_racing_conflict_does_not_overwrite(batch, tmp_path, monkeypatch):
    def race(source, target):
        Path(target).write_text('{"original": true}', encoding="utf-8")
        raise FileExistsError

    monkeypatch.setattr("airatlas.storage.raw.os.link", race)
    with pytest.raises(RawPersistenceConflictError):
        persist_raw_batch(batch, tmp_path)
    assert json.loads(next(tmp_path.rglob("*.json")).read_text()) == {"original": True}
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("parameter", ["../pm25", "pm25/other"])
def test_unsafe_path_refused(batch, tmp_path, parameter):
    batch["parameter"] = parameter
    with pytest.raises(RawPersistenceError):
        persist_raw_batch(batch, tmp_path)


def test_date_windows_and_equivalent_timestamps(batch, tmp_path):
    first = persist_raw_batch(batch, tmp_path)
    batch.update(
        datetime_from="2026-09-01T02:00:00+02:00",
        datetime_to="2026-09-01T03:00:00+02:00",
    )
    assert persist_raw_batch(batch, tmp_path)["path"] == first["path"]
    batch.update(datetime_from="2026-09-01", datetime_to="2026-09-02")
    assert (
        Path(persist_raw_batch(batch, tmp_path)["path"]).name
        == "20260901__20260902.json"
    )


def test_incremental_cli_refuses_unsafe_run(batch, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", lambda: object())
    monkeypatch.setattr(
        "airatlas.ingestion.incremental.ingest_incremental_measurements",
        lambda *args, **kwargs: {"checkpoint_safe": False, "sensors": [batch]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incremental",
            "--checkpoint",
            batch["datetime_from"],
            "--datetime-to",
            batch["datetime_to"],
            "--output-dir",
            str(tmp_path),
        ],
    )
    script = (
        Path(__file__).resolve().parents[1] / "scripts/ingest_incremental_openaq.py"
    )
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(script), run_name="__main__")
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "unsafe" in output.err
    assert not output.out
    assert not list(tmp_path.iterdir())


def test_invalid_existing_json_is_conflict(batch, tmp_path):
    path = Path(persist_raw_batch(batch, tmp_path)["path"])
    path.write_text("broken JSON", encoding="utf-8")
    with pytest.raises(RawPersistenceConflictError):
        persist_raw_batch(batch, tmp_path)
    assert path.read_text() == "broken JSON"


def test_subsecond_window_validation(batch, tmp_path):
    batch.update(
        datetime_from="2026-09-01T00:00:00.500000Z", datetime_to="2026-09-01T00:00:00Z"
    )
    with pytest.raises(RawPersistenceError, match="later"):
        persist_raw_batch(batch, tmp_path)
    assert not list(tmp_path.iterdir())
