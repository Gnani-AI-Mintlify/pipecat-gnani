import platform

import pipecat_gnani


def sdk_headers() -> dict[str, str]:
    """SDK identification headers for Gnani Vachana API."""
    return {
        "User-Agent": f"PipecatGnani/{pipecat_gnani.__version__} Python/{platform.python_version()}",
    }
