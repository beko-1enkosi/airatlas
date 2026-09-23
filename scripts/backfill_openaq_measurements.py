"""Retrieve historical measurements, persist raw JSON, and print a summary."""

import argparse
import json
from pathlib import Path

from airatlas.ingestion.historical_backfill import (
    backfill_historical_measurements,
    validate_date_range,
)
from airatlas.ingestion.measurement_window import load_mvp_config, select_mvp_locations
from airatlas.ingestion.openaq import (
    OpenAQClient,
    OpenAQClientError,
    OpenAQConfigurationError,
)
from airatlas.storage.raw import persist_raw_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date-from", required=True, help="Start ISO date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--date-to",
        required=True,
        help=(
            "End ISO date (YYYY-MM-DD), strictly later than --date-from and passed "
            "unchanged to OpenAQ. For a one-day window, use "
            "--date-from 2026-09-01 --date-to 2026-09-02."
        ),
    )
    parser.add_argument(
        "--location-id", type=int, help="Restrict to one approved MVP location"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/raw",
        help="Raw JSON output root (default: repository data/raw)",
    )
    args = parser.parse_args()
    config_path = Path(__file__).resolve().parents[1] / "config/mvp_locations.json"
    try:
        config = load_mvp_config(config_path)
        validate_date_range(args.date_from, args.date_to)
        select_mvp_locations(config, args.location_id)
        result = backfill_historical_measurements(
            OpenAQClient(),
            config,
            args.date_from,
            args.date_to,
            location_id=args.location_id,
        )
        persistence = persist_raw_run(result, args.output_dir)
    except (OSError, ValueError, OpenAQConfigurationError, OpenAQClientError) as exc:
        parser.error(str(exc))

    sensors = result["sensors"]
    summary = {
        "datetime_from": result["datetime_from"],
        "datetime_to": result["datetime_to"],
        "locations_considered": len(result["locations"]),
        "matching_sensors_queried": len(sensors),
        "measurements_returned": sum(sensor["returned"] for sensor in sensors),
        "incomplete_responses": sum(sensor["incomplete"] is True for sensor in sensors),
        "unknown_completeness_responses": sum(
            sensor["incomplete"] is None for sensor in sensors
        ),
        "empty_responses": sum(sensor["returned"] == 0 for sensor in sensors),
        "locations": result["locations"],
        "sensors": [
            {
                key: sensor[key]
                for key in (
                    "location_id",
                    "location_name",
                    "sensor_id",
                    "parameter",
                    "returned",
                    "found",
                    "incomplete",
                )
            }
            for sensor in sensors
        ],
    }
    summary["persistence"] = persistence
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
