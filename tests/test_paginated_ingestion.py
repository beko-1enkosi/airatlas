"""Exercise ingestion through the real client with offline HTTP pages."""

import json
from pathlib import Path

import httpx
import pytest

from airatlas.ingestion.historical_backfill import backfill_historical_measurements
from airatlas.ingestion.incremental import ingest_incremental_measurements
from airatlas.ingestion.location_discovery import discover_south_african_locations
from airatlas.ingestion.openaq import OpenAQClient, OpenAQClientError


@pytest.mark.parametrize("incremental", [False, True])
@pytest.mark.parametrize("fail_second_page", [False, True])
def test_paginated_window_and_failure_safety(incremental, fail_second_page):
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "config/mvp_locations.json").read_text()
    )
    location_id = config["locations"][0]["id"]
    calls, delays = [], []
    start, end = (
        ("2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")
        if incremental
        else ("2026-09-01", "2026-09-02")
    )

    def handler(request):
        calls.append(request)
        page = int(request.url.params["page"])
        assert request.headers["X-API-Key"] == "fake-test-key"
        if request.url.path == f"/v3/locations/{location_id}/sensors":
            parameter = "pm25" if page == 1 else "pm10"
            return httpx.Response(
                200,
                json={
                    "meta": {"page": page, "limit": 1, "found": 2},
                    "results": [{"id": page, "parameter": {"name": parameter}}],
                },
            )
        assert request.url.path in {
            "/v3/sensors/1/measurements",
            "/v3/sensors/2/measurements",
        }
        assert request.url.params["datetime_from"] == start
        assert request.url.params["datetime_to"] == end
        if page == 2 and fail_second_page:
            return httpx.Response(503)
        # Unknown total: a full page must be followed by an empty page.
        records = (
            [{"id": "original", "value": 12.5, "extra": {"unchanged": True}}]
            if page == 1
            else []
        )
        return httpx.Response(
            200, json={"meta": {"page": page, "limit": 1}, "results": records}
        )

    client = OpenAQClient(
        "fake-test-key", transport=httpx.MockTransport(handler), sleep=delays.append
    )
    function = (
        ingest_incremental_measurements
        if incremental
        else backfill_historical_measurements
    )
    if fail_second_page:
        with pytest.raises(OpenAQClientError, match="retries exhausted"):
            function(client, config, start, end, location_id=location_id)
        assert delays == [0.5, 1, 2]
    else:
        result = function(client, config, start, end, location_id=location_id)
        assert len(calls) == 6
        assert result["locations"][0]["sensor_discovery_incomplete"] is False
        assert result["locations"][0]["sensor_pagination"]["pages_fetched"] == 2
        assert len(result["sensors"]) == 2
        for sensor in result["sensors"]:
            assert sensor["pagination"]["pages_fetched"] == 2
            assert sensor["incomplete"] is False
            assert sensor["results"] == [
                {"id": "original", "value": 12.5, "extra": {"unchanged": True}}
            ]
        if incremental:
            assert result["checkpoint_safe"] is True
            assert result["next_checkpoint_candidate"] == end


def test_paginated_south_african_discovery():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["iso"] == "ZA"
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "meta": {"found": 2, "page": page, "limit": 1},
                "results": [{"id": page, "country": {"code": "ZA"}}],
            },
        )

    client = OpenAQClient(
        "fake-test-key",
        transport=httpx.MockTransport(handler),
        sleep=lambda delay: pytest.fail("Unexpected sleep"),
    )
    result = discover_south_african_locations(client)
    assert [location["id"] for location in result["locations"]] == [1, 2]
    assert result["pagination"]["pages_fetched"] == 2
    assert result["incomplete"] is False
    assert len(calls) == 2
