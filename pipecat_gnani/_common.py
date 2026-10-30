"""Shared constants and helpers for Gnani Pipecat services.

Re-exports constants from the gnani SDK to avoid duplication.
Pipecat-specific language mapping and helpers live here.

API docs: https://docs.gnani.ai/api/introduction/introduction
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from gnani.stt.client import (
    STREAM_SUPPORTED_LANGUAGES,  # noqa: F401
    STREAM_SUPPORTED_SAMPLE_RATES,
)
from gnani.stt.client import (
    SUPPORTED_LANGUAGES as STT_SUPPORTED_LANGUAGES,  # noqa: F401
)
from gnani.stt.client import _validate_language_code  # type: ignore[import-untyped]
from gnani.stt._prisma import (  # type: ignore[import-untyped]
    INDIC_AUTO_LANGUAGE_CODE,
    PRISMA_V3_MODEL,
    build_context,
    check_format,
    normalize_model,
    parse_candidates,
    require_prisma_v3,
)
from gnani.tts.client import (  # type: ignore[import-untyped]
    DEFAULT_MODEL,  # noqa: F401
    SUPPORTED_TTS_LANGUAGES,  # noqa: F401
    SUPPORTED_VOICES,  # noqa: F401
    TIMBRE_V25_VOICES,  # noqa: F401
    TIMBRE_V30_VOICES,  # noqa: F401
)
from pipecat.transcriptions.language import Language, resolve_language

# ``DEFAULT_MODEL`` comes from the SDK (single source of truth). The SDK has no default-voice
# constant, so the plugin keeps its own; ``Pranav`` is valid on the default model.
DEFAULT_VOICE = "Pranav"

# Pipecat renamed its "not provided" sentinel type: ``_NotGiven`` (<= 1.6) became the
# public ``NotGiven`` in ``pipecat.utils.types`` (>= 1.8). Resolve whichever exists so
# the settings dataclasses work across the supported pipecat-ai range.
try:
    from pipecat.utils.types import NotGiven  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - older pipecat
    from pipecat.services.settings import _NotGiven as NotGiven  # type: ignore[attr-defined,no-redef]

GNANI_STT_REST_URL = "https://api.vachana.ai/stt/v3"
GNANI_STT_WS_URL = "wss://api.vachana.ai/stt/v3/stream"

GNANI_TTS_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"
GNANI_TTS_SSE_URL = "https://api.vachana.ai/api/v1/tts/sse"
GNANI_TTS_WS_URL = "wss://api.vachana.ai/api/v1/tts"

STT_SUPPORTED_SAMPLE_RATES = STREAM_SUPPORTED_SAMPLE_RATES
TTS_SUPPORTED_SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
SUPPORTED_SAMPLE_RATES = TTS_SUPPORTED_SAMPLE_RATES

STT_FORMAT_VERBATIM = "verbatim"
STT_FORMAT_TRANSCRIBE = "transcribe"

# STT models. ``None`` (model not set) means the server default, Prisma v2.5.
STT_MODEL_V25 = "prisma-v2.5"
STT_MODEL_V30 = PRISMA_V3_MODEL  # "prisma-v3.0"
STT_SUPPORTED_MODELS = (STT_MODEL_V25, STT_MODEL_V30)


def resolve_stt_model(model: Any) -> str | None:
    """Return the canonical STT model name, or ``None`` when unset (server default)."""
    if model is None or not isinstance(model, str):
        return None
    return normalize_model(model)


def validate_stt_options(model: Any, fmt: Any) -> None:
    """Validate STT ``model`` and ``format`` together.

    Raises:
        ValueError: If the model is unknown, or the format is not valid for that model
            (``codemix`` / ``transliterate`` need ``prisma-v3.0``).
    """
    resolved = resolve_stt_model(model)
    if resolved is not None and resolved not in STT_SUPPORTED_MODELS:
        # The WebSocket endpoint silently ignores unknown models, so refuse here rather
        # than let a typo fall back to Prisma v2.5 unnoticed.
        raise ValueError(f"model must be one of {STT_SUPPORTED_MODELS}, got '{model}'")
    if isinstance(fmt, str) and fmt:
        check_format(fmt, resolved)

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
        The Language enum when configured with a real language, otherwise ``None``.
    """
    lang = settings.language
    if isinstance(lang, Language):
        return lang
    # Pipecat stores the configured language as its string value ("hi-IN"), so map it back.
    # Non-language strings such as "indic-auto" give None.
    return language_from_code(lang)


