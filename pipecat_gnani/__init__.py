"""Gnani Vachana speech AI service integration for Pipecat.

This package provides STT and TTS services using Gnani's Vachana platform,
with support for Indian languages and real-time streaming.

Services:
    STT:
    - GnaniHttpSTTService: REST-based file transcription (requires VAD)
    - GnaniSTTService: WebSocket streaming speech-to-text with VAD
    Both support the multilingual ``prisma-v3.0`` model (``model="prisma-v3.0"``).

    TTS:
    - GnaniHttpTTSService: REST-based text-to-speech
    - GnaniSSETTSService: SSE streaming text-to-speech (lower latency)
    - GnaniTTSService: WebSocket streaming text-to-speech with interruption handling

API docs: https://docs.gnani.ai/api/introduction/introduction
"""

__version__ = "0.6.0"
from pipecat_gnani._common import (
    DEFAULT_MODEL,
    STT_FORMAT_TRANSCRIBE,
    STT_FORMAT_VERBATIM,
    SUPPORTED_SAMPLE_RATES,
    SUPPORTED_TTS_LANGUAGES,
    SUPPORTED_VOICES,
    TIMBRE_MODELS,
    TIMBRE_V25_VOICES,
    TIMBRE_V30_VOICES,
)
from pipecat_gnani._prisma import (
    INDIC_AUTO_LANGUAGE_CODE,
    PRISMA_V3_LANGUAGES,
    PRISMA_V3_MODEL,
    STT_FORMAT_CODEMIX,
    STT_FORMAT_TRANSLITERATE,
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
    "INDIC_AUTO_LANGUAGE_CODE",
    "PRISMA_V3_LANGUAGES",
    "PRISMA_V3_MODEL",
    "STT_FORMAT_CODEMIX",
    "STT_FORMAT_TRANSCRIBE",
    "STT_FORMAT_TRANSLITERATE",
    "STT_FORMAT_VERBATIM",
    "SUPPORTED_SAMPLE_RATES",
    "SUPPORTED_TTS_LANGUAGES",
    "SUPPORTED_VOICES",
    "TIMBRE_MODELS",
    "TIMBRE_V25_VOICES",
    "TIMBRE_V30_VOICES",
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


# Audio-format constants that used to be re-exported from the Gnani SDK. They list formats
# (mp3, ogg, mulaw, alaw, bitrates) that this package now rejects, because Pipecat plays
# 16-bit PCM only. Still importable for one release, with a DeprecationWarning.
_DEPRECATED_EXPORTS = ("SUPPORTED_BITRATES", "SUPPORTED_CONTAINERS", "SUPPORTED_ENCODINGS")


def __getattr__(name: str):
    if name in _DEPRECATED_EXPORTS:
        import warnings

        import gnani.tts.client as _sdk_tts

        warnings.warn(
            f"pipecat_gnani.{name} is deprecated and will be removed in a future release. "
            "It lists audio formats this package no longer accepts (only linear_pcm with a "
            "wav/raw container works in Pipecat).",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_sdk_tts, name)
    raise AttributeError(f"module 'pipecat_gnani' has no attribute {name!r}")
