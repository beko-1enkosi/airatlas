"""Explicit date-range backfill; single pages only, with no persistence."""

from datetime import date
from typing import Any

from airatlas.ingestion.openaq import OpenAQClient


def validate_date_range(datetime_from: str, datetime_to: str) -> None:
    """Require calendar dates in YYYY-MM-DD format, with end strictly after start."""
    try:
        start = date.fromisoformat(datetime_from)
        end = date.fromisoformat(datetime_to)
        if start.isoformat() != datetime_from or end.isoformat() != datetime_to:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(
            "Both dates must be valid ISO dates in YYYY-MM-DD format."
        ) from None
    if start >= end:
        raise ValueError(
            "date_to must be strictly later than date_from. "
            "For a one-day window, use 2026-09-01 to 2026-09-02."
        )


def _incomplete(found: Any, returned: int) -> bool | None:
    if type(found) is int and found >= 0:
        return found > returned
    if isinstance(found, str) and found.strip().isascii() and found.strip().isdigit():
        return int(found) > returned
    return None


def backfill_historical_measurements(
    client: OpenAQClient,
    config: dict[str, Any],
    datetime_from: str,
    datetime_to: str,
    *,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Fetch PM2.5/PM10 history for the supplied approved MVP configuration.

    Dates are passed unchanged to OpenAQ; no end-of-day or timezone conversion
    is applied. Missing pollutants are reported per location. HTTP failures use
    the client's existing exceptions. None completeness means an unknown total.
    """
    validate_date_range(datetime_from, datetime_to)
    locations = config["locations"]
    if location_id is not None:
        locations = [
            location for location in locations if location["id"] == location_id
        ]
        if not locations:
            raise ValueError(
                "location_id must belong to the approved MVP configuration."
            )
    required = config["selection"]["required_parameters"]
    if set(required) != {"pm25", "pm10"}:
        raise ValueError("MVP required_parameters must contain pm25 and pm10 only.")

    params = {
        "datetime_from": datetime_from,
        "datetime_to": datetime_to,
        "limit": 1000,
        "page": 1,
    }
    sensor_results = []
    location_reports = []
    for location in locations:
        response = client.get_location_sensors(location["id"])
        sensors = response["results"]
        matching = [
            sensor
            for sensor in sensors
            if (sensor.get("parameter") or {}).get("name") in required
        ]
        present = {sensor["parameter"]["name"] for sensor in matching}
        sensor_meta = response.get("meta")
        location_reports.append(
            {
                "location_id": location["id"],
                "location_name": location["name"],
                "matching_sensors": len(matching),
                "missing_parameters": [
                    parameter for parameter in required if parameter not in present
                ],
                "sensor_meta": sensor_meta,
                "sensor_discovery_incomplete": _incomplete(
                    (sensor_meta or {}).get("found"), len(sensors)
                ),
            }
        )
        for sensor in matching:
            measurements = client.get_sensor_measurements(sensor["id"], params=params)
            records = measurements["results"]
            meta = measurements.get("meta")
            found = (meta or {}).get("found")
            sensor_results.append(
                {
                    "location_id": location["id"],
                    "location_name": location["name"],
                    "sensor_id": sensor["id"],
                    "parameter": sensor["parameter"]["name"],
                    "datetime_from": datetime_from,
                    "datetime_to": datetime_to,
                    "meta": meta,
                    "results": records,
                    "returned": len(records),
                    "found": found,
                    "incomplete": _incomplete(found, len(records)),
                }
            )
    return {
        "datetime_from": datetime_from,
        "datetime_to": datetime_to,
        "locations": location_reports,
        "sensors": sensor_results,
    }
