"""Transactionally refresh PostgreSQL from weather-enriched curated Parquet."""

import argparse
import json
from pathlib import Path

from airatlas.warehouse.loader import WarehouseError, load_postgres_warehouse


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "data/curated/open_meteo_air_quality/air_quality_weather",
    )
    args = parser.parse_args()
    try:
        summary = load_postgres_warehouse(args.input_dir)
    except WarehouseError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
