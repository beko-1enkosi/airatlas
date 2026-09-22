"""Single-page HTTP access to the OpenAQ v3 API."""

import os
from collections.abc import Mapping
from typing import Any

import httpx


class OpenAQConfigurationError(ValueError):
    """OpenAQ authentication is missing or invalid."""


class OpenAQClientError(RuntimeError):
    """An OpenAQ request failed or returned invalid JSON."""


class OpenAQClient:
    """Fetch OpenAQ data without pagination or retries.

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
        try:
            with httpx.Client(
                base_url=self._base_url,
                headers={"X-API-Key": self._api_key},
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.get("locations", params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise OpenAQClientError(
                f"OpenAQ locations request failed with HTTP {exc.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise OpenAQClientError(
                "OpenAQ locations request failed during HTTP communication."
            ) from None
        except ValueError:
            raise OpenAQClientError(
                "OpenAQ locations response was not valid JSON."
            ) from None
