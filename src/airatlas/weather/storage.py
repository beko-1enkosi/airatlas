"""Immutable cache of validated original weather responses, keyed by request."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from airatlas.weather.client import WeatherError, request_parameters, validate_response


def cache_path(raw_dir, request):
    identity = json.dumps(
        request, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return (
        Path(raw_dir)
        / "open_meteo/hourly"
        / f"location_id={request['location_id']}"
        / f"{request['start_date']}__{request['end_date']}__{digest}.json"
    )


def _load(path, request):
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise WeatherError(f"Invalid raw weather cache: {path.name}.") from None
    if (
        not isinstance(envelope, dict)
        or envelope.get("schema_version") != 1
        or envelope.get("source") != "open_meteo"
        or envelope.get("request") != request
    ):
        raise WeatherError(f"Raw weather cache identity mismatch: {path.name}.")
    validate_response(
        envelope.get("response"), request["start_date"], request["end_date"]
    )
    return envelope


def get_cached_weather(
    client,
    raw_dir,
    *,
    location_id,
    location_name,
    latitude,
    longitude,
    start_date,
    end_date,
):
    """Return (raw envelope, cache hit). Invalid caches fail, never auto-refresh.

    The full response retains source-grid metadata, units and original hourly
    arrays. Names are descriptive; IDs and normalized request settings identify
    the cache. Like OpenAQ raw publication, same-filesystem hard links are used.
    """
    if type(location_id) is not int or location_id <= 0:
        raise WeatherError("Weather cache requires a positive location ID.")
    request = {
        "location_id": location_id,
        **request_parameters(latitude, longitude, start_date, end_date),
    }
    root = Path(raw_dir).resolve()
    path = cache_path(root, request)
    if not path.resolve().is_relative_to(root):
        raise WeatherError("Weather cache must remain beneath the raw root.")
    if path.exists():
        return _load(path, request), True
    response = client.get_hourly(latitude, longitude, start_date, end_date)
    validate_response(response, start_date, end_date)
    envelope = {
        "schema_version": 1,
        "source": "open_meteo",
        "location_name": location_name,
        "request": request,
        "response": response,
    }
    encoded = json.dumps(envelope, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".airatlas-weather-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            # Another identical request won publication. Its valid snapshot wins.
            envelope = _load(path, request)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return envelope, False
