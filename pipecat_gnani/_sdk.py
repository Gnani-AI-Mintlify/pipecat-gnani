"""SDK identification headers for Gnani Vachana API requests."""

import platform

import pipecat_gnani


def sdk_headers() -> dict[str, str]:
    """Build HTTP headers that identify this Pipecat integration to Gnani.

    Returns:
        Header dict with ``User-Agent`` for request tracing.
    """
    return {
        "User-Agent": f"PipecatGnani/{pipecat_gnani.__version__} Python/{platform.python_version()}",
    }
