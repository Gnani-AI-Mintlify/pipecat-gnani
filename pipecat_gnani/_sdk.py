"""SDK identification headers and WebSocket helpers for Gnani Vachana API requests."""

import platform
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


def sdk_headers() -> dict[str, str]:
    """Build HTTP headers that identify this Pipecat integration to Gnani.

    Returns:
        Header dict with ``User-Agent`` for request tracing.
    """
    return {
        "User-Agent": f"PipecatGnani/{pipecat_gnani.__version__} Python/{platform.python_version()}",
    }
