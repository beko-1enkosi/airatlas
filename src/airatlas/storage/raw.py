"""Deterministic, immutable raw JSON batches; no durable checkpoint state."""

import json
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


class RawPersistenceError(ValueError):
    """A batch or run cannot safely be persisted."""


class RawPersistenceConflictError(RawPersistenceError):
    """An existing raw snapshot differs from the requested content."""


def _boundary(value: str) -> tuple[str, str]:
    """Normalize a date or aware timestamp, retaining subsecond precision."""
    try:
        if "T" not in value:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
            normalized = parsed.isoformat()
        else:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
            normalized = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        raise RawPersistenceError(
            "Raw windows require ISO dates or timezone-aware timestamps."
        ) from None
    return normalized, normalized.replace("-", "").replace(":", "")


def _prepare_batch(batch: dict[str, Any], output_dir: Path) -> tuple[Path, dict]:
    if batch.get("incomplete") is not False:
        raise RawPersistenceError("Only complete sensor retrievals may be persisted.")
    pagination = batch.get("pagination")
    if pagination is not None and pagination.get("complete") is not True:
        raise RawPersistenceError("Pagination must be complete before persistence.")
    for field in ("location_id", "sensor_id"):
        if type(batch.get(field)) is not int or batch[field] <= 0:
            raise RawPersistenceError(f"{field} must be a positive OpenAQ integer ID.")
    parameter = batch.get("parameter")
    if not isinstance(parameter, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", parameter):
        raise RawPersistenceError("parameter must be a filesystem-safe name.")
    records = batch.get("results")
    if (
        not isinstance(records, list)
        or type(batch.get("returned")) is not int
        or batch["returned"] != len(records)
    ):
        raise RawPersistenceError(
            "returned must match the measurement collection length."
        )
    start, start_label = _boundary(batch["datetime_from"])
    end, end_label = _boundary(batch["datetime_to"])
    parse = datetime.fromisoformat if "T" in start else date.fromisoformat
    if ("T" in start) != ("T" in end) or parse(start) >= parse(end):
        raise RawPersistenceError(
            "Raw window end must be later than its start, using matching date formats."
        )
    target = (
        Path(output_dir)
        / "openaq"
        / "measurements"
        / f"location_id={batch['location_id']}"
        / f"parameter={parameter}"
        / f"sensor_id={batch['sensor_id']}"
        / f"{start_label}__{end_label}.json"
    )
    retrieval = {
        "location_id": batch["location_id"],
        "location_name": batch.get("location_name"),
        "sensor_id": batch["sensor_id"],
        "parameter": parameter,
        "datetime_from": start,
        "datetime_to": end,
        "returned": batch["returned"],
        "found": batch.get("found"),
        "complete": True,
    }
    envelope = {
        "source": "openaq",
        "resource": "measurements",
        "schema_version": 1,
        "retrieval": retrieval,
        "source_meta": batch.get("meta"),
        "measurements": records,
    }
    if pagination is not None:
        retrieval["pages_fetched"] = pagination["pages_fetched"]
        retrieval["requested_page_size"] = pagination["requested_limit"]
        retrieval["found"] = pagination.get("found")
        # Rate-limit counters vary between identical retrievals and are not source data.
        envelope["source_pages"] = [
            {key: page[key] for key in ("page", "meta", "returned")}
            for page in pagination["pages"]
        ]
    return target, envelope


def _existing_matches(target: Path, envelope: dict) -> bool:
    try:
        content = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (ValueError, UnicodeError):
        raise RawPersistenceConflictError(
            f"Existing raw batch is not valid JSON: {target}"
        ) from None
    if content != envelope:
        raise RawPersistenceConflictError(
            f"Different content already exists at raw path: {target}"
        )
    return True


def _write_batch(target: Path, envelope: dict) -> str:
    # Serialize before creating directories or temporary files.
    encoded = json.dumps(envelope, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if _existing_matches(target, envelope):
        return "reused"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=".airatlas-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic publication without overwrite: an existing destination wins even
        # if another writer created it after our initial existence check.
        try:
            os.link(temporary, target)
        except FileExistsError:
            _existing_matches(target, envelope)
            return "reused"
        return "written"
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def persist_raw_batch(batch: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write or reuse one complete raw snapshot; conflicting content is immutable.

    Publication requires a filesystem supporting same-directory hard links.
    A failure is surfaced rather than falling back to a non-atomic overwrite.
    """
    target, envelope = _prepare_batch(batch, output_dir)
    return {
        "path": str(target),
        "status": _write_batch(target, envelope),
        "returned": batch["returned"],
    }


def persist_raw_run(result: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Persist batches after validating the run; never write a checkpoint.

    Incremental runs must explicitly permit checkpoint advancement. Writes are
    atomic per file, not a transaction across files. A later I/O failure can
    leave complete earlier batches; rerunning reuses those identical snapshots.
    The caller must not commit a checkpoint if this function raises.
    """
    if "checkpoint" in result and result.get("checkpoint_safe") is not True:
        raise RawPersistenceError(
            "Incremental checkpoint is unsafe; raw run persistence refused."
        )
    if "checkpoint_safe" in result and result["checkpoint_safe"] is not True:
        raise RawPersistenceError(
            "Incremental checkpoint is unsafe; raw run persistence refused."
        )
    prepared = [_prepare_batch(batch, output_dir) for batch in result["sensors"]]
    # Check all batches and known conflicts before writing any part of the run.
    targets = {}
    for target, envelope in prepared:
        json.dumps(envelope, allow_nan=False)
        if target in targets and targets[target] != envelope:
            raise RawPersistenceConflictError(
                f"Conflicting batches target the same raw path: {target}"
            )
        targets[target] = envelope
        _existing_matches(target, envelope)
    statuses = [_write_batch(target, envelope) for target, envelope in prepared]
    return {
        "batches_written": statuses.count("written"),
        "batches_reused": statuses.count("reused"),
        "measurements_represented": sum(
            batch["returned"] for batch in result["sensors"]
        ),
        "output_root": str(Path(output_dir).resolve()),
    }
