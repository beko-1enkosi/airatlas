"""Ask Air contracts, trusted context and mocked OpenRouter behaviour."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from airatlas.api import ask_air, queries
from airatlas.api.app import app
from airatlas.api.models import AskAirRequest


@pytest.fixture(autouse=True)
def configured_free_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret-key")
    monkeypatch.setenv("OPENROUTER_MODEL", ask_air.DEFAULT_MODEL)
    ask_air.rate_limiter.reset()
    yield
    ask_air.rate_limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


def mocked_openrouter(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        ask_air,
        "openrouter_client",
        lambda: httpx.AsyncClient(transport=transport),
    )


def test_valid_question_uses_bounded_free_model_request(client, monkeypatch):
    captured = {}

    def handler(request):
        captured["request"] = request
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "PM2.5 is fine dust."},
                    }
                ],
                "usage": {
                    "completion_tokens": 8,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    mocked_openrouter(monkeypatch, handler)
    monkeypatch.setattr(queries, "summary", lambda: pytest.fail("No data needed"))
    response = client.post(
        "/api/ask-air",
        json={
            "question": "  What does PM2.5 mean?  ",
            "section": "overview",
            "history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "PM2.5 is fine dust."}
    assert captured["request"].url == ask_air.OPENROUTER_URL
    assert captured["request"].headers["authorization"] == "Bearer test-secret-key"
    assert captured["payload"]["model"] == ask_air.DEFAULT_MODEL
    assert captured["payload"]["max_tokens"] == ask_air.MAX_OUTPUT_TOKENS
    assert captured["payload"]["reasoning"] == {"enabled": False}
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["usage"] == {"include": True}
    assert "models" not in captured["payload"]
    assert captured["payload"]["messages"][-1] == {
        "role": "user",
        "content": "What does PM2.5 mean?",
    }


@pytest.mark.parametrize("question", ["", "   ", "x" * 1201])
def test_empty_and_oversized_questions_are_rejected(client, question):
    response = client.post("/api/ask-air", json={"question": question})
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Please enter a shorter, valid question for Ask Air."
    }


def test_missing_api_key_keeps_endpoint_safely_unavailable(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(
        ask_air,
        "openrouter_client",
        lambda: pytest.fail("Missing configuration must not call OpenRouter"),
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_paid_model_configuration_is_rejected(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "paid/provider-model")
    monkeypatch.setattr(
        ask_air,
        "openrouter_client",
        lambda: pytest.fail("Paid model configuration must not be called"),
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 503
    assert "free model configuration" in response.json()["detail"]


def test_openrouter_timeout_is_safe(client, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("provider trace with test-secret-key", request=request)

    mocked_openrouter(monkeypatch, handler)
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 504
    assert "too long" in response.json()["detail"]
    assert "secret" not in response.text


@pytest.mark.parametrize("provider_status", [500, 502, 503])
def test_provider_errors_are_safe(client, monkeypatch, provider_status):
    mocked_openrouter(
        monkeypatch,
        lambda request: httpx.Response(
            provider_status, json={"error": {"message": "private provider trace"}}
        ),
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 503
    assert "provider is temporarily unavailable" in response.json()["detail"]
    assert "private provider trace" not in response.text


def test_upstream_rate_limit_is_friendly(client, monkeypatch):
    mocked_openrouter(
        monkeypatch,
        lambda request: httpx.Response(429, json={"error": "quota details"}),
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert "free usage limit" in response.json()["detail"]
    assert "quota details" not in response.text


@pytest.mark.parametrize(
    "provider_json",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "   "}}]},
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": ["unexpected"]},
                }
            ]
        },
    ],
)
def test_malformed_or_empty_provider_response_is_safe(
    client, monkeypatch, provider_json
):
    mocked_openrouter(
        monkeypatch, lambda request: httpx.Response(200, json=provider_json)
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 502
    assert "Ask Air received" in response.json()["detail"]


def test_reasoning_budget_exhaustion_is_diagnosed_without_sensitive_data(
    client, monkeypatch, caplog
):
    mocked_openrouter(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": None,
                            "reasoning": "private chain of thought",
                        },
                    }
                ],
                "usage": {
                    "completion_tokens": 320,
                    "completion_tokens_details": {"reasoning_tokens": 320},
                },
            },
        ),
    )
    with caplog.at_level("WARNING", logger="airatlas.api.ask_air"):
        response = client.post(
            "/api/ask-air", json={"question": "What does PM2.5 mean?"}
        )

    assert response.status_code == 502
    assert "ran out of room" in response.json()["detail"]
    assert "finish_reason=length" in caplog.text
    assert "completion_tokens=320" in caplog.text
    assert "reasoning_tokens=320" in caplog.text
    assert "content_present=False" in caplog.text
    assert "private chain of thought" not in caplog.text
    assert "test-secret-key" not in caplog.text
    assert "What does PM2.5 mean?" not in caplog.text


@pytest.mark.parametrize(
    "provider_json",
    [
        {"error": {"message": "provider failed"}},
        {
            "choices": [
                {
                    "finish_reason": "error",
                    "error": {"message": "provider failed"},
                    "message": {"content": "partial private output"},
                }
            ]
        },
    ],
)
def test_embedded_provider_errors_are_not_returned_as_answers(
    client, monkeypatch, provider_json
):
    mocked_openrouter(
        monkeypatch, lambda request: httpx.Response(200, json=provider_json)
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 503
    assert "provider is temporarily unavailable" in response.json()["detail"]
    assert "provider failed" not in response.text
    assert "partial private output" not in response.text


def test_provider_credentials_and_error_details_never_leak(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "super-private-openrouter-key")
    mocked_openrouter(
        monkeypatch,
        lambda request: httpx.Response(
            401,
            json={"error": "super-private-openrouter-key is invalid", "trace": "raw"},
        ),
    )
    response = client.post("/api/ask-air", json={"question": "What is PM10?"})
    assert response.status_code == 503
    assert "super-private" not in response.text
    assert "trace" not in response.text


def test_cors_permits_frontend_post_and_content_type(client):
    response = client.options(
        "/api/ask-air",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "Content-Type" in response.headers["access-control-allow-headers"]


def test_cors_rejects_unrelated_origin(client):
    response = client.options(
        "/api/ask-air",
        headers={
            "Origin": "https://unrelated.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_existing_get_endpoint_remains_available(client, monkeypatch):
    monkeypatch.setattr("airatlas.api.app.query", lambda _: [{"connected": 1}])
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_recency_context_uses_trusted_historical_summary_only(monkeypatch):
    summary = {
        "monitored_locations": 6,
        "observation_count": 100,
        "weather_coverage": 72.5,
        "earliest_observation": datetime(2019, 1, 1, tzinfo=UTC),
        "latest_observation": datetime(2026, 8, 1, tzinfo=UTC),
        "averages": [],
    }
    monkeypatch.setattr(queries, "summary", lambda: summary)
    monkeypatch.setattr(queries, "locations", lambda: pytest.fail("Not relevant"))
    monkeypatch.setattr(queries, "comparison", lambda _: pytest.fail("Not relevant"))

    context = ask_air.build_data_context("How recent are these observations?")
    message = ask_air._context_message(
        AskAirRequest(question="How recent are these observations?"), context
    )

    assert context == {"summary": summary}
    assert "2019-01-01" in message and "2026-08-01" in message
    assert "latest observation is historical" in message
    assert "automatic cloud refresh pipeline is operational" in message


def test_comparison_context_preserves_dates_units_and_pollutant(monkeypatch):
    comparison = [
        {
            "location_id": 6868,
            "location_name": "Brackenham - RBCAA",
            "parameter": "pm10",
            "unit": "µg/m³",
            "average_value": 31.2,
            "earliest_observation_utc": datetime(2019, 1, 1, tzinfo=UTC),
            "latest_observation_utc": datetime(2019, 12, 31, tzinfo=UTC),
        }
    ]
    monkeypatch.setattr(queries, "summary", lambda: {"averages": []})
    requested = []

    def compare(parameter):
        requested.append(parameter)
        return comparison

    monkeypatch.setattr(queries, "comparison", compare)
    context = ask_air.build_data_context(
        "Which station has the highest recorded average PM10?"
    )
    assert requested == ["pm10"]
    assert context["location_comparisons"]["pm10"] == comparison
    assert context["summary"] == {"averages": []}


def test_instance_rate_limiter_is_bounded_but_explicitly_local():
    limiter = ask_air.InstanceRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=61)
