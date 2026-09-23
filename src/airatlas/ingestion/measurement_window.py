"""Shared paginated sensor retrieval for explicit ingestion windows."""

import json
from pathlib import Path
from typing import Any

from airatlas.ingestion.openaq import OpenAQClient


def load_mvp_config(path: Path) -> dict[str, Any]:
    """Read the approved configuration without duplicating station IDs."""
    return json.loads(path.read_text(encoding="utf-8"))


def select_mvp_locations(
    config: dict[str, Any], location_id: int | None = None
) -> list[dict[str, Any]]:
    """Select all configured locations or one approved development location."""
    locations = config["locations"]
    if location_id is not None:
        locations = [
            location for location in locations if location["id"] == location_id
        ]
        if not locations:
            raise ValueError(
                "location_id must belong to the approved MVP configuration."
            )
    return locations


def _incomplete(found: Any, returned: int) -> bool | None:
    if type(found) is int and found >= 0:
        return found > returned
    if isinstance(found, str) and found.strip().isascii() and found.strip().isdigit():
        return int(found) > returned
    return None


def fetch_measurement_window(
    client: OpenAQClient,
    config: dict[str, Any],
    datetime_from: str,
    datetime_to: str,
    *,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Retrieve a caller-validated date/timestamp window with source provenance.

    Keep boundary records unchanged: later persistence must handle repeated
    records idempotently, including inclusive boundaries and retried windows.
    HTTP failures propagate; no safe checkpoint can be inferred from an exception.
    """
    locations = select_mvp_locations(config, location_id)
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
        response = client.get_all_location_sensors(location["id"])
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
                "sensor_pagination": response.get("pagination"),
                "sensor_discovery_incomplete": False
                if response.get("pagination", {}).get("complete") is True
                else _incomplete((sensor_meta or {}).get("found"), len(sensors)),
            }
        )
        for sensor in matching:
            measurements = client.get_all_sensor_measurements(
                sensor["id"], params=params
            )
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
                    "pagination": measurements.get("pagination"),
                    "incomplete": False
                    if measurements.get("pagination", {}).get("complete") is True
                    else _incomplete(found, len(records)),
                }
            )
    return {
        "datetime_from": datetime_from,
        "datetime_to": datetime_to,
        "locations": location_reports,
        "sensors": sensor_results,
    }
