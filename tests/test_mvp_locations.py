"""Protect the manually approved MVP selection and its configuration invariants."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def mvp_config():
    path = Path(__file__).resolve().parents[1] / "config/mvp_locations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_location_ids(mvp_config):
    locations = mvp_config["locations"]
    ids = [location["id"] for location in locations]

    assert len(locations) == mvp_config["selection"]["location_count"] == 6
    assert all(type(location_id) is int and location_id > 0 for location_id in ids)
    assert len(set(ids)) == len(ids)
    assert set(ids) == {225448, 225404, 6868, 225396, 925659, 355971}


def test_location_metadata(mvp_config):
    assert mvp_config["country_code"] == "ZA"
    for location in mvp_config["locations"]:
        assert isinstance(location["name"], str) and location["name"].strip()
        assert isinstance(location["locality"], str) and location["locality"].strip()
        assert location["country_code"] == "ZA"


def test_selection_criteria(mvp_config):
    selection = mvp_config["selection"]
    assert {"pm25", "pm10"} <= set(selection["required_parameters"])
    assert selection["criteria"]
    assert all(
        isinstance(criterion, str) and criterion.strip()
        for criterion in selection["criteria"]
    )


def test_confirmed_openaq_coordinates(mvp_config):
    # User-verified OpenAQ v3 /locations/{id} responses, not geocoded values.
    expected = {
        225448: (-26.252611, 27.872139),
        225404: (-33.819667, 18.514333),
        6868: (-28.731301, 32.039016),
        225396: (-33.763778, 25.683428),
        925659: (-23.90677, 29.431096),
        355971: (-25.483507788469588, 27.167539254241067),
    }
    actual = {
        location["id"]: (location["latitude"], location["longitude"])
        for location in mvp_config["locations"]
    }
    assert actual == expected
    for latitude, longitude in actual.values():
        assert -90 <= latitude <= 90
        assert -180 <= longitude <= 180
