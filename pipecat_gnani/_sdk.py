"""SDK identification headers and WebSocket helpers for Gnani Vachana API requests."""

import platform
import uuid
from typing import Any

import pipecat_gnani


def ws_header_kwargs(headers: dict[str, str]) -> dict[str, Any]:
    """Return the correct ``connect()`` header kwarg for the installed websockets.

    websockets >= 13 renamed ``extra_headers`` to ``additional_headers``. Support
    both so WebSocket STT/TTS work when another dependency pins websockets < 13.
    """
    try:
        import websockets

        major = int(websockets.__version__.split(".", 1)[0])
    except (ImportError, AttributeError, ValueError):
        major = 13
    key = "additional_headers" if major >= 13 else "extra_headers"
    return {key: headers}


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
    }
    if request_id:
        headers["X-API-Request-ID"] = request_id
    return headers
