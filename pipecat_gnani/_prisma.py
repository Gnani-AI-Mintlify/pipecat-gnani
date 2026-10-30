"""Request options for the ``prisma-v3.0`` STT model.

The rules (supported languages and formats, candidate counts, context limits) live in the
``gnani-vachana`` SDK, which is the single source of truth. This module adapts them to
Pipecat settings: it converts ``Language`` values, treats unset Pipecat settings as absent,
and keeps the call shapes the STT services use.

``prisma-v3.0``-only options raise ``ValueError`` with any other model, so a bad combination
fails when the service is built (or updated) instead of as a 400 in the middle of a call.

API docs: https://docs.gnani.ai/api/STT/speech-to-text
"""

from __future__ import annotations

from typing import Any

from gnani.stt._prisma import (  # type: ignore[import-untyped]
    INDIC_AUTO_LANGUAGE_CODE,
    PRISMA_V3_MODEL,
    build_context,
    is_prisma_v3,
    normalize_model,
    require_prisma_v3,
)
from gnani.stt._prisma import check_format as _sdk_check_format
from gnani.stt._prisma import parse_candidates as _sdk_parse_candidates
from gnani.stt.client import (  # type: ignore[import-untyped]
    STREAM_SUPPORTED_LANGUAGES,
    SUPPORTED_LANGUAGES,
    _validate_language_code,
)
from pipecat.services.settings import is_given
from pipecat.transcriptions.language import Language

STT_FORMAT_CODEMIX = "codemix"
STT_FORMAT_TRANSLITERATE = "transliterate"

# Models the plugin accepts. ``None`` (not set) uses the server default, prisma-v2.5.
STT_MODELS = ("prisma-v2.5", PRISMA_V3_MODEL)

# Languages prisma-v3.0 covers (the SDK's list; no ``as-IN`` / ``or-IN``).
PRISMA_V3_LANGUAGES = tuple(sorted(SUPPORTED_LANGUAGES))


def is_set(value: Any) -> bool:
    """Return whether an option was actually given (not unset, None or empty)."""
    if not is_given(value) or value is None or value == "":
        return False
    return not (isinstance(value, list | tuple | set | frozenset) and not value)


def check_format(fmt: Any, model: Any) -> None:
    """Raise if ``fmt`` is not valid for this model (REST and streaming share the rules)."""
    if is_set(fmt):
        _sdk_check_format(fmt, model)


def check_language(language: Any, model: Any, *, streaming: bool = False) -> None:
    """Raise if ``language`` is not valid for this model.

    A supported locale is always valid; ``indic-auto`` needs ``prisma-v3.0``.
    """
    if not is_set(language):
        return
    supported = STREAM_SUPPORTED_LANGUAGES if streaming else SUPPORTED_LANGUAGES
    _validate_language_code(language, model, supported)


def _candidate_code(value: Any) -> Any:
    """A candidate as a locale string (``Language.HI_IN`` -> ``"hi-IN"``)."""
    return value.value if isinstance(value, Language) else value


def parse_candidates(
    value: Any, language: Any, model: Any, *, streaming: bool = False
) -> list[str]:
    """Return 2-4 distinct candidate languages as BCP-47 codes (order kept).

    Candidates are ``prisma-v3.0`` only and apply only with ``indic-auto``; the API would
    silently ignore them with a forced language, so that raises here.
    """
    if not is_set(value):
        return []
    require_prisma_v3(model, language_candidates=value)
    if language != INDIC_AUTO_LANGUAGE_CODE:
        raise ValueError(
            f"language_candidates only apply with language={INDIC_AUTO_LANGUAGE_CODE!r} "
            f"(got {language!r}); for one language, set it as `language`"
        )
    if isinstance(value, list | tuple | set | frozenset):
        value = [_candidate_code(v) for v in value]
    supported = STREAM_SUPPORTED_LANGUAGES if streaming else SUPPORTED_LANGUAGES
    return _sdk_parse_candidates(value, supported)


__all__ = [
    "INDIC_AUTO_LANGUAGE_CODE",
    "PRISMA_V3_LANGUAGES",
    "PRISMA_V3_MODEL",
    "STT_FORMAT_CODEMIX",
    "STT_FORMAT_TRANSLITERATE",
    "STT_MODELS",
    "build_context",
    "check_format",
    "check_language",
    "is_prisma_v3",
    "is_set",
    "normalize_model",
    "parse_candidates",
    "require_prisma_v3",
]
