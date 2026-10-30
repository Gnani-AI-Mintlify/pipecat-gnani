"""Gnani Speech-to-Text service implementations.

Services:

- GnaniHttpSTTService — REST-based file transcription (requires VAD)
- GnaniSTTService — WebSocket streaming transcription with real-time VAD

Both accept ``model="prisma-v3.0"``, the multilingual model: it can identify
the language itself (``language="indic-auto"``), take 2-4 candidate languages,
and reports the language of each transcript on the frame's ``language``.

API docs: https://docs.gnani.ai/api/STT/speech-to-text
"""

import asyncio
import copy
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import SegmentedSTTService, WebsocketSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt
from websockets.protocol import State

from pipecat_gnani._common import (
    GNANI_STT_REST_URL,
    GNANI_STT_WS_URL,
    NOT_GIVEN,
    STREAM_CHUNK_BYTES,
    STT_SUPPORTED_SAMPLE_RATES,
    NotGiven,
    get_language_string,
    is_given,
    language_from_gnani,
    settings_language,
    stt_language_to_gnani,
)
from pipecat_gnani._prisma import (
    INDIC_AUTO_LANGUAGE_CODE,
    STT_MODELS,
    build_context,
    check_format,
    check_language,
    is_prisma_v3,
    is_set,
    normalize_model,
    parse_candidates,
    require_prisma_v3,
)
from pipecat_gnani._sdk import _generate_request_id, sdk_headers, ws_connect

_DEFAULT_STT_SAMPLE_RATE = 16000


def _make_transcript_frame(
    text: str,
    *,
    is_final: bool,
    user_id: str,
    language: Language | None = None,
    result: Any | None = None,
) -> TranscriptionFrame | InterimTranscriptionFrame:
    """Build a final or interim transcription frame for STT output."""
    timestamp = time_now_iso8601()
    if is_final:
        return TranscriptionFrame(
            text=text,
            user_id=user_id,
            timestamp=timestamp,
            language=language,
            result=result,
            finalized=True,
        )
    return InterimTranscriptionFrame(
        text=text,
        user_id=user_id,
        timestamp=timestamp,
        language=language,
        result=result,
    )


def _model_name(model: Any) -> str | None:
    """Return the model to send, or ``None`` for the server default."""
    if not is_set(model) or not str(model).strip():
        return None
    name = normalize_model(str(model))
    if name not in STT_MODELS:
        raise ValueError(f"model must be one of {', '.join(STT_MODELS)}, got {str(model)!r}")
    return name


def _frame_language(payload: dict[str, Any], settings: Any) -> Language | None:
    """Language for a transcript frame.

    prisma-v3.0 reports ``detected_language_code`` per transcript, which is
    what an ``indic-auto`` session needs; otherwise use the configured language.
    """
    return language_from_gnani(payload.get("detected_language_code")) or settings_language(settings)


def _drop_stale_candidates(settings: Any, changed: dict[str, Any]) -> None:
    """Clear candidates when the language moves off ``indic-auto``.

    Candidates only apply to ``indic-auto`` (the server drops them on a
    language change too), so a plain language switch should not fail on them.
    """
    if (
        "language" in changed
        and "language_candidates" not in changed
        and settings.language != INDIC_AUTO_LANGUAGE_CODE
    ):
        settings.language_candidates = None


def _build_rest_fields(settings: Any) -> dict[str, str]:
    """Validate REST settings and return the ``POST /stt/v3`` form fields.

    Raises:
        ValueError: If an option is invalid, or prisma-v3.0-only with another model.
    """
    model = _model_name(settings.model)
    lang = get_language_string(settings, stt_language_to_gnani) or "en-IN"
    fmt = getattr(settings, "format", None)
    check_language(lang, model)
    check_format(fmt, model)
    candidates = parse_candidates(getattr(settings, "language_candidates", None), lang, model)
    context = {
        "keywords": getattr(settings, "keywords", None),
        "topic": getattr(settings, "topic", None),
        "previous_text": getattr(settings, "previous_text", None),
        "speaker_names": getattr(settings, "speaker_names", None),
    }
    require_prisma_v3(model, **context)

    fields: dict[str, str] = {"language_code": lang}
    if model:
        fields["model"] = model
    if is_set(fmt):
        fields["format"] = fmt
    itn = getattr(settings, "itn_native_numerals", None)
    if is_set(itn) and itn:
        fields["itn_native_numerals"] = "true"
    if candidates:
        fields["multi_lang_codes"] = ",".join(candidates)
    if is_prisma_v3(model):
        for key, value in build_context(**context).items():
            # Lists go as JSON arrays so an item may contain a comma.
            fields[key] = (
                json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
            )
    return fields


