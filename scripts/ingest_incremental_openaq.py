"""Persist safe incremental raw batches and print a checkpoint candidate; never save checkpoint state."""

import argparse
import json
from pathlib import Path

from airatlas.ingestion.incremental import (
    ingest_incremental_measurements,
    normalize_incremental_window,
)
from airatlas.ingestion.measurement_window import load_mvp_config, select_mvp_locations
from airatlas.ingestion.openaq import OpenAQClient, OpenAQClientError
from airatlas.storage.raw import persist_raw_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Previous successful window end, e.g. 2026-09-01T00:00:00Z",
    )
    parser.add_argument(
        "--datetime-to",
        required=True,
        help="Later timezone-aware upper boundary, e.g. 2026-09-01T01:00:00Z",
    )
    parser.add_argument(
        "--location-id",
        type=int,
        help="One approved MVP location; checkpoint safety applies only to this subset",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/raw",
        help="Raw JSON output root (default: repository data/raw)",
    )
    args = parser.parse_args()
    try:
        config = load_mvp_config(
            Path(__file__).resolve().parents[1] / "config/mvp_locations.json"
        )
        start, end = normalize_incremental_window(args.checkpoint, args.datetime_to)
        select_mvp_locations(config, args.location_id)
        result = ingest_incremental_measurements(
            OpenAQClient(), config, start, end, location_id=args.location_id
        )
        persistence = persist_raw_run(result, args.output_dir)
    except (OSError, ValueError, OpenAQClientError) as exc:
        parser.error(str(exc))
    sensors = result["sensors"]
    summary = {
        key: result[key]
        for key in (
            "checkpoint",
            "datetime_to",
            "next_checkpoint_candidate",
            "checkpoint_safe",
            "status",
            "unsafe_reasons",
            "location_ids",
        )
    }
    summary.update(
        {
            "locations_considered": len(result["locations"]),
            "sensors_queried": len(sensors),
            "measurements_by_parameter": {
                parameter: sum(
                    sensor["returned"]
                    for sensor in sensors
                    if sensor["parameter"] == parameter
                )
                for parameter in config["selection"]["required_parameters"]
            },
            "total_measurements": sum(sensor["returned"] for sensor in sensors),
            "empty_responses": sum(sensor["returned"] == 0 for sensor in sensors),
            "incomplete_responses": sum(
                sensor["incomplete"] is True for sensor in sensors
            ),
            "unknown_completeness_responses": sum(
                sensor["incomplete"] is None for sensor in sensors
            ),
            "missing_required_sensors": [
                {
                    "location_id": location["location_id"],
                    "parameters": location["missing_parameters"],
                }
                for location in result["locations"]
                if location["missing_parameters"]
            ],
        }
    )
    summary["persistence"] = persistence
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
