"""One observation per source period; validation returns one reason per rejection.

Units are preserved, never converted. UTC is explicit; local timestamps remain
source strings. Optional metadata stays null. No scientific range filter is used.
"""

import copy
import json
import math

import pandas as pd

COLUMNS = [
    "source",
    "location_id",
    "location_name",
    "sensor_id",
    "parameter",
    "parameter_id",
    "unit",
    "value",
    "period_label",
    "period_interval",
    "datetime_from_utc",
    "datetime_to_utc",
    "datetime_from_local",
    "datetime_to_local",
    "latitude",
    "longitude",
    "source_file",
    "retrieval_datetime_from",
    "retrieval_datetime_to",
]
KEY = ["location_id", "sensor_id", "parameter", "datetime_from_utc", "datetime_to_utc"]


def _identifier(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def normalize_measurement(record, retrieval, source_file):
    """Return (row, comparison signature, rejection reason).

    Exact deduplication compares all original source fields after normalizing
    parameter case and UTC representations; retrieval provenance is excluded.
    This conservatively fails on changed source metadata rather than discarding it.
    """
    if not isinstance(record, dict):
        return None, None, "missing_required_field"
    if not all(_identifier(retrieval.get(key)) for key in ("location_id", "sensor_id")):
        return None, None, "invalid_identifier"
    parameter = record.get("parameter")
    period = record.get("period")
    if not isinstance(parameter, dict) or not isinstance(period, dict):
        return None, None, "missing_required_field"
    name = parameter.get("name")
    name = name.strip().lower() if isinstance(name, str) else None
    if name not in {"pm25", "pm10"}:
        return None, None, "invalid_parameter"
    if name != retrieval["parameter"].strip().lower():
        return None, None, "parameter_mismatch"
    parameter_id = parameter.get("id")
    if parameter_id is not None and not _identifier(parameter_id):
        return None, None, "invalid_identifier"
    unit = parameter.get("units")
    if not isinstance(unit, str) or not unit.strip():
        return None, None, "missing_unit"
    value = record.get("value")
    if not _finite(value):
        return None, None, "invalid_value"
    times, locals_ = [], []
    for key in ("datetimeFrom", "datetimeTo"):
        boundary = period.get(key)
        if not isinstance(boundary, dict) or not isinstance(boundary.get("utc"), str):
            return None, None, "invalid_timestamp"
        try:
            timestamp = pd.Timestamp(boundary["utc"])
            if pd.isna(timestamp) or timestamp.tzinfo is None:
                raise ValueError
            times.append(timestamp.tz_convert("UTC").as_unit("ns"))
        except (ValueError, TypeError, OverflowError):
            return None, None, "invalid_timestamp"
        local = boundary.get("local")
        if local is not None and not isinstance(local, str):
            return None, None, "invalid_timestamp"
        locals_.append(local)
    if times[1] <= times[0]:
        return None, None, "invalid_period"
    coordinates = record.get("coordinates")
    if coordinates is None:
        coordinates = {}
    if not isinstance(coordinates, dict):
        return None, None, "missing_required_field"
    for key in ("latitude", "longitude"):
        if coordinates.get(key) is not None and not _finite(coordinates[key]):
            return None, None, "invalid_value"
    if any(
        period.get(key) is not None and not isinstance(period[key], str)
        for key in ("label", "interval")
    ):
        return None, None, "missing_required_field"
    row = dict(
        zip(
            COLUMNS,
            [
                "openaq",
                retrieval["location_id"],
                retrieval.get("location_name"),
                retrieval["sensor_id"],
                name,
                parameter_id,
                unit,
                value,
                period.get("label"),
                period.get("interval"),
                times[0],
                times[1],
                locals_[0],
                locals_[1],
                coordinates.get("latitude"),
                coordinates.get("longitude"),
                source_file,
                retrieval["datetime_from"],
                retrieval["datetime_to"],
            ],
            strict=True,
        )
    )
    meaningful = copy.deepcopy(record)
    meaningful["parameter"]["name"] = name
    for key, timestamp in zip(("datetimeFrom", "datetimeTo"), times, strict=True):
        meaningful["period"][key]["utc"] = timestamp.isoformat()
    # Numeric 1 and 1.0 compare as the same measurement without modifying raw input.
    meaningful["value"] = int(value) if value == int(value) else value
    signature = json.dumps(meaningful, sort_keys=True, ensure_ascii=False)
    return row, signature, None


def observation_frame(rows):
    frame = pd.DataFrame(rows, columns=COLUMNS)
    for key in ("location_id", "sensor_id", "parameter_id"):
        frame[key] = pd.array([row[key] for row in rows], dtype="Int64")
    for key in ("datetime_from_utc", "datetime_to_utc"):
        frame[key] = pd.to_datetime(frame[key], utc=True)
    return frame
