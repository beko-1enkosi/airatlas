"""Incremental retrieval from an explicit checkpoint, without durable state."""

from datetime import UTC, datetime
from typing import Any

from airatlas.ingestion.measurement_window import fetch_measurement_window
from airatlas.ingestion.openaq import OpenAQClient


def normalize_incremental_window(checkpoint: str, datetime_to: str) -> tuple[str, str]:
    """Accept timezone-aware ISO timestamps and normalize to UTC with Z."""
    timestamps = []
    for value in (checkpoint, datetime_to):
        try:
            if not isinstance(value, str) or "T" not in value:
                raise ValueError
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError
            timestamps.append(timestamp.astimezone(UTC))
        except (ValueError, TypeError, OverflowError):
            raise ValueError(
                "checkpoint and datetime_to must be ISO timestamps with a timezone, "
                "for example 2026-09-01T00:00:00Z."
            ) from None
    start, end = timestamps
    if end <= start:
        raise ValueError("datetime_to must be strictly later than checkpoint.")
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace(
        "+00:00", "Z"
    )


def ingest_incremental_measurements(
    client: OpenAQClient,
    config: dict[str, Any],
    checkpoint: str,
    datetime_to: str,
    *,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Retrieve only the supplied window and assess a next checkpoint candidate.

    The candidate is the requested upper boundary, even for empty responses.
    Safety applies ONLY to the returned location_ids, not unqueried stations.
    All sensor discovery and measurement responses must be known complete, and
    both required pollutants must be present. HTTP failures propagate without
    returning a candidate. The caller must persist records successfully before
    committing a safe candidate, and handle inclusive boundary repeats
    idempotently. No records are dropped or checkpoints persisted here.
    """
    start, end = normalize_incremental_window(checkpoint, datetime_to)
    result = fetch_measurement_window(
        client, config, start, end, location_id=location_id
    )
    unsafe_reasons = []
    if not result["locations"]:
        unsafe_reasons.append("No configured locations were processed.")
    for location in result["locations"]:
        if location["missing_parameters"]:
            unsafe_reasons.append(
                f"Location {location['location_id']} is missing required sensors."
            )
        if location["sensor_discovery_incomplete"] is not False:
            unsafe_reasons.append(
                f"Location {location['location_id']} sensor discovery is incomplete or unknown."
            )
    for sensor in result["sensors"]:
        if sensor["incomplete"] is not False:
            unsafe_reasons.append(
                f"Sensor {sensor['sensor_id']} measurement completeness is incomplete or unknown."
            )
    result.update(
        {
            "checkpoint": start,
            "next_checkpoint_candidate": end,
            "checkpoint_safe": not unsafe_reasons,
            "status": "complete" if not unsafe_reasons else "not_complete",
            "unsafe_reasons": unsafe_reasons,
            "location_ids": [
                location["location_id"] for location in result["locations"]
            ],
        }
    )
    return result
