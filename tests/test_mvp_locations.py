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
