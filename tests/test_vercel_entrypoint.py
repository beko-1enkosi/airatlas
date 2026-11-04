"""Vercel deployment entry-point contract."""

import subprocess
import sys
from pathlib import Path

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


def test_vercel_entrypoint_imports_without_editable_install(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    script = """
import importlib.util
import sys
from importlib import import_module
from pathlib import Path

entrypoint = Path(sys.argv[1])
source_root = Path(sys.argv[2]).resolve()
sys.path[:] = [
    item for item in sys.path
    if not item or Path(item).resolve() != source_root
]
assert importlib.util.find_spec("airatlas") is None

spec = importlib.util.spec_from_file_location("vercel_entrypoint", entrypoint)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.app is import_module("airatlas.api.app").app
expected_routes = {
    "/api/health",
    "/api/summary",
    "/api/locations",
    "/api/locations/{location_id}",
    "/api/trends",
    "/api/comparison/locations",
    "/api/weather-context",
    "/api/data-health",
}
assert expected_routes <= {route.path for route in module.app.routes}
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(repository / "app.py"),
            str(repository / "src"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
