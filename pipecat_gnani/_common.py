"""Shared constants and helpers for Gnani Pipecat services.

Re-exports constants from the gnani SDK to avoid duplication.
Pipecat-specific language mapping and helpers live here.

API docs: https://docs.gnani.ai/api/introduction/introduction
"""

from collections.abc import Callable
from typing import Any, cast

from gnani.stt.client import (
    STREAM_CHUNK_BYTES,  # noqa: F401
    STREAM_SUPPORTED_LANGUAGES,  # noqa: F401
    STREAM_SUPPORTED_SAMPLE_RATES,
)
from gnani.stt.client import (
    SUPPORTED_LANGUAGES as STT_SUPPORTED_LANGUAGES,  # noqa: F401
)
from gnani.tts.client import (  # type: ignore[import-untyped]
    SUPPORTED_BITRATES,  # noqa: F401
    SUPPORTED_CONTAINERS,  # noqa: F401
    SUPPORTED_ENCODINGS,  # noqa: F401
    SUPPORTED_MODELS,  # noqa: F401
    SUPPORTED_VOICES,  # noqa: F401
)
from pipecat.transcriptions.language import Language, resolve_language

GNANI_STT_REST_URL = "https://api.vachana.ai/stt/v3"
GNANI_STT_WS_URL = "wss://api.vachana.ai/stt/v3/stream"

GNANI_TTS_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"
GNANI_TTS_SSE_URL = "https://api.vachana.ai/api/v1/tts/sse"
GNANI_TTS_WS_URL = "wss://api.vachana.ai/api/v1/tts"

STT_SUPPORTED_SAMPLE_RATES = STREAM_SUPPORTED_SAMPLE_RATES
TTS_SUPPORTED_SAMPLE_RATES = (8000, 16000, 22050, 44100)

STT_FORMAT_VERBATIM = "verbatim"
STT_FORMAT_TRANSCRIBE = "transcribe"
STT_SUPPORTED_FORMATS = (STT_FORMAT_VERBATIM, STT_FORMAT_TRANSCRIBE)

STT_LANGUAGE_MAP = cast(
    "dict[Language, str]",
    {
        Language.AS_IN: "as-IN",
        Language.BN_IN: "bn-IN",
        Language.EN_IN: "en-IN",
        Language.GU_IN: "gu-IN",
        Language.HI_IN: "hi-IN",
        Language.KN_IN: "kn-IN",
        Language.ML_IN: "ml-IN",
        Language.MR_IN: "mr-IN",
        Language.OR_IN: "or-IN",
        Language.PA_IN: "pa-IN",
        Language.TA_IN: "ta-IN",
        Language.TE_IN: "te-IN",
    },
)

TTS_LANGUAGE_MAP = cast(
    "dict[Language, str]",
    {
        Language.AS: "as-IN",
        Language.AS_IN: "as-IN",
        Language.BN: "bn-IN",
        Language.BN_IN: "bn-IN",
        Language.EN: "en-IN",
        Language.EN_IN: "en-IN",
        Language.GU: "gu-IN",
        Language.GU_IN: "gu-IN",
        Language.HI: "hi-IN",
        Language.HI_IN: "hi-IN",
        Language.KN: "kn-IN",
        Language.KN_IN: "kn-IN",
        Language.ML: "ml-IN",
        Language.ML_IN: "ml-IN",
        Language.MR: "mr-IN",
        Language.MR_IN: "mr-IN",
        Language.OR: "or-IN",
        Language.OR_IN: "or-IN",
        Language.PA: "pa-IN",
        Language.PA_IN: "pa-IN",
        Language.TA: "ta-IN",
        Language.TA_IN: "ta-IN",
        Language.TE: "te-IN",
        Language.TE_IN: "te-IN",
    },
)


def stt_language_to_gnani(language: Language) -> str:
    """Convert a Language enum to Gnani STT language code.

    Args:
        language: The Language enum value to convert.

    Returns:
        The Gnani BCP-47 language code string.
    """
    return resolve_language(language, STT_LANGUAGE_MAP, use_base_code=False)


def tts_language_to_gnani(language: Language) -> str:
    """Convert a Language enum to Gnani TTS language code.

    Args:
        language: The Language enum value to convert.

    Returns:
        The Gnani BCP-47 language code string.
    """
    return resolve_language(language, TTS_LANGUAGE_MAP, use_base_code=False)


def get_language_string(
    settings: Any,
    converter: Callable[[Language], str],
) -> str | None:
    """Resolve the language setting to a string code.

    Args:
        settings: Service settings object with a ``language`` attribute.
        converter: Callable that maps a Language enum to a provider code.

    Returns:
        The resolved language code, or ``en-IN`` when unset.
    """
    if settings.language:
        if isinstance(settings.language, Language):
            return converter(settings.language)
        return str(settings.language)
    return "en-IN"


def settings_language(settings: Any) -> Language | None:
    """Return the Language enum from settings, if set.

    Args:
        settings: Service settings object with a ``language`` attribute.

    Returns:
        The Language enum when configured, otherwise ``None``.
    """
    lang = settings.language
    if isinstance(lang, Language):
        return lang
    return None
