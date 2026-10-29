"""Request options for the ``prisma-v3.0`` STT model.

``prisma-v3.0`` is one multilingual model for ten Indian languages. It can
identify the language itself (``language="indic-auto"``), take 2-4 *candidate*
languages as a hint, write a third output style (``codemix``, REST only), and
accept request context (``keywords`` on both transports; ``topic``,
``previous_text`` and ``speaker_names`` on REST only).

None of that applies to the other models, so these options raise ``ValueError``
with any other ``model`` rather than being silently ignored by the API.

The limits mirror asr-server's so a bad value fails when the service is built,
not as a 400 in the middle of a call. They are kept here rather than imported
from ``gnani-vachana`` so this package works with the SDK versions it already
supports.

API docs: https://docs.gnani.ai/api/STT/speech-to-text
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pipecat.services.settings import is_given
from pipecat.transcriptions.language import Language

PRISMA_V3_MODEL = "prisma-v3.0"

# ``language`` value that lets prisma-v3.0 identify the language itself.
INDIC_AUTO_LANGUAGE_CODE = "indic-auto"

# The ten languages prisma-v3.0 covers (no ``as-IN`` / ``or-IN``).
PRISMA_V3_LANGUAGES = (
    "bn-IN",
    "en-IN",
    "gu-IN",
    "hi-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "pa-IN",
    "ta-IN",
    "te-IN",
)

STT_FORMAT_CODEMIX = "codemix"

PRISMA_V3_MIN_CANDIDATES = 2
PRISMA_V3_MAX_CANDIDATES = 4
PRISMA_V3_MAX_KEYWORDS = 200
PRISMA_V3_TOPIC_MIN_CHARS = 30
PRISMA_V3_TOPIC_MAX_CHARS = 1600
PRISMA_V3_PREVIOUS_TEXT_MIN_CHARS = 12
PRISMA_V3_MAX_SPEAKER_NAMES = 4

_TAG_MARKERS = ("<|", "|>")

# The only context shapes the model accepts; anything else is 400 INVALID_CONTEXT.
_ALLOWED_CONTEXT = frozenset(
    {
        frozenset(),
        frozenset({"keywords"}),
        frozenset({"topic"}),
        frozenset({"topic", "keywords"}),
        frozenset({"speaker_names"}),
        frozenset({"previous_text"}),
    }
)

StrList = str | Iterable[str] | None


def is_prisma_v3(model: Any) -> bool:
    """Return whether ``model`` names prisma-v3.0 (case-insensitive)."""
    return isinstance(model, str) and model.strip().lower() == PRISMA_V3_MODEL


def is_set(value: Any) -> bool:
    """Return whether an option was actually given (not None/empty)."""
    if not is_given(value) or value is None or value == "":
        return False
    return not (isinstance(value, list | tuple | set | frozenset) and not value)


def require_prisma_v3(model: Any, **options: Any) -> None:
    """Raise if any prisma-v3.0-only option is set for another model."""
    sent = [name for name, value in options.items() if is_set(value)]
    if sent and not is_prisma_v3(model):
        raise ValueError(
            f"{', '.join(sent)} {'is' if len(sent) == 1 else 'are'} only supported "
            f"with model={PRISMA_V3_MODEL!r} (got model={model!r})"
        )


def check_format(fmt: Any, model: Any, *, streaming: bool) -> None:
    """Raise if ``fmt`` is not valid for this model and transport."""
    if not is_set(fmt):
        return
    allowed: tuple[str, ...] = ("verbatim", "transcribe")
    if not streaming and is_prisma_v3(model):
        allowed = (*allowed, STT_FORMAT_CODEMIX)
    if fmt in allowed:
        return
    hint = ""
    if fmt == STT_FORMAT_CODEMIX:
        hint = (
            " ('codemix' is REST-only: use GnaniHttpSTTService)"
            if streaming
            else f" ('codemix' needs model={PRISMA_V3_MODEL!r})"
        )
    raise ValueError(
        f"format must be one of {', '.join(repr(a) for a in allowed)}, got {fmt!r}{hint}"
    )


def _to_list(field: str, value: Any) -> list[str]:
    """A list, a JSON-array string, or a comma-separated string, trimmed and de-duplicated."""
    if not is_set(value):
        return []
    items: list[Any]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{field} must be a list of strings") from exc
            if not isinstance(parsed, list):
                raise ValueError(f"{field} must be a list of strings")
            items = parsed
        else:
            items = text.split(",")
    else:
        items = list(value)
    out: list[str] = []
    for item in items:
        if isinstance(item, Language):
            item = item.value
        if not isinstance(item, str):
            raise ValueError(f"{field} must be a list of strings")
        word = item.strip()
        if word and word not in out:
            out.append(word)
    return out


def _check_markers(field: str, *values: str) -> None:
    for v in values:
        if any(m in v for m in _TAG_MARKERS):
            raise ValueError(f"{field} must not contain '<|' or '|>'")


def check_language(language: Any, model: Any) -> None:
    """Validate the session language against the model.

    ``indic-auto`` needs prisma-v3.0, and prisma-v3.0 covers only
    ``PRISMA_V3_LANGUAGES``. Other models are left to the API, as before.
    """
    if language == INDIC_AUTO_LANGUAGE_CODE:
        if not is_prisma_v3(model):
            raise ValueError(
                f"language={INDIC_AUTO_LANGUAGE_CODE!r} needs model={PRISMA_V3_MODEL!r}"
            )
        return
    if is_prisma_v3(model) and is_set(language) and language not in PRISMA_V3_LANGUAGES:
        raise ValueError(
            f"{PRISMA_V3_MODEL} does not support language {language!r}. Choose from: "
            f"{', '.join(PRISMA_V3_LANGUAGES)}, or {INDIC_AUTO_LANGUAGE_CODE!r}"
        )


def parse_candidates(value: Any, language: Any, model: Any) -> list[str]:
    """Return 2-4 distinct candidate languages as BCP-47 codes (order kept).

    Candidates are prisma-v3.0 only and apply only with ``indic-auto``; the API
    would silently ignore them with a forced language, so that raises here.
    """
    codes = _to_list("language_candidates", value)
    if not codes:
        return []
    require_prisma_v3(model, language_candidates=codes)
    if language != INDIC_AUTO_LANGUAGE_CODE:
        raise ValueError(
            f"language_candidates only apply with language={INDIC_AUTO_LANGUAGE_CODE!r} "
            f"(got {language!r})"
        )
    bad = [c for c in codes if c not in PRISMA_V3_LANGUAGES]
    if bad:
        raise ValueError(
            f"Unsupported language_candidates {', '.join(repr(b) for b in bad)}. "
            f"Choose from: {', '.join(PRISMA_V3_LANGUAGES)}"
        )
    if not PRISMA_V3_MIN_CANDIDATES <= len(codes) <= PRISMA_V3_MAX_CANDIDATES:
        raise ValueError(
            f"language_candidates takes {PRISMA_V3_MIN_CANDIDATES}-{PRISMA_V3_MAX_CANDIDATES} "
            f"distinct languages, got {len(codes)}. For one language, set it as "
            f"language instead."
        )
    return codes


def build_context(
    *,
    keywords: Any = None,
    topic: Any = None,
    previous_text: Any = None,
    speaker_names: Any = None,
) -> dict[str, Any]:
    """Validate the context options and return only those that were set."""
    ctx: dict[str, Any] = {}
    words = _to_list("keywords", keywords)
    if words:
        _check_markers("keywords", *words)
        if len(words) > PRISMA_V3_MAX_KEYWORDS:
            raise ValueError(
                f"keywords takes at most {PRISMA_V3_MAX_KEYWORDS} items, got {len(words)}"
            )
        ctx["keywords"] = words
    if is_set(topic) and str(topic).strip():
        t = str(topic).strip()
        _check_markers("topic", t)
        if not PRISMA_V3_TOPIC_MIN_CHARS <= len(t) <= PRISMA_V3_TOPIC_MAX_CHARS:
            raise ValueError(
                f"topic must be {PRISMA_V3_TOPIC_MIN_CHARS}-{PRISMA_V3_TOPIC_MAX_CHARS} "
                f"characters, got {len(t)}"
            )
        ctx["topic"] = t
    if is_set(previous_text) and str(previous_text).strip():
        p = str(previous_text).strip()
        _check_markers("previous_text", p)
        if len(p) < PRISMA_V3_PREVIOUS_TEXT_MIN_CHARS:
            raise ValueError(
                f"previous_text must be at least {PRISMA_V3_PREVIOUS_TEXT_MIN_CHARS} "
                f"characters, got {len(p)}"
            )
        ctx["previous_text"] = p
    names = _to_list("speaker_names", speaker_names)
    if names:
        _check_markers("speaker_names", *names)
        if len(names) > PRISMA_V3_MAX_SPEAKER_NAMES:
            raise ValueError(
                f"speaker_names takes at most {PRISMA_V3_MAX_SPEAKER_NAMES} names, got {len(names)}"
            )
        if any("\n" in n or "\r" in n for n in names):
            raise ValueError("speaker_names must each be a single line")
        ctx["speaker_names"] = names
    if frozenset(ctx) not in _ALLOWED_CONTEXT:
        raise ValueError(
            f"{PRISMA_V3_MODEL} accepts one of: keywords, topic, topic + keywords, "
            f"speaker_names, or previous_text (got {' + '.join(sorted(ctx))})"
        )
    return ctx
