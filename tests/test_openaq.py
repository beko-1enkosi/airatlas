"""Offline checks of the OpenAQ HTTP boundary."""

import traceback

import httpx
import pytest

from airatlas.ingestion.openaq import (
    OpenAQClient,
    OpenAQClientError,
    OpenAQConfigurationError,
)


def test_locations_request(monkeypatch):
    monkeypatch.setenv("OPENAQ_API_KEY", "unused-environment-test-value")
    requests = []
    payload = {"meta": {"page": 2, "found": 100}, "results": [{"id": 123}]}

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url).split("?")[0] == "https://api.openaq.org/v3/locations"
        assert request.headers["X-API-Key"] == "fake-test-key"
        assert dict(request.url.params) == {
            "limit": "5",
            "page": "2",
            "parameters_id": "2",
        }
        assert request.extensions["timeout"]["read"] == 10.0
        return httpx.Response(200, json=payload)

    client = OpenAQClient("fake-test-key", transport=httpx.MockTransport(handler))
    assert client.get_locations({"limit": 5, "page": 2, "parameters_id": 2}) == payload
    assert len(requests) == 1


def test_environment_key(monkeypatch):
    monkeypatch.setenv("OPENAQ_API_KEY", "fake-environment-key")

    def handler(request):
        assert request.headers["X-API-Key"] == "fake-environment-key"
        return httpx.Response(200, json={"results": []})

    client = OpenAQClient(transport=httpx.MockTransport(handler))
    assert client.get_locations() == {"results": []}


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key(monkeypatch, key):
    monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
    with pytest.raises(OpenAQConfigurationError, match="Configure OPENAQ_API_KEY"):
        OpenAQClient(key)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failure(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="fake-test-key")

    client = OpenAQClient("fake-test-key", transport=httpx.MockTransport(handler))
    with pytest.raises(OpenAQClientError, match=f"HTTP {status}") as error:
        client.get_locations()
    assert "fake-test-key" not in "".join(traceback.format_exception(error.value))
    assert len(requests) == 1


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("fake-test-key", request=request)

    client = OpenAQClient("fake-test-key", transport=httpx.MockTransport(handler))
    with pytest.raises(OpenAQClientError, match="HTTP communication") as error:
        client.get_locations()
    assert "fake-test-key" not in "".join(traceback.format_exception(error.value))


def test_invalid_json():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not JSON")
    )
    client = OpenAQClient("fake-test-key", transport=transport)
    with pytest.raises(OpenAQClientError, match="not valid JSON"):
        client.get_locations()


def test_invalid_key_is_not_exposed():
    with pytest.raises(OpenAQConfigurationError) as error:
        OpenAQClient("fake-test-key\n")
    assert "fake-test-key" not in str(error.value)
