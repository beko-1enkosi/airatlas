"""Read only AirAtlas measurement envelopes, without altering raw files."""

import json
from datetime import date, datetime
from pathlib import Path


class ProcessingInputError(ValueError):
    """A raw batch or input root cannot safely be processed."""


def discover_raw_batches(raw_dir: Path) -> list[Path]:
    root = Path(raw_dir).resolve()
    paths = sorted((root / "openaq" / "measurements").rglob("*.json"))
    if not paths:
        raise ProcessingInputError("No OpenAQ measurement raw batches found.")
    for path in paths:
        if not path.resolve().is_relative_to(root):
            raise ProcessingInputError(
                "Raw batch symlinks must remain inside the raw root."
            )
    return paths


def load_raw_batch(path: Path, raw_dir: Path) -> dict:
    """Validate envelope structure; individual measurement validation is separate."""
    relative = path.relative_to(Path(raw_dir).resolve()).as_posix()
    try:
        batch = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(batch, dict):
            raise ValueError("expected an object")
        if (
            batch.get("source") != "openaq"
            or batch.get("resource") != "measurements"
            or type(batch.get("schema_version")) is not int
            or batch["schema_version"] != 1
        ):
            raise ValueError("unsupported raw envelope")
        retrieval = batch.get("retrieval")
        fields = {
            "location_id",
            "sensor_id",
            "parameter",
            "datetime_from",
            "datetime_to",
            "returned",
            "complete",
        }
        if not isinstance(retrieval, dict) or not fields <= retrieval.keys():
            raise ValueError("missing essential retrieval provenance")
        records = batch.get("measurements")
        if (
            not isinstance(records, list)
            or type(retrieval["returned"]) is not int
            or retrieval["returned"] != len(records)
        ):
            raise ValueError("invalid measurements or returned count")
        if retrieval["complete"] is not True:
            raise ValueError("raw retrieval is not complete")
        if "source_meta" not in batch or (
            batch["source_meta"] is not None
            and not isinstance(batch["source_meta"], dict)
        ):
            raise ValueError("invalid source_meta")
        if "source_pages" in batch and (
            not isinstance(batch["source_pages"], list)
            or any(not isinstance(page, dict) for page in batch["source_pages"])
        ):
            raise ValueError("invalid source_pages")
        if (
            not isinstance(retrieval["parameter"], str)
            or not retrieval["parameter"].strip()
        ):
            raise ValueError("missing retrieval parameter")
        if retrieval.get("location_name") is not None and not isinstance(
            retrieval["location_name"], str
        ):
            raise ValueError("invalid location name")
        boundaries = []
        for key in ("datetime_from", "datetime_to"):
            value = retrieval[key]
            if not isinstance(value, str):
                raise ValueError("invalid retrieval window")
            parsed = (
                datetime.fromisoformat(value)
                if "T" in value
                else date.fromisoformat(value)
            )
            if isinstance(parsed, datetime) and parsed.tzinfo is None:
                raise ValueError("naive retrieval timestamp")
            boundaries.append(parsed)
        if (
            type(boundaries[0]) is not type(boundaries[1])
            or boundaries[1] <= boundaries[0]
        ):
            raise ValueError("invalid retrieval window")
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        # Do not echo JSON contents or absolute paths from underlying exceptions.
        reason = (
            "unreadable or invalid JSON"
            if isinstance(exc, (json.JSONDecodeError, OSError, UnicodeError))
            else "invalid raw envelope/provenance"
        )
        raise ProcessingInputError(f"{relative}: {reason}") from None
    return batch
