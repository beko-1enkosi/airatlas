"""Small public Open-Meteo archive client; no credentials or OpenAQ coupling."""

import math
import time
from datetime import UTC, date, datetime
from numbers import Real

import httpx

ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
]
UNITS = dict(zip(VARIABLES, ["\u00b0C", "%", "mm", "km/h"], strict=True))
SETTINGS = {
    "timezone": "UTC",
    "temperature_unit": "celsius",
    "precipitation_unit": "mm",
    "wind_speed_unit": "kmh",
}
RETRYABLE = {408, 429, 500, 502, 503, 504}


class WeatherError(ValueError):
    """Weather configuration, communication, or source validation failed."""


def finite(value):
    try:
        return (
            isinstance(value, Real)
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    except OverflowError:
        return False


def coordinates(latitude, longitude):
    if (
        not finite(latitude)
        or not finite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise WeatherError(
            "Weather coordinates must be finite latitude/longitude within geographic bounds."
        )
    return float(latitude), float(longitude)


def request_parameters(latitude, longitude, start_date, end_date):
    latitude, longitude = coordinates(latitude, longitude)
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if (
            start.isoformat() != start_date
            or end.isoformat() != end_date
            or start > end
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise WeatherError(
            "Weather dates must be ISO dates with start_date <= end_date (inclusive)."
        ) from None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(VARIABLES),
        **SETTINGS,
    }


def validate_response(payload, start_date=None, end_date=None):
    """Validate without altering source JSON; return UTC hourly timestamps.

    Open-Meteo emits offset-free ISO times for timezone=UTC. Those are localized
    only after the response explicitly confirms a zero UTC offset and UTC/GMT.
    Missing values stay null; missing hours are allowed, duplicate hours are not.
    """
    if (
        not isinstance(payload, dict)
        or payload.get("error")
        or payload.get("utc_offset_seconds") != 0
        or payload.get("timezone") not in {"GMT", "UTC", "Etc/UTC", "Etc/GMT"}
    ):
        raise WeatherError("Weather response must confirm UTC/GMT with zero offset.")
    hourly, units = payload.get("hourly"), payload.get("hourly_units")
    if (
        not isinstance(hourly, dict)
        or not isinstance(units, dict)
        or units.get("time") != "iso8601"
    ):
        raise WeatherError("Weather response requires hourly data and ISO time units.")
    for name in ["time", *VARIABLES]:
        if not isinstance(hourly.get(name), list):
            raise WeatherError(f"Weather response missing hourly array: {name}.")
    size = len(hourly["time"])
    if any(len(hourly[name]) != size for name in VARIABLES):
        raise WeatherError("Weather hourly arrays have inconsistent lengths.")
    if any(units.get(name) != unit for name, unit in UNITS.items()):
        raise WeatherError("Weather response units do not match requested units.")
    times = []
    for value in hourly["time"]:
        try:
            if not isinstance(value, str) or "T" not in value:
                raise ValueError
            stamp = datetime.fromisoformat(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            if (
                stamp.utcoffset().total_seconds() != 0
                or stamp.minute
                or stamp.second
                or stamp.microsecond
            ):
                raise ValueError
            stamp = stamp.astimezone(UTC)
            if start_date and not start_date <= stamp.date().isoformat() <= end_date:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise WeatherError(
                "Weather timestamps must be UTC hours within the requested dates."
            ) from None
        times.append(stamp)
    if len(set(times)) != len(times):
        raise WeatherError("Weather response contains duplicate hourly timestamps.")
    for name in VARIABLES:
        for value in hourly[name]:
            if value is None:
                continue
            if (
                not finite(value)
                or (name == "relative_humidity_2m" and not 0 <= value <= 100)
                or (name in {"precipitation", "wind_speed_10m"} and value < 0)
            ):
                raise WeatherError(f"Invalid structural weather value: {name}.")
    if payload.get("latitude") is not None and payload.get("longitude") is not None:
        coordinates(payload["latitude"], payload["longitude"])
    return times


class OpenMeteoClient:
    """At most three retries by default; injectable transport and sleep for tests."""

    def __init__(
        self, *, transport=None, timeout=20.0, max_retries=3, sleep=time.sleep
    ):
        if type(max_retries) is not int or not 0 <= max_retries <= 10:
            raise WeatherError("max_retries must be between 0 and 10.")
        self.transport, self.timeout = transport, timeout
        self.max_retries, self.sleep = max_retries, sleep
        self.requests_made = 0

    def get_hourly(self, latitude, longitude, start_date, end_date):
        params = request_parameters(latitude, longitude, start_date, end_date)
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                response = None
                try:
                    self.requests_made += 1
                    response = client.get(ENDPOINT, params=params)
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    status = response.status_code
                    if status not in RETRYABLE:
                        raise WeatherError(
                            f"Open-Meteo archive request failed: HTTP {status} (not retryable)."
                        ) from None
                    final = f"HTTP {status}"
                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ):
                    final = "transient network error"
                except httpx.RequestError:
                    raise WeatherError(
                        "Open-Meteo archive request failed (not retryable)."
                    ) from None
                else:
                    try:
                        payload = response.json()
                    except ValueError:
                        raise WeatherError(
                            "Open-Meteo archive returned invalid JSON."
                        ) from None
                    validate_response(payload, start_date, end_date)
                    return payload
                if attempt == self.max_retries:
                    raise WeatherError(
                        f"Open-Meteo archive retries exhausted: {final}."
                    )
                delay = min(0.5 * 2**attempt, 30.0)
                if response is not None and response.status_code == 429:
                    try:
                        retry_after = float(response.headers.get("Retry-After", ""))
                        if math.isfinite(retry_after) and retry_after >= 0:
                            delay = min(retry_after, 60.0)
                    except ValueError:
                        pass
                self.sleep(delay)
