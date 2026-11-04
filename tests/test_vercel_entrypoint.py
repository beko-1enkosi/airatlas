"""Vercel deployment entry-point contract."""

from fastapi import FastAPI

import app as vercel_entrypoint
from airatlas.api.app import app as api_app


def test_vercel_entrypoint_exposes_existing_fastapi_application():
    assert isinstance(vercel_entrypoint.app, FastAPI)
    assert vercel_entrypoint.app is api_app
    assert {
        "/api/health",
        "/api/summary",
        "/api/locations",
        "/api/locations/{location_id}",
        "/api/trends",
        "/api/comparison/locations",
        "/api/weather-context",
        "/api/data-health",
    } <= {route.path for route in vercel_entrypoint.app.routes}