def _build_ws_option_headers(settings: Any) -> dict[str, str]:
    """Validate streaming settings and return the option headers for the handshake.

    Raises:
        ValueError: If an option is invalid, or prisma-v3.0-only with another model.
    """
    model = _model_name(settings.model)
    lang = get_language_string(settings, stt_language_to_gnani) or "en-IN"
    fmt = getattr(settings, "format", None)
    keywords = getattr(settings, "keywords", None)
    check_language(lang, model, streaming=True)
    check_format(fmt, model)
    candidates = parse_candidates(
        getattr(settings, "language_candidates", None), lang, model, streaming=True
    )
    require_prisma_v3(model, keywords=keywords)

    headers: dict[str, str] = {"lang_code": lang}
    if model:
        headers["x-model"] = model
    if is_set(fmt):
        headers["x-format"] = fmt
    itn = getattr(settings, "itn_native_numerals", None)
    if is_set(itn) and itn:
        headers["x-itn-native-numerals"] = "true"
    if candidates:
        headers["x-language-candidates"] = ",".join(candidates)
    if is_prisma_v3(model):
        words = build_context(keywords=keywords).get("keywords")
        if words:
            # HTTP headers are ASCII: JSON-escape non-ASCII keywords.
            headers["x-keywords"] = json.dumps(words, ensure_ascii=True)
    return headers


# ---------------------------------------------------------------------------
# REST (HTTP) STT
# ---------------------------------------------------------------------------


@dataclass
class GnaniHttpSTTSettings(STTSettings):
    """Settings for GnaniHttpSTTService (REST).

    Parameters:
        model: STT model. ``None`` (default) uses the server's default model;
            ``"prisma-v3.0"`` is the multilingual model, which unlocks the
            options marked *prisma-v3.0 only* below.
        language: A ``Language`` or BCP-47 code. With prisma-v3.0,
            ``"indic-auto"`` lets the model identify the language; the
            detected language is set on each ``TranscriptionFrame``.
        format: 'verbatim' or 'transcribe' (enables ITN). prisma-v3.0 also takes
            'codemix' (English words in Latin script, numbers as words) and
            'transliterate' (Indic speech in Latin letters).
        itn_native_numerals: When format='transcribe', render digits in native script.
        language_candidates: *prisma-v3.0 only, with language="indic-auto"*.
            2-4 languages the speaker is likely to use. A hint, not a limit.
        keywords: *prisma-v3.0 only*. Words or short phrases to favour
            (names, brands, product terms), up to 200.
        topic: *prisma-v3.0 only*. What the conversation is about, up to 1,600 characters.
        previous_text: *prisma-v3.0 only*. Transcript just before this
            segment (the last 600 characters are used).
        speaker_names: *prisma-v3.0 only*. 1-4 names that may be spoken.

    The context options can be combined. All rules come from the ``gnani-vachana`` SDK.
    Audio is limited to 30 s per request.
    """

    format: str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    itn_native_numerals: bool | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    language_candidates: list[str | Language] | str | NotGiven | None = field(
        default_factory=lambda: NOT_GIVEN
    )
    keywords: list[str] | str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    topic: str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    previous_text: str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    speaker_names: list[str] | str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)


def _default_http_stt_settings(
    settings_cls: type[GnaniHttpSTTSettings],
    *,
    language: Language = Language.EN_IN,
) -> GnaniHttpSTTSettings:
    """Build a store-mode settings object with every field explicitly set."""
    return settings_cls(
        model=None,
        language=language,
        format=None,
        itn_native_numerals=None,
        language_candidates=None,
        keywords=None,
        topic=None,
        previous_text=None,
        speaker_names=None,
    )


