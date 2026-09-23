"""Enrich curated air-quality Parquet with cached historical Open-Meteo hours."""

import argparse
import json
from pathlib import Path

from airatlas.weather.client import OpenMeteoClient
from airatlas.weather.enrichment import enrich_air_quality_weather


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir", type=Path, default=root / "data/curated/openaq/air_quality"
    )
    parser.add_argument("--raw-weather-dir", type=Path, default=root / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=root / "data/curated")
    args = parser.parse_args()
    try:
        summary = enrich_air_quality_weather(
            OpenMeteoClient(), args.input_dir, args.raw_weather_dir, args.output_dir
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
