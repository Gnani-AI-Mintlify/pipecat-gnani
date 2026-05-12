"""Gnani Vachana speech AI service integration for Pipecat.

This package provides STT and TTS services using Gnani's Vachana platform,
with support for Indian languages and real-time streaming.

Services:
    - GnaniSTTService: WebSocket streaming speech-to-text with VAD
    - GnaniHttpTTSService: REST-based text-to-speech
    - GnaniTTSService: WebSocket streaming text-to-speech with interruption handling
"""

from pipecat_gnani.stt import GnaniSTTService, GnaniSTTSettings
from pipecat_gnani.tts import (
    GnaniHttpTTSService,
    GnaniHttpTTSSettings,
    GnaniTTSService,
    GnaniTTSSettings,
    SUPPORTED_VOICES,
)

__version__ = "0.1.0"

__all__ = [
    "GnaniSTTService",
    "GnaniSTTSettings",
    "GnaniHttpTTSService",
    "GnaniHttpTTSSettings",
    "GnaniTTSService",
    "GnaniTTSSettings",
    "SUPPORTED_VOICES",
    "__version__",
]
