"""Gnani Speech-to-Text service implementations.

Services:

- GnaniHttpSTTService — REST-based file transcription (requires VAD)
- GnaniSTTService — WebSocket streaming transcription with real-time VAD

API docs: https://docs.gnani.ai/api/STT/speech-to-text
"""

import asyncio
import io
import json
import wave
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.settings import NOT_GIVEN, STTSettings, _NotGiven, is_given
from pipecat.services.stt_service import SegmentedSTTService, STTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt

from pipecat_gnani._common import (
    GNANI_STT_REST_URL,
    GNANI_STT_WS_URL,
    STT_SUPPORTED_FORMATS,
    STT_SUPPORTED_SAMPLE_RATES,
    get_language_string,
    settings_language,
    stt_language_to_gnani,
)
from pipecat_gnani._sdk import sdk_headers

try:
    from websockets.asyncio.client import connect as websocket_connect
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Gnani STT, you need to "
        "`pip install pipecat-gnani` or `pip install websockets gnani`."
    )
    raise Exception(f"Missing module: {e}")


# Default sample rate used to wrap raw PCM when the pipeline has not negotiated
# one (e.g. the service is driven directly, outside a running pipeline).
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
        )
    return InterimTranscriptionFrame(
        text=text,
        user_id=user_id,
        timestamp=timestamp,
        language=language,
        result=result,
    )


