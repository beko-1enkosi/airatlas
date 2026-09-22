"""Offline discovery checks using a mocked OpenAQ client."""

import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

from airatlas.ingestion.location_discovery import discover_south_african_locations
from airatlas.ingestion.openaq import OpenAQClient


def test_filter_and_location_metadata():
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {
        "meta": {"found": 1},
        "results": [
            {
                "id": 123,
                "name": "Example monitor",
                "locality": "Example locality",
                "country": {"code": "ZA"},
                "coordinates": {"latitude": -26.2, "longitude": 28.0},
                "timezone": "Africa/Johannesburg",
                "provider": {"name": "Example provider"},
                "owner": {"name": "Example owner"},
                "isMobile": False,
                "isMonitor": True,
                "sensors": [
                    {"parameter": {"name": "pm25"}},
                    {"parameter": {"name": "no2"}},
                    {"parameter": {"name": "pm25"}},
                ],
            }
        ],
    }
    result = discover_south_african_locations(client)
    client.get_locations.assert_called_once_with(
        {"iso": "ZA", "page": 1, "limit": 1000}
    )
    assert result["locations"] == [
        {
            "id": 123,
            "name": "Example monitor",
            "locality": "Example locality",
            "country_code": "ZA",
            "latitude": -26.2,
            "longitude": 28.0,
            "timezone": "Africa/Johannesburg",
            "provider": "Example provider",
            "owner": "Example owner",
            "is_mobile": False,
            "is_monitor": True,
            "parameters": ["pm25", "no2"],
        }
    ]
    assert result["returned"] == result["found"] == 1
    assert result["incomplete"] is False
    assert result["warning"] is None


@pytest.mark.parametrize(
    "optional",
    [
        {},
        {"locality": None, "owner": None, "coordinates": None, "sensors": None},
        {"locality": "", "owner": {}, "coordinates": {}, "sensors": []},
        {"sensors": [{}, {"parameter": None}, {"parameter": {}}]},
    ],
)
def test_missing_optional_metadata(optional):
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {"results": [{"id": 456, **optional}]}
    result = discover_south_african_locations(client)
    location = result["locations"][0]
    assert location["id"] == 456
    assert location["locality"] == optional.get("locality")
    for field in (
        "name",
        "latitude",
        "longitude",
        "owner",
        "provider",
        "country_code",
        "timezone",
        "is_mobile",
        "is_monitor",
    ):
        assert location[field] is None
    assert location["parameters"] == []
    assert result["incomplete"] is None
    assert "unknown" in result["warning"]


@pytest.mark.parametrize("found", [3, "3"])
def test_incomplete_page(found):
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {
        "meta": {"found": found},
        "results": [{"id": 1}, {"id": 2}],
    }
    result = discover_south_african_locations(client)
    assert result["found"] == found
    assert result["returned"] == 2
    assert result["incomplete"] is True
    assert "incomplete" in result["warning"]
    assert [location["id"] for location in result["locations"]] == [1, 2]
    client.get_locations.assert_called_once()


@pytest.mark.parametrize("found", [None, ">1000", "unknown"])
def test_unknown_total(found):
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {"meta": {"found": found}, "results": []}
    result = discover_south_african_locations(client)
    assert result["found"] == found
    assert result["incomplete"] is None
    assert "unknown" in result["warning"]


def test_empty_discovery():
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {"meta": {"found": 0}, "results": []}
    result = discover_south_african_locations(client)
    assert result["returned"] == 0
    assert result["locations"] == []
    assert result["incomplete"] is False


def test_terminal_output(monkeypatch, capsys):
    client = Mock(spec=OpenAQClient)
    client.get_locations.return_value = {"meta": {"found": 2}, "results": [{"id": 123}]}
    monkeypatch.setattr("airatlas.ingestion.openaq.OpenAQClient", lambda: client)
    script = (
        Path(__file__).resolve().parents[1] / "scripts/discover_openaq_locations.py"
    )
    runpy.run_path(str(script), run_name="__main__")
    output = json.loads(capsys.readouterr().out)
    assert output["found"] == 2
    assert output["returned"] == 1
    assert output["locations"][0]["id"] == 123
    assert output["incomplete"] is True
    assert "incomplete" in output["warning"]
    client.get_locations.assert_called_once()
