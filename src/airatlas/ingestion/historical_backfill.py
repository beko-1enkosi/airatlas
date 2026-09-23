"""Explicit date-range backfill; single pages only, with no persistence."""

from datetime import date
from typing import Any

from airatlas.ingestion.measurement_window import fetch_measurement_window
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
    return fetch_measurement_window(
        client, config, datetime_from, datetime_to, location_id=location_id
    )
