"""OpenAQ v3 requests with bounded retries and sequential pagination."""

import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx


class OpenAQConfigurationError(ValueError):
    """OpenAQ authentication is missing or invalid."""


class OpenAQClientError(RuntimeError):
    """An OpenAQ request failed or returned invalid JSON."""


class OpenAQClient:
    """Fetch OpenAQ data with bounded retries and optional full pagination.

    An explicit key takes precedence over OPENAQ_API_KEY. Environment variables
    must be set by the caller; this client does not automatically load .env files.
    A transport can be supplied for offline tests.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.openaq.org/v3",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        max_pages: int = 1000,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = os.environ.get("OPENAQ_API_KEY") if api_key is None else api_key
        if not key or not key.strip():
            raise OpenAQConfigurationError(
                "Configure OPENAQ_API_KEY before requesting data."
            )
        if not key.isascii() or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise OpenAQConfigurationError(
                "OPENAQ_API_KEY must be a valid HTTP header value."
            )
        if type(max_retries) is not int or not 0 <= max_retries <= 10:
            raise OpenAQConfigurationError("max_retries must be between 0 and 10.")
        if type(max_pages) is not int or max_pages < 1:
            raise OpenAQConfigurationError("max_pages must be a positive integer.")
        self._max_retries = max_retries
        self._max_pages = max_pages
        self._sleep = sleep
        self.last_rate_limit = {}
        self._api_key = key
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout = timeout
        self._transport = transport

    def get_locations(
        self, params: Mapping[str, str | int | float | bool] | None = None
    ) -> Any:
        """Return decoded JSON for one locations page.

        Pass query parameters such as {"limit": 10, "page": 1}. Responses are
        returned unchanged; no records are persisted or additional pages fetched.
        """
        return self._get("locations", params)

    def get_location_sensors(self, location_id: int) -> Any:
        """Return sensors attached to a location, without additional requests."""
        return self._get(f"locations/{location_id}/sensors")

    def get_sensor_measurements(
        self, sensor_id: int, params: Mapping[str, str | int | float | bool]
    ) -> Any:
        """Return one page of original measurements for a sensor."""
        return self._get(f"sensors/{sensor_id}/measurements", params)

    def get_all_locations(self, params: Mapping | None = None) -> dict:
        """Retrieve all location pages, preserving query filters."""
        return self._paginate("locations", params)

    def get_all_location_sensors(self, location_id: int) -> dict:
        """Retrieve all sensor pages for a location."""
        return self._paginate(f"locations/{location_id}/sensors")

    def get_all_sensor_measurements(self, sensor_id: int, params: Mapping) -> dict:
        """Retrieve all original measurements within the supplied window."""
        return self._paginate(f"sensors/{sensor_id}/measurements", params)

    @staticmethod
    def _count(value: Any) -> int | None:
        if type(value) is int and value >= 0:
            return value
        if (
            isinstance(value, str)
            and value.strip().isascii()
            and value.strip().isdigit()
        ):
            return int(value)
        return None

    def _paginate(self, resource: str, params: Mapping | None = None) -> dict:
        query = dict(params or {})
        query.update(limit=1000, page=1)
        results, pages = [], []
        fingerprints = set()
        total = None
        effective_limit = None
        for page in range(1, self._max_pages + 1):
            query["page"] = page
            response = self._get(resource, query)
            if not isinstance(response, dict) or not isinstance(
                response.get("results"), list
            ):
                raise OpenAQClientError(
                    f"OpenAQ {resource} returned an invalid results page."
                )
            records = response["results"]
            meta = response.get("meta") or {}
            if not isinstance(meta, dict):
                raise OpenAQClientError(f"OpenAQ {resource} returned invalid metadata.")
            if "page" in meta and self._count(meta["page"]) != page:
                raise OpenAQClientError(
                    f"OpenAQ {resource} returned an inconsistent page number."
                )
            limit = self._count(meta.get("limit", 1000))
            if limit is None or not 1 <= limit <= 1000 or len(records) > limit:
                raise OpenAQClientError(
                    f"OpenAQ {resource} returned an inconsistent page size."
                )
            if effective_limit is not None and effective_limit != limit:
                raise OpenAQClientError(
                    f"OpenAQ {resource} changed page size during pagination."
                )
            effective_limit = limit
            found = self._count(meta.get("found"))
            if found is not None:
                if total is not None and total != found:
                    raise OpenAQClientError(
                        f"OpenAQ {resource} changed total during pagination."
                    )
                total = found
            if records:
                fingerprint = hashlib.sha256(
                    json.dumps(records, sort_keys=True).encode()
                ).digest()
                if fingerprint in fingerprints:
                    raise OpenAQClientError(
                        f"OpenAQ {resource} repeated a page; retrieval aborted."
                    )
                fingerprints.add(fingerprint)
            results.extend(records)
            pages.append(
                {
                    "page": page,
                    "meta": meta,
                    "returned": len(records),
                    "rate_limit": dict(self.last_rate_limit),
                }
            )
            if total is not None:
                if len(results) > total or (not records and len(results) < total):
                    raise OpenAQClientError(
                        f"OpenAQ {resource} returned results inconsistent with its total."
                    )
                complete = len(results) >= total
            else:
                complete = len(records) < effective_limit
            if complete:
                return {
                    "meta": meta,
                    "results": results,
                    "pagination": {
                        "pages_fetched": page,
                        "requested_limit": 1000,
                        "returned": len(results),
                        "found": total if total is not None else meta.get("found"),
                        "complete": True,
                        "pages": pages,
                    },
                }
        raise OpenAQClientError(
            f"OpenAQ {resource} exceeded maximum page count; retrieval incomplete."
        )

    def _get(self, resource: str, params: Mapping | None = None) -> Any:
        retryable = {408, 429, 500, 502, 503, 504}
        with httpx.Client(
            base_url=self._base_url,
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
        ) as client:
            for attempt in range(self._max_retries + 1):
                delay = min(0.5 * 2**attempt, 60.0)
                try:
                    response = client.get(resource, params=params)
                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ):
                    if attempt == self._max_retries:
                        raise OpenAQClientError(
                            f"OpenAQ {resource} HTTP communication failed; retries exhausted."
                        ) from None
                    self._sleep(delay)
                    continue
                except httpx.RequestError:
                    raise OpenAQClientError(
                        f"OpenAQ {resource} failed during HTTP communication."
                    ) from None
                self.last_rate_limit = {
                    header: response.headers[header]
                    for header in (
                        "x-ratelimit-limit",
                        "x-ratelimit-remaining",
                        "x-ratelimit-reset",
                        "x-ratelimit-used",
                    )
                    if header in response.headers
                }
                if response.status_code in retryable:
                    if attempt == self._max_retries:
                        raise OpenAQClientError(
                            f"OpenAQ {resource} failed with HTTP {response.status_code}; retries exhausted."
                        )
                    if response.status_code == 429:
                        try:
                            reset = float(response.headers.get("x-ratelimit-reset", ""))
                            if math.isfinite(reset) and reset >= 0:
                                delay = min(reset, 60.0)
                        except ValueError:
                            pass
                    self._sleep(delay)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    raise OpenAQClientError(
                        f"OpenAQ {resource} request failed with HTTP {response.status_code}."
                    ) from None
                try:
                    return response.json()
                except ValueError:
                    raise OpenAQClientError(
                        f"OpenAQ {resource} response was not valid JSON."
                    ) from None
