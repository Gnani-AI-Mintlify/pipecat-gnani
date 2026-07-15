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

API docs: https://docs.gnani.ai/api/introduction/introduction
"""

__version__ = "0.5.8"
from pipecat_gnani._common import (
    DEFAULT_MODEL,
    STT_FORMAT_TRANSCRIBE,
    STT_FORMAT_VERBATIM,
    SUPPORTED_TTS_LANGUAGES,
    SUPPORTED_VOICES,
    TIMBRE_V20_VOICES,
    TIMBRE_V25_VOICES,
)
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
)

__all__ = [
    "DEFAULT_MODEL",
    "STT_FORMAT_TRANSCRIBE",
    "STT_FORMAT_VERBATIM",
    "SUPPORTED_TTS_LANGUAGES",
    "SUPPORTED_VOICES",
    "TIMBRE_V20_VOICES",
    "TIMBRE_V25_VOICES",
    "GnaniHttpSTTService",
    "GnaniHttpSTTSettings",
    "GnaniHttpTTSService",
    "GnaniHttpTTSSettings",
    "GnaniSSETTSService",
    "GnaniSSETTSSettings",
    "GnaniSTTService",
    "GnaniSTTSettings",
    "GnaniTTSService",
    "GnaniTTSSettings",
    "__version__",
]