# ---------------------------------------------------------------------------
# Prisma v3.0 request options (language auto-detect, candidates, context hints)
# ---------------------------------------------------------------------------

#: Pass as ``language=INDIC_AUTO`` (Prisma v3.0) to let the model identify the language.
INDIC_AUTO = INDIC_AUTO_LANGUAGE_CODE


@dataclass
class SttRequestOptions:
    """Validated, wire-ready STT options derived from a service's settings."""

    language_code: str
    model: str | None
    candidates: list[str] = field(default_factory=list)
    #: Prisma v3.0 context hints, keyed by wire name (``keyterms``, ``topic``,
    #: ``previous_text``, ``speaker_names``). Lists stay lists; callers encode them.
    context: dict[str, Any] = field(default_factory=dict)


def _is_set(value: Any) -> bool:
    return value is not None and not isinstance(value, NotGiven) and value != "" and value != []


def _candidate_code(item: Any) -> str:
    return stt_language_to_gnani(item) if isinstance(item, Language) else str(item)


def resolve_stt_request_options(
    settings: Any, *, supported_languages: dict[str, str]
) -> SttRequestOptions:
    """Validate STT settings and return the options to put on the wire.

    Covers ``model``, ``format``, ``language`` (including ``INDIC_AUTO``),
    ``language_candidates`` and the Prisma v3.0 context hints. Validation reuses
    the SDK's own rules, so the plugin accepts and refuses exactly what the SDK does.

    Raises:
        ValueError: On any invalid value or on a v3.0-only option used with another model.
    """
    model = resolve_stt_model(getattr(settings, "model", None))
    validate_stt_options(model, getattr(settings, "format", None))

    language_code = get_language_string(settings, stt_language_to_gnani) or "en-IN"
    _validate_language_code(language_code, model, supported_languages)

    raw_candidates = getattr(settings, "language_candidates", None)
    candidates: list[str] = []
    if _is_set(raw_candidates):
        require_prisma_v3(model, language_candidates=raw_candidates)
        if language_code != INDIC_AUTO:
            raise ValueError(
                f"language_candidates only apply with language={INDIC_AUTO!r} "
                f"(got {language_code!r}); for one language, set it as `language`"
            )
        candidates = parse_candidates(
            [_candidate_code(c) for c in raw_candidates], supported_languages
        )

    keyterms = getattr(settings, "keyterms", None)
    topic = getattr(settings, "topic", None)
    previous_text = getattr(settings, "previous_text", None)
    speaker_names = getattr(settings, "speaker_names", None)
    given = {
        k: v
        for k, v in (
            ("keyterms", keyterms),
            ("topic", topic),
            ("previous_text", previous_text),
            ("speaker_names", speaker_names),
        )
        if _is_set(v)
    }
    context: dict[str, Any] = {}
    if given:
        require_prisma_v3(model, **given)
        built = build_context(
            keywords=given.get("keyterms"),
            topic=given.get("topic"),
            previous_text=given.get("previous_text"),
            speaker_names=given.get("speaker_names"),
        )
        # The SDK calls these ``keywords``; the API (and its docs) call them ``keyterms``.
        context = {("keyterms" if k == "keywords" else k): v for k, v in built.items()}

    return SttRequestOptions(
        language_code=language_code, model=model, candidates=candidates, context=context
    )


def language_from_code(code: Any, fallback: Language | None = None) -> Language | None:
    """Map an API language code (e.g. ``detected_language_code``) to a ``Language``.

    Returns ``fallback`` when the code is missing or not a known ``Language``.
    """
    if isinstance(code, str) and code:
        try:
            return Language(code)
        except ValueError:
            pass
    return fallback