class GnaniHttpSTTService(SegmentedSTTService):
    """REST-based speech-to-text service using Gnani Vachana API.

    Transcribes complete audio segments via HTTP POST. Requires VAD to be
    enabled in the pipeline so that speech segments are buffered and sent
    as whole utterances.

    Example::

        stt = GnaniHttpSTTService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniHttpSTTService.Settings(
                language=Language.HI_IN,
            ),
        )

    Let prisma-v3.0 identify the language (each frame's ``language`` is the
    detected one)::

        stt = GnaniHttpSTTService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniHttpSTTService.Settings(
                model="prisma-v3.0",
                language="indic-auto",
                language_candidates=["hi-IN", "en-IN"],  # optional hint
            ),
        )
    """

    Settings = GnaniHttpSTTSettings
    _settings: GnaniHttpSTTSettings

    def __init__(
        self,
        *,
        api_key: str,
        aiohttp_session: aiohttp.ClientSession,
        settings: GnaniHttpSTTSettings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani REST STT service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            aiohttp_session: Shared aiohttp session for HTTP requests.
            settings: Runtime-updatable STT settings (model, language, format, ITN
                and prisma-v3.0 options).
            **kwargs: Additional arguments passed to the parent SegmentedSTTService.

        Raises:
            ValueError: If a setting is invalid for the chosen model.
        """
        default_settings = _default_http_stt_settings(self.Settings)

        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(settings=default_settings, **kwargs)

        # Fail at construction rather than as a 400 on the first utterance.
        _build_rest_fields(self._settings)

        self._api_key = api_key
        self._session = aiohttp_session

    async def _update_settings(self, delta: STTSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply a settings delta, keeping the old settings if the result is invalid.

        Args:
            delta: Settings delta from an ``STTUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If the updated settings are invalid for the chosen model.
        """
        previous = copy.copy(self._settings)
        changed = await super()._update_settings(delta)
        _drop_stale_candidates(self._settings, changed)
        try:
            _build_rest_fields(self._settings)
        except ValueError:
            self._settings = previous
            raise
        return changed

    def can_generate_metrics(self) -> bool:
        """Return whether this service can emit processing metrics.

        Returns:
            True — metrics are supported for REST transcription.
        """
        return True

    def language_to_service_language(self, language: Language) -> str:
        """Convert a Language enum to a Gnani STT language code.

        Args:
            language: The Language enum value to convert.

        Returns:
            The Gnani BCP-47 language code string.
        """
        return stt_language_to_gnani(language)

    @traced_stt
    async def _handle_transcription(
        self, transcript: str, is_final: bool, language: Language | None = None
    ):
        """Record a transcription result for tracing and metrics.

        Args:
            transcript: Recognized speech text.
            is_final: Whether this is a final (vs interim) transcript.
            language: Detected or configured language, if known.
        """
        pass

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:  # type: ignore[override]
        """Transcribe a complete audio segment via the Gnani REST API.

        Args:
            audio: WAV audio of one speech segment from the pipeline VAD segmenter.

        Yields:
            TranscriptionFrame on success, ErrorFrame on API or network failure.
        """
        request_id = _generate_request_id()
        try:
            await self.start_processing_metrics()

            fields = _build_rest_fields(self._settings)

            headers = {"X-API-Key-ID": self._api_key, **sdk_headers(request_id=request_id)}
            logger.debug(
                "[STT HTTP] transcribe start | request_id={} | language={} | model={}",
                request_id,
                fields["language_code"],
                fields.get("model", "default"),
            )

            form = aiohttp.FormData()
            form.add_field("audio_file", audio, filename="audio.wav", content_type="audio/wav")
            for name, value in fields.items():
                form.add_field(name, value)

            async with self._session.post(
                GNANI_STT_REST_URL, data=form, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    msg = f"Gnani STT API error: {error_text}"
                    logger.error(
                        "[STT HTTP] transcribe failed | request_id={} | error={}",
                        request_id,
                        msg,
                    )
                    yield ErrorFrame(error=msg)
                    return
                result = await response.json()

            await self.stop_processing_metrics()

            text = (result.get("transcript") or "").strip()
            logger.debug(
                "[STT HTTP] transcribe complete | request_id={} | transcript_length={} | detected_language={}",
                request_id,
                len(text),
                result.get("detected_language_code"),
            )
            if result.get("truncated"):
                logger.warning(
                    "[STT HTTP] transcript was cut short by the model | request_id={}",
                    request_id,
                )
            if text:
                lang = _frame_language(result, self._settings)
                await self._handle_transcription(text, True, lang)
                yield _make_transcript_frame(
                    text,
                    is_final=True,
                    user_id=self._user_id,
                    language=lang,
                    result=result,
                )

        except Exception as e:
            logger.error(
                "[STT HTTP] transcribe failed | request_id={} | error={}",
                request_id,
                str(e),
            )
            yield ErrorFrame(error=f"Error transcribing audio: {e}", exception=e)


# ---------------------------------------------------------------------------
# WebSocket streaming STT
# ---------------------------------------------------------------------------


@dataclass
class GnaniSTTSettings(STTSettings):
    """Settings for GnaniSTTService (WebSocket streaming).

    Parameters:
        model: STT model, sent as ``x-model``. ``None`` (default) uses the
            server's default model; ``"prisma-v3.0"`` is the multilingual model.
        language: A ``Language`` or BCP-47 code. With prisma-v3.0,
            ``"indic-auto"`` lets the model identify the language of each
            utterance; the detected language is set on each ``TranscriptionFrame``.
        sample_rate: Sample rate sent to Gnani (8000, 16000, 44100, or 48000 Hz).
            Pipeline audio is resampled to it. Defaults to the pipeline input
            rate when Gnani supports it, otherwise 16000.
        format: 'verbatim' for raw output, 'transcribe' for ITN-normalized output.
            prisma-v3.0 also takes 'codemix' and 'transliterate'.
        itn_native_numerals: When format='transcribe', render digits in native script.
        language_candidates: *prisma-v3.0 only, with language="indic-auto"*.
            2-4 languages the speaker is likely to use. A hint, not a limit.
        keywords: *prisma-v3.0 only*. Words or short phrases to favour
            (names, brands, product terms), up to 200.
    """

    sample_rate: int | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    format: str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    itn_native_numerals: bool | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)
    language_candidates: list[str | Language] | str | NotGiven | None = field(
        default_factory=lambda: NOT_GIVEN
    )
    keywords: list[str] | str | NotGiven | None = field(default_factory=lambda: NOT_GIVEN)


def _default_ws_stt_settings(
    settings_cls: type[GnaniSTTSettings],
    *,
    language: Language = Language.EN_IN,
) -> GnaniSTTSettings:
    """Build a store-mode settings object with every field explicitly set."""
    return settings_cls(
        model=None,
        language=language,
        sample_rate=None,
        format=None,
        itn_native_numerals=None,
        language_candidates=None,
        keywords=None,
    )


class GnaniSTTService(WebsocketSTTService):
    """WebSocket streaming speech-to-text service using Gnani Vachana.

    Provides real-time speech recognition for Indian languages via a
    persistent WebSocket connection to wss://api.vachana.ai/stt/v3/stream.
    Gnani detects speech segments server-side and returns one final
    transcript per segment.

    Event handlers (in addition to STTService events):

    - on_connected(service): Connected to Gnani WebSocket
    - on_disconnected(service): Disconnected from Gnani WebSocket
    - on_connection_error(service, error): Connection error occurred

    Example::

        stt = GnaniSTTService(
            api_key="your-api-key",
            settings=GnaniSTTService.Settings(
                language=Language.HI_IN,
            ),
        )

    Let prisma-v3.0 identify the language of each utterance::

        stt = GnaniSTTService(
            api_key="your-api-key",
            settings=GnaniSTTService.Settings(
                model="prisma-v3.0",
                language="indic-auto",
                language_candidates=["hi-IN", "en-IN"],  # optional hint
            ),
        )
    """

    Settings = GnaniSTTSettings
    _settings: GnaniSTTSettings

    def __init__(
        self,
        *,
        api_key: str,
        sample_rate: int | None = None,
        settings: GnaniSTTSettings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani WebSocket streaming STT service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            sample_rate: Optional input audio sample rate override. When omitted, the
                pipeline input sample rate is used.
            settings: Runtime-updatable STT settings (model, language, format, sample
                rate, ITN and prisma-v3.0 options).
            **kwargs: Additional arguments passed to the parent WebsocketSTTService,
                e.g. ``keepalive_timeout`` and ``keepalive_interval``.

        Raises:
            ValueError: If ``sample_rate`` or a setting is invalid for the chosen model.
        """
        default_settings = _default_ws_stt_settings(self.Settings)

        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(sample_rate=sample_rate, settings=default_settings, **kwargs)

        # Fail at construction rather than with an error frame at connect time.
        _build_ws_option_headers(self._settings)

        self._api_key = api_key
        self._receive_task: asyncio.Task | None = None
        self._request_id: str | None = None
        # Gnani expects fixed-size binary frames, so audio is re-framed here.
        self._audio_buffer = bytearray()
        self._send_sample_rate = _DEFAULT_STT_SAMPLE_RATE
        self._resampler = create_stream_resampler()

    def language_to_service_language(self, language: Language) -> str:
        """Convert a Language enum to a Gnani STT language code.

        Args:
            language: The Language enum value to convert.

        Returns:
            The Gnani BCP-47 language code string.
        """
        return stt_language_to_gnani(language)

    def can_generate_metrics(self) -> bool:
        """Return whether this service can emit processing metrics.

        Returns:
            True — metrics are supported for streaming transcription.
        """
        return True

    def _resolve_send_sample_rate(self) -> int:
        """Return the sample rate to send to Gnani.

        Returns:
            The configured rate, else the pipeline input rate when Gnani
            supports it, else 16000 Hz.
        """
        settings_rate = self._settings.sample_rate
        if is_given(settings_rate) and settings_rate in STT_SUPPORTED_SAMPLE_RATES:
            return settings_rate
        if self.sample_rate in STT_SUPPORTED_SAMPLE_RATES:
            return self.sample_rate
        return _DEFAULT_STT_SAMPLE_RATE

    async def _update_settings(self, delta: STTSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply settings and reconnect when connect-time parameters change.

        Args:
            delta: Settings delta from an ``STTUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If the updated settings are invalid for the chosen model;
                the previous settings are kept.
        """
        previous = copy.copy(self._settings)
        changed = await super()._update_settings(delta)
        _drop_stale_candidates(self._settings, changed)
        try:
            _build_ws_option_headers(self._settings)
        except ValueError:
            self._settings = previous
            raise

        reconnect_fields = {
            "model",
            "language",
            "format",
            "itn_native_numerals",
            "sample_rate",
            "language_candidates",
            "keywords",
        }
        if changed.keys() & reconnect_fields:
            if "sample_rate" in changed:
                self._send_sample_rate = self._resolve_send_sample_rate()
            if self._websocket is not None:
                await self._disconnect()
                await self._connect()

        unhandled = {k: v for k, v in changed.items() if k not in reconnect_fields}
        if unhandled:
            self._warn_unhandled_updated_settings(unhandled)

        return changed

    @traced_stt
    async def _handle_transcription(
        self, transcript: str, is_final: bool, language: Language | None = None
    ):
        """Record a transcription result for tracing and metrics.

        Args:
            transcript: Recognized speech text.
            is_final: Whether this is a final (vs interim) transcript.
            language: Detected or configured language, if known.
        """
        pass

    async def _push_transcript(
        self,
        text: str,
        *,
        is_final: bool,
        language: Language | None = None,
        result: Any | None = None,
    ):
        """Push a final or interim transcription frame downstream.

        Args:
            text: Recognized speech text.
            is_final: Whether this is a final transcript.
            language: Detected or configured language, if known.
            result: Raw STT payload for observability, if available.
        """
        await self._handle_transcription(text, is_final, language)
        await self.push_frame(
            _make_transcript_frame(
                text,
                is_final=is_final,
                user_id=self._user_id,
                language=language,
                result=result,
            )
        )

    async def start(self, frame: StartFrame):
        """Start the service and open the Gnani WebSocket connection.

        The pipeline sample rate is known here on every Pipecat 1.x release.

        Args:
            frame: Pipeline start frame with negotiated audio parameters.
        """
        await super().start(frame)
        self._send_sample_rate = self._resolve_send_sample_rate()
        await self._connect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:  # type: ignore[override]
        """Stream audio bytes to the Gnani WebSocket STT endpoint.

        Args:
            audio: Raw PCM audio chunk from the pipeline.

        Yields:
            ``None`` after sending audio; transcripts arrive via ``_receive_messages``.
        """
        if not self._websocket or self._websocket.state is not State.OPEN:
            yield None
            return

        try:
            await self._send_audio(audio)
        except Exception as e:
            # The receive loop reconnects a dropped connection.
            logger.warning(
                "[STT WS] send failed | request_id={} | error={}",
                self._request_id,
                str(e),
            )

        yield None

    async def _send_audio(self, audio: bytes):
        """Send audio as ``STREAM_CHUNK_BYTES`` frames, buffering any remainder."""
        if not self._websocket:
            return
        audio = await self._resampler.resample(audio, self.sample_rate, self._send_sample_rate)
        self._audio_buffer.extend(audio)
        while len(self._audio_buffer) >= STREAM_CHUNK_BYTES:
            chunk = bytes(self._audio_buffer[:STREAM_CHUNK_BYTES])
            del self._audio_buffer[:STREAM_CHUNK_BYTES]
            await self._websocket.send(chunk)

    async def _send_keepalive(self, silence: bytes):
        await self._send_audio(silence)
        # Usage metrics need Pipecat 1.14+.
        if hasattr(self, "_record_stt_audio_usage"):
            self._record_stt_audio_usage(silence)

    async def _connect(self):
        await super()._connect()
        await self._connect_websocket()
        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(
                self._receive_task_handler(self._report_error), name="gnani-stt-recv"
            )

    async def _disconnect(self):
        await super()._disconnect()
        self._audio_buffer.clear()
        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None
        await self._disconnect_websocket()

    async def _connect_websocket(self):
        if self._websocket and self._websocket.state is State.OPEN:
            return

        request_id = _generate_request_id()
        self._request_id = request_id
        logger.debug("[STT WS] connect | request_id={}", request_id)

        try:
            headers = {
                "x-api-key-id": self._api_key,
                **_build_ws_option_headers(self._settings),
                "x-sample-rate": str(self._send_sample_rate),
                "x-api-request-id": request_id,
                **sdk_headers(),
            }

            self._websocket = await ws_connect(self, GNANI_STT_WS_URL, headers)

            connected_msg = await asyncio.wait_for(self._websocket.recv(), timeout=10)
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") == "connected":
                logger.info(
                    "[STT WS] connected | request_id={} | message={}",
                    request_id,
                    connected_data.get("message", ""),
                )
            else:
                logger.warning(
                    "[STT WS] unexpected first message | request_id={} | data={}",
                    request_id,
                    connected_data,
                )

            await self._call_event_handler("on_connected")

        except Exception as e:
            logger.error(
                "[STT WS] connect failed | request_id={} | error={}",
                request_id,
                str(e),
            )
            # The socket may be open if the `connected` message was late or malformed.
            if self._websocket:
                try:
                    await self._websocket.close()
                except Exception:
                    pass
            self._websocket = None
            await self.push_error(error_msg=f"Failed to connect to Gnani STT: {e}", exception=e)
            await self._call_event_handler("on_connection_error", str(e))

    async def _disconnect_websocket(self):
        try:
            if self._websocket:
                logger.debug("[STT WS] disconnect | request_id={}", self._request_id)
                await self._websocket.close()
        except Exception as e:
            logger.warning("[STT WS] close failed | error={}", str(e))
        finally:
            self._websocket = None
            await self._call_event_handler("on_disconnected")

    async def _receive_messages(self):
        if not self._websocket:
            return

        async for msg in self._websocket:
            if isinstance(msg, bytes):
                continue

            data = json.loads(msg)
            msg_type = data.get("type", "")

            if msg_type == "transcript":
                text = data.get("text", "")
                if text:
                    logger.debug(
                        "[STT WS] transcript | request_id={} | text={}",
                        self._request_id,
                        text[:50],
                    )
                    # Each transcript is final for its speech segment; honour is_final when present.
                    is_final = data.get("is_final", True)
                    if is_final and hasattr(self, "emit_stt_usage_metrics"):
                        await self.emit_stt_usage_metrics()
                    lang = _frame_language(data, self._settings)
                    await self._push_transcript(
                        text,
                        is_final=is_final,
                        language=lang,
                        result=data,
                    )

            elif msg_type == "error":
                error_msg = data.get("message", "Unknown error")
                logger.error(
                    "[STT WS] stream error | request_id={} | error={}",
                    self._request_id,
                    error_msg,
                )
                await self.push_error(error_msg=f"Gnani STT: {error_msg}")