def _pcm_to_wav(pcm: bytes, sample_rate: int, *, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw little-endian PCM samples in a WAV (RIFF) container.

    pipecat delivers VAD-segmented audio to ``run_stt`` as headerless PCM, but
    the Gnani STT REST endpoint decodes an uploaded audio *file* (via ffmpeg),
    which rejects raw PCM ("invalid start code in RIFF header"). Give the PCM a
    WAV header first. ``sample_rate`` must match the PCM's true rate or the
    transcription will be pitch-shifted.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# REST (HTTP) STT
# ---------------------------------------------------------------------------


@dataclass
class GnaniHttpSTTSettings(STTSettings):
    """Settings for GnaniHttpSTTService (REST).

    Parameters:
        format: 'verbatim' (default) or 'transcribe' (enables ITN).
        itn_native_numerals: When format='transcribe', render digits in native script.
        preferred_language: Force single-language model when multiple languages specified.
    """

    format: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    itn_native_numerals: bool | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    preferred_language: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


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
            settings: Runtime-updatable STT settings (language, format, ITN options).
            **kwargs: Additional arguments passed to the parent SegmentedSTTService.
        """
        default_settings = self.Settings(language=Language.EN_IN)

        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(settings=default_settings, **kwargs)

        self._api_key = api_key
        self._session = aiohttp_session

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
            audio: Raw PCM or WAV audio bytes from the pipeline VAD segmenter.

        Yields:
            TranscriptionFrame on success, ErrorFrame on API or network failure.
        """
        try:
            await self.start_processing_metrics()

            lang = get_language_string(self._settings, stt_language_to_gnani)

            headers = {"X-API-Key-ID": self._api_key, **sdk_headers()}

            # pipecat delivers raw PCM; the REST endpoint decodes an audio file.
            # Wrap PCM in a WAV header unless the caller already passed a WAV.
            if audio[:4] != b"RIFF":
                audio = _pcm_to_wav(audio, self.sample_rate or _DEFAULT_STT_SAMPLE_RATE)

            form = aiohttp.FormData()
            form.add_field("audio_file", audio, filename="audio.wav", content_type="audio/wav")
            form.add_field("language_code", lang or "en-IN")

            fmt = getattr(self._settings, "format", None)
            if fmt and fmt not in (NOT_GIVEN, None):
                form.add_field("format", fmt)

            preferred = getattr(self._settings, "preferred_language", None)
            if preferred and preferred not in (NOT_GIVEN, None):
                form.add_field("preferred_language", preferred)

            itn = getattr(self._settings, "itn_native_numerals", None)
            if itn and itn not in (NOT_GIVEN, None):
                form.add_field("itn_native_numerals", str(itn).lower())

            async with self._session.post(
                GNANI_STT_REST_URL, data=form, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    msg = f"Gnani STT API error: {error_text}"
                    await self.push_error(error_msg=msg)
                    yield ErrorFrame(error=msg)
                    return
                result = await response.json()

            await self.stop_processing_metrics()

            text = result.get("transcript", "").strip()
            if text:
                lang = settings_language(self._settings)
                await self._handle_transcription(text, True, lang)
                yield _make_transcript_frame(
                    text,
                    is_final=True,
                    user_id=self._user_id if hasattr(self, "_user_id") else "",
                    language=lang,
                    result=result,
                )

        except Exception as e:
            await self.push_error(error_msg=f"Error transcribing audio: {e}", exception=e)
            yield ErrorFrame(error=f"Error transcribing audio: {e}", exception=e)


# ---------------------------------------------------------------------------
# WebSocket streaming STT
# ---------------------------------------------------------------------------


@dataclass
class GnaniSTTSettings(STTSettings):
    """Settings for GnaniSTTService (WebSocket streaming).

    Parameters:
        sample_rate: Audio sample rate (8000, 16000, 44100, or 48000 Hz).
        format: 'verbatim' for raw output, 'transcribe' for ITN-normalized output.
        itn_native_numerals: When format='transcribe', render digits in native script.
    """

    sample_rate: int | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    format: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    itn_native_numerals: bool | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


class GnaniSTTService(STTService):
    """WebSocket streaming speech-to-text service using Gnani Vachana.

    Provides real-time speech recognition for Indian languages via a
    persistent WebSocket connection to wss://api.vachana.ai/stt/v3/stream.

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
    """

    Settings = GnaniSTTSettings
    _settings: GnaniSTTSettings

    def __init__(
        self,
        *,
        api_key: str,
        sample_rate: int | None = None,
        settings: GnaniSTTSettings | None = None,
        keepalive_timeout: float | None = None,
        keepalive_interval: float = 5.0,
        **kwargs,
    ):
        """Initialize the Gnani WebSocket streaming STT service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            sample_rate: Optional audio sample rate override (8000, 16000, 44100, or 48000 Hz).
                When omitted, the rate is negotiated from ``StartFrame``.
            settings: Runtime-updatable STT settings (language, format, sample rate, ITN).
            keepalive_timeout: Seconds of silence before sending keepalive audio. ``None`` disables.
            keepalive_interval: Seconds between keepalive checks when enabled.
            **kwargs: Additional arguments passed to the parent STTService.
        """
        if sample_rate is not None and sample_rate not in STT_SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"sample_rate must be one of {STT_SUPPORTED_SAMPLE_RATES}, got {sample_rate}"
            )

        default_settings = self.Settings(language=Language.EN_IN)

        if settings is not None:
            default_settings.apply_update(settings)

        if (
            hasattr(default_settings, "format")
            and default_settings.format
            and default_settings.format not in (NOT_GIVEN, None)
            and default_settings.format not in STT_SUPPORTED_FORMATS
        ):
            raise ValueError(
                f"format must be one of {STT_SUPPORTED_FORMATS}, got '{default_settings.format}'"
            )

        super().__init__(
            sample_rate=sample_rate,
            keepalive_timeout=keepalive_timeout,
            keepalive_interval=keepalive_interval,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._ws = None
        self._receive_task = None
        self._teardown_done = False

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

    def _resolve_sample_rate(self) -> int:
        """Return a supported sample rate, preferring pipeline negotiation.

        Returns:
            The resolved sample rate in Hz.
        """
        if self.sample_rate in STT_SUPPORTED_SAMPLE_RATES:
            return self.sample_rate
        if self._init_sample_rate in STT_SUPPORTED_SAMPLE_RATES:
            return self._init_sample_rate
        settings_rate = getattr(self._settings, "sample_rate", None)
        if (
            is_given(settings_rate)
            and isinstance(settings_rate, int)
            and settings_rate in STT_SUPPORTED_SAMPLE_RATES
        ):
            return settings_rate
        return _DEFAULT_STT_SAMPLE_RATE

    async def _update_settings(self, delta: STTSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply settings and reconnect when connect-time parameters change.

        Args:
            delta: Settings delta from an ``STTUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If ``format`` is not a supported value.
        """
        if isinstance(delta, self.Settings):
            fmt = getattr(delta, "format", NOT_GIVEN)
            if is_given(fmt) and fmt is not None and fmt not in STT_SUPPORTED_FORMATS:
                raise ValueError(f"format must be one of {STT_SUPPORTED_FORMATS}, got '{fmt}'")

        changed = await super()._update_settings(delta)

        reconnect_fields = {"language", "format", "itn_native_numerals", "sample_rate"}
        if changed.keys() & reconnect_fields:
            if "sample_rate" in changed:
                self._sample_rate = self._resolve_sample_rate()
            if self._ws is not None:
                await self._disconnect()
                self._teardown_done = False
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
                user_id=self._user_id if hasattr(self, "_user_id") else "",
                language=language,
                result=result,
            )
        )

    async def start(self, frame: StartFrame):
        """Start the service and open the Gnani WebSocket connection.

        Args:
            frame: Pipeline start frame with negotiated audio parameters.
        """
        await super().start(frame)
        self._sample_rate = self._resolve_sample_rate()
        self._teardown_done = False
        await self._connect()

    async def stop(self, frame: EndFrame):
        """Stop the service and tear down the WebSocket connection.

        Args:
            frame: Pipeline end frame.
        """
        await super().stop(frame)
        await self._teardown()

    async def cancel(self, frame: CancelFrame):
        """Cancel the service and tear down the WebSocket connection.

        Args:
            frame: Pipeline cancel frame.
        """
        await super().cancel(frame)
        await self._teardown()

    async def cleanup(self):
        """Release WebSocket resources regardless of prior stop/cancel."""
        await super().cleanup()
        await self._teardown()

    async def _teardown(self):
        """Close the WebSocket and cancel the receive task.

        Idempotent so it can run from ``stop()``, ``cancel()``, and
        ``cleanup()`` without duplicating teardown work.
        """
        if self._teardown_done:
            return
        self._teardown_done = True
        await self._disconnect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:  # type: ignore[override]
        """Stream audio bytes to the Gnani WebSocket STT endpoint.

        Args:
            audio: Raw PCM audio chunk from the pipeline.

        Yields:
            ``None`` after sending audio; transcripts arrive via ``_receive_messages``.
        """
        if not self._ws:
            await self._connect()
            if not self._ws:
                yield None
                return

        try:
            await self._ws.send(audio)
        except Exception as e:
            logger.warning(f"Gnani STT send failed, reconnecting: {e}")
            self._ws = None
            await self._connect()
            if self._ws:
                try:
                    await self._ws.send(audio)
                except Exception as e2:
                    await self.push_error(
                        error_msg=f"Error sending audio to Gnani: {e2}", exception=e2
                    )
                    yield ErrorFrame(error=f"Error sending audio to Gnani: {e2}", exception=e2)

        yield None

    async def _connect(self):
        logger.debug("Connecting to Gnani Vachana STT")

        try:
            lang = get_language_string(self._settings, stt_language_to_gnani)
            headers = {
                "x-api-key-id": self._api_key,
                "lang_code": lang or "en-IN",
                "x-sample-rate": str(self._resolve_sample_rate()),
                **sdk_headers(),
            }

            fmt = getattr(self._settings, "format", None)
            if fmt and fmt not in (NOT_GIVEN, None):
                headers["x-format"] = fmt

            itn = getattr(self._settings, "itn_native_numerals", None)
            if itn and itn not in (NOT_GIVEN, None):
                headers["itn_native_numerals"] = str(itn).lower()

            self._ws = await websocket_connect(
                GNANI_STT_WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )

            connected_msg = await asyncio.wait_for(self._ws.recv(), timeout=10)
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") == "connected":
                logger.info(f"Gnani STT connected: {connected_data.get('message', '')}")
            else:
                logger.warning(f"Unexpected first message from Gnani STT: {connected_data}")

            self._receive_task = asyncio.create_task(
                self._receive_messages(), name="gnani-stt-recv"
            )

            await self._call_event_handler("on_connected")

        except Exception as e:
            logger.error(f"Failed to connect to Gnani STT: {e}")
            self._ws = None
            await self.push_error(error_msg=f"Failed to connect to Gnani STT: {e}", exception=e)
            await self._call_event_handler("on_connection_error", str(e))

    async def _disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        await self._call_event_handler("on_disconnected")

    async def _receive_messages(self):
        try:
            async for msg in self._ws:
                if isinstance(msg, bytes):
                    continue

                data = json.loads(msg)
                msg_type = data.get("type", "")

                if msg_type == "transcript":
                    text = data.get("text", "")
                    if text:
                        # Gnani currently sends final transcripts only; honour is_final when present.
                        is_final = data.get("is_final", True)
                        lang = settings_language(self._settings)
                        await self._push_transcript(
                            text,
                            is_final=is_final,
                            language=lang,
                            result=data,
                        )

                elif msg_type in (
                    "processing",
                    "speech_start",
                    "vad_start",
                    "speech_end",
                    "vad_end",
                ):
                    pass

                elif msg_type == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"Gnani STT stream error: {error_msg}")
                    self._ws = None
                    await self.push_error(error_msg=f"Gnani STT: {error_msg}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Gnani STT receive error: {e}")
            self._ws = None
            await self.push_error(error_msg=f"Gnani STT receive error: {e}", exception=e)
            await self._call_event_handler("on_connection_error", str(e))
