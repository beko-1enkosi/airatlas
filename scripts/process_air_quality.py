"""Rebuild processed CSV and quality counts from immutable raw OpenAQ batches."""

import argparse
import json
from pathlib import Path

from airatlas.processing.pipeline import process_air_quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--raw-dir", type=Path, default=root / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=root / "data/processed")
    args = parser.parse_args()
    try:
        summary = process_air_quality(args.raw_dir, args.output_dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
