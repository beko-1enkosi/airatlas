"""Rebuild a deterministic processed snapshot; raw evidence is read-only."""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from airatlas.processing.loader import (
    ProcessingInputError,
    discover_raw_batches,
    load_raw_batch,
)
from airatlas.processing.normalize import (
    COLUMNS,
    KEY,
    normalize_measurement,
    observation_frame,
)


class DataQualityConflictError(ValueError):
    """The same observation identity has conflicting source content."""


def build_processed_snapshot(raw_dir: Path):
    """Validate, deduplicate and return a DataFrame and path-free quality counts.

    First rejection reason per record is counted. Final parameter/unit/negative
    counts describe deduplicated rows. Duplicate provenance uses the first file
    in sorted relative-path order; every original remains available in raw.
    """
    root = Path(raw_dir).resolve()
    paths = discover_raw_batches(root)
    observations, signatures = {}, {}
    reasons = Counter()
    read = valid = duplicates = 0
    for path in paths:
        batch = load_raw_batch(path, root)
        source_file = path.relative_to(root).as_posix()
        for record in batch["measurements"]:
            read += 1
            row, signature, reason = normalize_measurement(
                record, batch["retrieval"], source_file
            )
            if reason:
                reasons[reason] += 1
                continue
            valid += 1
            key = tuple(row[column] for column in KEY)
            if key in observations:
                if signatures[key] != signature:
                    raise DataQualityConflictError(
                        f"Conflicting observation: location={key[0]}, sensor={key[1]}, parameter={key[2]}, period={key[3].isoformat()} to {key[4].isoformat()}"
                    )
                duplicates += 1
            else:
                observations[key], signatures[key] = row, signature
    frame = observation_frame(list(observations.values()))
    frame = frame.sort_values(
        [
            "datetime_from_utc",
            "datetime_to_utc",
            "location_id",
            "sensor_id",
            "parameter",
        ],
        kind="stable",
    ).reset_index(drop=True)
    report = {
        "raw_files_discovered": len(paths),
        "raw_measurement_records_read": read,
        "valid_observations_before_deduplication": valid,
        "invalid_observations_rejected": sum(reasons.values()),
        "rejection_counts_by_reason": dict(sorted(reasons.items())),
        "identical_duplicates_removed": duplicates,
        "final_processed_row_count": len(frame),
        "negative_measurement_count": int((frame["value"] < 0).sum()),
        "counts_by_parameter": {
            parameter: int((frame["parameter"] == parameter).sum())
            for parameter in ("pm25", "pm10")
        },
        "observed_units_by_parameter": {
            parameter: sorted(
                frame.loc[frame["parameter"] == parameter, "unit"].unique().tolist()
            )
            for parameter in ("pm25", "pm10")
        },
    }
    return frame, report


def process_air_quality(raw_dir: Path, output_dir: Path) -> dict:
    """Replace rebuildable outputs atomically per file, not as a two-file transaction.

    All validation/conflict checks finish before either output is touched. Both
    temporary files are staged before publication; rerun after an I/O failure.
    Reject overlapping input/output roots to protect immutable raw evidence.
    """
    root, output = Path(raw_dir).resolve(), Path(output_dir).resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ProcessingInputError("Raw and processed output roots must not overlap.")
    destination = (output / "openaq").resolve()
    if not destination.is_relative_to(output) or destination.is_relative_to(root):
        raise ProcessingInputError(
            "Processed destination must remain inside the output root."
        )
    frame, report = build_processed_snapshot(root)
    destination.mkdir(parents=True, exist_ok=True)
    targets = [
        destination / "air_quality_observations.csv",
        destination / "quality_report.json",
    ]
    temporary = []
    try:
        for index, _target in enumerate(targets):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=destination,
                prefix=".airatlas-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary.append(Path(stream.name))
                if index == 0:
                    # ISO timestamps retain UTC offsets and subsecond precision.
                    frame.to_csv(
                        stream, index=False, columns=COLUMNS, lineterminator="\n"
                    )
                else:
                    json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
                    stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        for source, target in zip(temporary, targets, strict=True):
            os.replace(source, target)
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return {
        "quality": report,
        "csv_path": str(targets[0]),
        "report_path": str(targets[1]),
    }
