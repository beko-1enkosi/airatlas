"""Inspect one page of South African OpenAQ location metadata."""

from typing import Any

from airatlas.ingestion.openaq import OpenAQClient


def discover_south_african_locations(client: OpenAQClient) -> dict[str, Any]:
    """Return location summaries and first-page completeness information.

    Missing optional fields remain None (JSON null). An empty parameters list
    means no parameter names were supplied, not that no pollutants are measured.
    Incomplete is None when meta.found is missing or is not an exact count.
    """
    response = client.get_locations({"iso": "ZA", "page": 1, "limit": 1000})
    locations = []
    for location in response["results"]:
        coordinates = location.get("coordinates") or {}
        parameters = []
        for sensor in location.get("sensors") or []:
            parameter = (sensor or {}).get("parameter") or {}
            name = parameter.get("name")
            if name and name not in parameters:
                parameters.append(name)
        locations.append(
            {
                "id": location["id"],
                "name": location.get("name"),
                "locality": location.get("locality"),
                "country_code": (location.get("country") or {}).get("code"),
                "latitude": coordinates.get("latitude"),
                "longitude": coordinates.get("longitude"),
                "timezone": location.get("timezone"),
                "provider": (location.get("provider") or {}).get("name"),
                "owner": (location.get("owner") or {}).get("name"),
                "is_mobile": location.get("isMobile"),
                "is_monitor": location.get("isMonitor"),
                "parameters": parameters,
            }
        )

    found = (response.get("meta") or {}).get("found")
    total = None
    if type(found) is int and found >= 0:
        total = found
    elif isinstance(found, str) and found.strip().isascii() and found.strip().isdigit():
        total = int(found)
    incomplete = total > len(locations) if total is not None else None
    warning = None
    if incomplete:
        warning = "Results are incomplete: OpenAQ reports more locations than this page contains."
    elif incomplete is None:
        warning = "Completeness is unknown: OpenAQ did not supply an exact total count."

    return {
        "page": 1,
        "limit": 1000,
        "found": found,
        "returned": len(locations),
        "incomplete": incomplete,
        "warning": warning,
        "locations": locations,
    }
