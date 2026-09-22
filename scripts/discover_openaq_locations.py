"""Print South African location metadata using OPENAQ_API_KEY from the environment.

Run from the repository root after installing AirAtlas with .[dev]:
    python scripts/discover_openaq_locations.py
No discovery data is written to disk.
"""

import json
import sys

from airatlas.ingestion.location_discovery import discover_south_african_locations
from airatlas.ingestion.openaq import (
    OpenAQClient,
    OpenAQClientError,
    OpenAQConfigurationError,
)


def main() -> None:
    try:
        discovery = discover_south_african_locations(OpenAQClient())
    except (OpenAQConfigurationError, OpenAQClientError) as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(discovery, indent=2))


if __name__ == "__main__":
    main()
