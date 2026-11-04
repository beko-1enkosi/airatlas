"""Vercel entry point for the existing AirAtlas FastAPI application."""

import sys
from importlib import import_module
from pathlib import Path

_SOURCE_ROOT = str(Path(__file__).resolve().parent / "src")
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)

app = import_module("airatlas.api.app").app

__all__ = ["app"]
