"""GPU-tenant and service-readiness checks. Python only verifies state — it never starts,
stops, or otherwise owns container lifecycle (that stays with the root Makefile)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 5.0


class GpuTenantError(RuntimeError):
    """The GPU tenant that must be stopped for this phase is still answering."""


class ServiceNotReadyError(RuntimeError):
    """A required service did not become ready before the deadline."""


def require_down(name: str, url: str, make_hint: str) -> None:
    """Raise unless ``name`` is unreachable at ``url`` (the GPU tenant this phase needs down).

    Connection-refused is the only outcome that means "down". Any HTTP response, at any
    status, means the tenant is still answering and sharing the GPU. A timeout also raises,
    because the tenant's state is then genuinely unknown.
    """
    try:
        resp = requests.get(url, timeout=PROBE_TIMEOUT_SECONDS)
    except requests.ConnectionError:
        return
    except requests.Timeout as exc:
        raise GpuTenantError(
            f"{name} at {url} did not respond within {PROBE_TIMEOUT_SECONDS}s "
            f"(state unknown) — run `make {make_hint}` first"
        ) from exc
    raise GpuTenantError(
        f"{name} is answering at {url} (HTTP {resp.status_code}); it shares the GPU with "
        f"this phase — run `make {make_hint}` first"
    )


def _poll_until_ready(
    description: str,
    probe: Callable[[], tuple[bool, str]],
    deadline_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> None:
    start = now()
    last_state = "never probed"
    while True:
        try:
            ready, last_state = probe()
        except requests.ConnectionError as exc:
            ready, last_state = False, f"connection refused: {exc}"
        if ready:
            return
        elapsed = now() - start
        if elapsed >= deadline_seconds:
            raise ServiceNotReadyError(
                f"{description} was not ready after {deadline_seconds}s; "
                f"last observed state: {last_state}"
            )
        logger.info("%s not ready yet (elapsed %.0fs): %s", description, elapsed, last_state)
        sleep(POLL_INTERVAL_SECONDS)


def wait_ocr_ready(base_url: str, deadline_seconds: float, **poll_kwargs: Callable) -> None:
    def probe() -> tuple[bool, str]:
        resp = requests.get(f"{base_url}/healthz", timeout=PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}"
        body = resp.json()
        return body["ready"] is True, f"body: {body}"

    _poll_until_ready("OCR service", probe, deadline_seconds, **poll_kwargs)


def wait_llm_serving(
    base_url: str, api_key: str, model: str, deadline_seconds: float, **poll_kwargs: Callable
) -> None:
    def probe() -> tuple[bool, str]:
        resp = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}"
        model_ids = [entry["id"] for entry in resp.json()["data"]]
        return model in model_ids, f"models listed: {model_ids}"

    _poll_until_ready(f"LLM serving {model!r}", probe, deadline_seconds, **poll_kwargs)


def wait_memory_ready(base_url: str, deadline_seconds: float, **poll_kwargs: Callable) -> None:
    def probe() -> tuple[bool, str]:
        resp = requests.get(f"{base_url}/health", timeout=PROBE_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}"
        body = resp.json()
        return body["ready"] is True, f"body: {body}"

    _poll_until_ready("Memory service", probe, deadline_seconds, **poll_kwargs)
