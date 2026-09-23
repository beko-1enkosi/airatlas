"""Deterministic retry and pagination checks; sleeping is always injected."""

import traceback

import httpx
import pytest

from airatlas.ingestion.openaq import OpenAQClient, OpenAQClientError


def make_client(handler, **kwargs):
    delays = []
    client = OpenAQClient(
        "fake-test-key",
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        **kwargs,
    )
    return client, delays


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_status_eventually_succeeds(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status if len(calls) < 3 else 200, json={"results": []})

    client, delays = make_client(handler)
    assert client.get_locations() == {"results": []}
    assert len(calls) == 3
    assert delays == [0.5, 1.0]


@pytest.mark.parametrize("status", [503, 429])
def test_retry_exhaustion(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="fake-test-key")

    client, delays = make_client(handler)
    with pytest.raises(
        OpenAQClientError, match=f"locations.*HTTP {status}.*retries exhausted"
    ) as error:
        client.get_locations()
    assert len(calls) == 4
    assert delays == [0.5, 1.0, 2.0]
    assert "fake-test-key" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("status", [401, 403, 404, 405, 410, 422, 501])
def test_permanent_failure_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    client, delays = make_client(handler)
    with pytest.raises(OpenAQClientError, match=f"HTTP {status}"):
        client.get_locations()
    assert len(calls) == 1
    assert delays == []


@pytest.mark.parametrize(
    "error_type", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError]
)
@pytest.mark.parametrize("recover", [True, False])
def test_transport_retries(error_type, recover):
    calls = []

    def handler(request):
        calls.append(request)
        if recover and len(calls) == 2:
            return httpx.Response(200, json={"results": []})
        raise error_type("fake-test-key", request=request)

    client, delays = make_client(handler)
    if recover:
        assert client.get_locations() == {"results": []}
        assert delays == [0.5]
    else:
        with pytest.raises(OpenAQClientError, match="retries exhausted") as error:
            client.get_locations()
        assert len(calls) == 4
        assert delays == [0.5, 1.0, 2.0]
        assert "fake-test-key" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize(
    ("reset", "delay"),
    [
        ("2", 2),
        ("0", 0),
        ("999999", 60),
        ("bad", 0.5),
        ("-1", 0.5),
        ("nan", 0.5),
        ("inf", 0.5),
    ],
)
def test_rate_limit_delay(reset, delay):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"x-ratelimit-reset": reset})
        return httpx.Response(
            200, json={"results": []}, headers={"x-ratelimit-remaining": "5"}
        )

    client, delays = make_client(handler)
    client.get_locations()
    assert delays == [delay]
    assert client.last_rate_limit == {"x-ratelimit-remaining": "5"}


def test_known_total_2500():
    calls = []

    def handler(request):
        calls.append(request)
        page = int(request.url.params["page"])
        assert request.url.params["limit"] == "1000"
        assert request.url.params["iso"] == "ZA"
        return httpx.Response(
            200,
            json={
                "meta": {"found": "2500", "page": page, "limit": 1000},
                "results": [
                    {"id": i} for i in range((page - 1) * 1000, min(page * 1000, 2500))
                ],
            },
            headers={"x-ratelimit-remaining": "50"},
        )

    client, delays = make_client(handler)
    result = client.get_all_locations({"iso": "ZA"})
    assert result["results"] == [{"id": i} for i in range(2500)]
    assert len(calls) == 3
    assert result["pagination"]["pages_fetched"] == 3
    assert result["pagination"]["returned"] == result["pagination"]["found"] == 2500
    assert result["pagination"]["complete"] is True
    assert result["pagination"]["pages"][0]["meta"]["page"] == 1
    assert result["pagination"]["pages"][0]["rate_limit"] == {
        "x-ratelimit-remaining": "50"
    }
    assert delays == []


@pytest.mark.parametrize("found", [None, "unavailable"])
@pytest.mark.parametrize("last_size", [0, 7])
def test_unknown_total_ends_on_short_page(found, last_size):
    calls = []

    def handler(request):
        calls.append(request)
        page = len(calls)
        size = 1000 if page == 1 else last_size
        return httpx.Response(
            200,
            json={
                "meta": {"found": found},
                "results": [{"id": (page - 1) * 1000 + i} for i in range(size)],
            },
        )

    client, _ = make_client(handler)
    result = client.get_all_locations()
    assert len(calls) == 2
    assert len(result["results"]) == 1000 + last_size
    assert result["pagination"]["complete"] is True


@pytest.mark.parametrize("records", [[], [{"id": 1}]])
@pytest.mark.parametrize("known", [True, False])
def test_single_page(records, known):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"meta": {"found": len(records)} if known else {}, "results": records},
        )

    client, _ = make_client(handler)
    assert client.get_all_locations()["results"] == records
    assert len(calls) == 1


def test_page_guard():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"meta": {"limit": 1}, "results": [{"id": len(calls)}]}
        )

    client, _ = make_client(handler, max_pages=3)
    with pytest.raises(OpenAQClientError, match="maximum page count"):
        client.get_all_locations()
    assert len(calls) == 3


def test_repeated_page_fails():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"meta": {"limit": 1}, "results": [{"id": 1}]})

    client, _ = make_client(handler)
    with pytest.raises(OpenAQClientError, match="repeated a page"):
        client.get_all_locations()
    assert len(calls) == 2


@pytest.mark.parametrize("second_meta", [{"page": 1}, {"found": 3}, {"limit": 2}])
def test_inconsistent_metadata(second_meta):
    calls = []

    def handler(request):
        calls.append(request)
        page = len(calls)
        meta = {"page": page, "limit": 1, "found": 2}
        if page == 2:
            meta.update(second_meta)
        return httpx.Response(200, json={"meta": meta, "results": [{"id": page}]})

    client, _ = make_client(handler)
    with pytest.raises(OpenAQClientError, match="inconsistent|changed"):
        client.get_all_locations()


def test_premature_empty_page_fails():
    client, _ = make_client(
        lambda request: httpx.Response(200, json={"meta": {"found": 1}, "results": []})
    )
    with pytest.raises(OpenAQClientError, match="inconsistent"):
        client.get_all_locations()


def test_invalid_json_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="not-json")

    client, delays = make_client(handler)
    with pytest.raises(OpenAQClientError, match="not valid JSON"):
        client.get_locations()
    assert len(calls) == 1
    assert delays == []
