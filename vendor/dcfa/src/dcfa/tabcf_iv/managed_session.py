"""Scoped credentials and structured quota evidence for interactive managed runs."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from dcfa.errors import BackendError, ErrorCode

MANAGED_SESSION_LOCK = threading.RLock()


@dataclass(frozen=True)
class QuotaUsage:
    daily_used: int
    daily_limit: int
    monthly_used: int
    monthly_limit: int

    @classmethod
    def parse(cls, value: Any) -> QuotaUsage | None:
        if not isinstance(value, dict):
            return None
        keys = (
            "daily_tokens_used",
            "daily_token_limit",
            "monthly_tokens_used",
            "monthly_token_limit",
        )
        values = [value.get(key) for key in keys]
        if any(type(v) is not int or v < 0 for v in values):
            return None
        return cls(*values)

    @property
    def exhausted(self) -> bool:
        return self.daily_used >= self.daily_limit or self.monthly_used >= self.monthly_limit


def quota_error(usage: QuotaUsage, *, stage: str) -> BackendError:
    from dataclasses import asdict

    return BackendError(
        ErrorCode.MANAGED_QUOTA_EXHAUSTED,
        "The service confirmed that the API token allowance is exhausted.",
        stage=stage,
        context={"quota": asdict(usage)},
    )


def response_guard(usage_reader: Callable[[], QuotaUsage | None]):
    """Intercept errors before the SDK flattens them or logs their bodies.

    Upload deduplication responses (409) remain owned by the official client.
    A 429 alone is never quota evidence. No free-text error matching is used.
    """

    def guard(response: Any) -> None:
        status = response.status_code
        if status not in {400, 401, 403, 402, 408, 422, 426, 429} and status < 500:
            return
        code = ErrorCode.MANAGED_SERVICE_FAILED
        if status == 429:
            usage = usage_reader()
            if usage is not None and usage.exhausted:
                raise quota_error(usage, stage="managed_client.http")
            code = ErrorCode.MANAGED_RATE_LIMITED
        elif status in {401, 403}:
            code = ErrorCode.DATA_ACCESS_BLOCKED
        elif status == 426:
            code = ErrorCode.UNSUPPORTED_BACKEND_PROFILE
        elif status in {400, 422}:
            code = ErrorCode.INVALID_DATA
        raise BackendError(
            code,
            "The managed service rejected the request.",
            stage="managed_client.http",
            context={"http_status": status},
        )

    return guard


@contextmanager
def managed_session(client: Any, token: str, *, capture_errors: bool = True) -> Iterator[Any]:
    """Serialize the SDK singleton, restoring HTTP hooks and clearing credentials."""
    import httpx

    with MANAGED_SESSION_LOCK:

        def usage_reader() -> QuotaUsage | None:
            # Separate transport avoids recursive hooks and SDK error-body logging.
            try:
                with httpx.Client(timeout=15, follow_redirects=False) as transport:
                    response = transport.post(
                        "https://api.priorlabs.ai/get_api_usage/",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                if response.status_code == 200:
                    return QuotaUsage.parse(response.json())
            except (httpx.HTTPError, ValueError):
                pass
            return None

        hook = response_guard(usage_reader)
        hooks = None
        try:
            if capture_errors:
                from tabpfn_client.client import ServiceClient

                hooks = ServiceClient.httpx_client.event_hooks["response"]
                hooks.append(hook)
            client.set_access_token(token)
            yield usage_reader
        finally:
            if hooks is not None:
                hooks.remove(hook)
            try:
                client.reset()
            finally:
                if capture_errors:
                    from tabpfn_client.client import ServiceClient
                    from tabpfn_client.options import get_opts

                    ServiceClient.reset_authorization()
                    get_opts().TABPFN_TOKEN = None
