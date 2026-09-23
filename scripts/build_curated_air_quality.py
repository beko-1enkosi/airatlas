"""Build curated partitioned Parquet from the validated processed CSV."""

import argparse
import json
from pathlib import Path

from airatlas.curation.parquet import build_curated_air_quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--input-file",
        type=Path,
        default=root / "data/processed/openaq/air_quality_observations.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=root / "data/curated")
    args = parser.parse_args()
    try:
        summary = build_curated_air_quality(args.input_file, args.output_dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
