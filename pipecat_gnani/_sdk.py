"""SDK identification headers and WebSocket helpers for Gnani Vachana API requests."""

import platform
import uuid
from typing import Any

from websockets.asyncio.client import connect as websocket_connect

import pipecat_gnani


async def ws_connect(service: Any, uri: str, headers: dict[str, str]) -> Any:
    """Open a WebSocket for ``service``.

    Pipecat 1.14+ provides ``_websocket_connect()``, which applies the service's
    send and close timeouts; older releases connect directly.
    """
    connect = getattr(service, "_websocket_connect", None)
    if connect is not None:
        return await connect(uri, additional_headers=headers)
    return await websocket_connect(uri, additional_headers=headers)


def _generate_request_id() -> str:
    """Generate a unique request ID for Gnani API correlation."""
    return f"pc_req_{uuid.uuid4().hex[:12]}"


def sdk_headers(request_id: str | None = None) -> dict[str, str]:
    """Build HTTP headers for Gnani API calls.

    Args:
        request_id: Optional correlation ID sent as ``X-API-Request-ID``.

    Returns:
        Header dict with ``User-Agent`` and optional ``X-API-Request-ID``.
    """
    headers = {
        "User-Agent": f"PipecatGnani/{pipecat_gnani.__version__} Python/{platform.python_version()}",
        "X-Source": "pipecat",
    }
    if request_id:
        headers["X-API-Request-ID"] = request_id
    return headers
