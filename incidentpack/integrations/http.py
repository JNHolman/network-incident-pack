"""Small JSON HTTP client with explicit timeout and retry behavior."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

import requests

from incidentpack.security import redact_secret_text

logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Raised when an external API request cannot be completed safely."""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry settings for transient HTTP failures."""

    max_attempts: int = 3
    initial_delay: float = 0.25
    backoff_factor: float = 2.0
    retry_statuses: Sequence[int] = (429, 502, 503, 504)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_delay < 0:
            raise ValueError("initial_delay cannot be negative")
        if self.backoff_factor < 1:
            raise ValueError("backoff_factor must be at least 1")


class JsonApiClient:
    """HTTP JSON client that centralizes timeout, retries, and error classification."""

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy()
        self.session = session or requests.Session()
        self.sleep = sleep

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, object]] = None,
        json_body: Optional[Mapping[str, object]] = None,
        auth: Optional[tuple[str, str]] = None,
    ) -> Any:
        """Send one JSON API request with bounded retries for transient failures."""
        policy = self.retry_policy
        last_error: BaseException | None = None

        for attempt in range(1, policy.max_attempts + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=dict(headers or {}),
                    params=dict(params or {}),
                    json=dict(json_body or {}) if json_body is not None else None,
                    auth=auth,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                last_error = error
                logger.warning(
                    "API transport failure method=%s url=%s attempt=%s/%s type=%s",
                    method,
                    redact_secret_text(url),
                    attempt,
                    policy.max_attempts,
                    type(error).__name__,
                )
                if attempt >= policy.max_attempts:
                    message = (
                        f"API request failed after {attempt} attempts: "
                        f"{type(error).__name__}: {redact_secret_text(str(error))}"
                    )
                    raise ApiError(message) from error
                self._sleep_before_retry(attempt)
                continue
            except requests.RequestException as error:
                raise ApiError(
                    f"API request failed: {type(error).__name__}: "
                    f"{redact_secret_text(str(error))}"
                ) from error

            if response.status_code in policy.retry_statuses:
                logger.warning(
                    "API transient status method=%s url=%s status=%s attempt=%s/%s",
                    method,
                    redact_secret_text(url),
                    response.status_code,
                    attempt,
                    policy.max_attempts,
                )
                if attempt < policy.max_attempts:
                    self._sleep_before_retry(attempt)
                    continue

            if response.status_code < 200 or response.status_code >= 300:
                body = redact_secret_text((response.text or "").strip().replace("\n", " "))
                if len(body) > 240:
                    body = body[:240] + "..."
                raise ApiError(
                    f"API request returned HTTP {response.status_code}"
                    + (f": {body}" if body else "")
                )

            try:
                return response.json()
            except ValueError as error:
                raise ApiError("API response was not valid JSON") from error

        # Defensive; loop always returns or raises.
        raise ApiError(f"API request failed: {redact_secret_text(str(last_error))}")

    def _sleep_before_retry(self, completed_attempt: int) -> None:
        delay = self.retry_policy.initial_delay * (
            self.retry_policy.backoff_factor ** (completed_attempt - 1)
        )
        if delay:
            self.sleep(delay)
