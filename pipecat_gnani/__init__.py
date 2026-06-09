"""Gnani Vachana speech AI service integration for Pipecat.

This package provides STT and TTS services using Gnani's Vachana platform,
with support for Indian languages and real-time streaming.

Services:
    STT:
    - GnaniHttpSTTService: REST-based file transcription (requires VAD)
    - GnaniSTTService: WebSocket streaming speech-to-text with VAD

    TTS:
    - GnaniHttpTTSService: REST-based text-to-speech
    - GnaniSSETTSService: SSE streaming text-to-speech (lower latency)
    - GnaniTTSService: WebSocket streaming text-to-speech with interruption handling
"""

__version__ = "0.3.0"

from pipecat_gnani.stt import (
    GnaniHttpSTTService,
    GnaniHttpSTTSettings,
    GnaniSTTService,
    GnaniSTTSettings,
)
from pipecat_gnani.tts import (
    GnaniHttpTTSService,
    GnaniHttpTTSSettings,
    GnaniSSETTSService,
    GnaniSSETTSSettings,
    GnaniTTSService,
    GnaniTTSSettings,
    SUPPORTED_VOICES,
)

__all__ = [
    "GnaniHttpSTTService",
    "GnaniHttpSTTSettings",
    "GnaniSTTService",
    "GnaniSTTSettings",
    "GnaniHttpTTSService",
    "GnaniHttpTTSSettings",
    "GnaniSSETTSService",
    "GnaniSSETTSSettings",
    "GnaniTTSService",
    "GnaniTTSSettings",
    "SUPPORTED_VOICES",
    "__version__",
]
