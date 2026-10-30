"""Gnani Text-to-Speech service implementations.

Services:

- GnaniHttpTTSService — REST-based single-request synthesis
- GnaniSSETTSService — SSE streaming synthesis (lower latency)
- GnaniTTSService — WebSocket streaming synthesis with interruption handling

Models: timbre-v2.5 (default, 42 voices, default voice Pranav) and timbre-v3.0
(13 voices, default voice Avinash).
See https://docs.gnani.ai/api/TTS/tts-sse#available-voices

API docs: https://docs.gnani.ai/api/TTS/tts-inference
"""

import asyncio
import base64
import json
import struct
import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, cast

import aiohttp
from gnani.tts.client import (  # type: ignore[import-untyped]
    DEFAULT_MODEL,
    TIMBRE_MODELS,
    TV30,
    _validate_model,
    _validate_timbre_options,
    _validate_voice,
)
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.services.settings import NOT_GIVEN, TTSSettings, is_given
from pipecat.services.tts_service import InterruptibleTTSService, TTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.tracing.service_decorators import traced_tts

from pipecat_gnani._common import (
    GNANI_TTS_REST_URL,
    GNANI_TTS_SSE_URL,
    GNANI_TTS_WS_URL,
    TTS_SUPPORTED_SAMPLE_RATES,
    _NotGiven,
    tts_language_to_gnani,
)
from pipecat_gnani._sdk import _generate_request_id, sdk_headers, ws_header_kwargs

try:
    from websockets.asyncio.client import connect as websocket_connect
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Gnani TTS, you need to "
        "`pip install pipecat-gnani` or `pip install websockets gnani`."
    )
    raise Exception(f"Missing module: {e}")


_DEFAULT_TTS_SAMPLE_RATE = 16000
_WAV_HEADER_SIZE = 44

# Settings the services act on. A runtime update to any of these is re-validated;
# anything else is reported by Pipecat as "unhandled".
_TTS_HANDLED_SETTINGS = frozenset(
    {"voice", "model", "language", "speed", "encoding", "container", "sample_width", "bitrate"}
)

# Pipecat pipelines carry raw 16-bit PCM, so only PCM output is usable. Other encodings and
# containers (mp3, ogg/opus, mulaw, alaw) would be emitted as audio frames and play as noise.
_PCM_ENCODING = "linear_pcm"
_PCM_CONTAINERS = ("wav", "raw")

# Accepted for backward compatibility but ignored: output is always 16-bit PCM and ``bitrate``
# only applies to MP3, which Pipecat cannot play.
_DEPRECATED_TTS_SETTINGS = ("sample_width", "bitrate")
_warned_deprecated: set[str] = set()


def _strip_wav_header(data: bytes) -> bytes:
    """Strip a RIFF/WAV container if present, returning only PCM samples.

    Gnani streaming sends the WAV header as the first chunk (often with zero
    PCM bytes) and then raw PCM continuations without per-chunk headers. The
    SDK helper only strips when ``len(data) > 44``, so a header-only first
    chunk is emitted as audio and sounds like a click at segment start.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data

    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        if chunk_id == b"data":
            data_start = offset + 8
            return data[data_start : data_start + chunk_size]
        offset += 8 + chunk_size

    if len(data) <= _WAV_HEADER_SIZE:
        return b""
    return data[_WAV_HEADER_SIZE:]


class _Pcm16Aligner:
    """Ensure emitted PCM chunks contain whole 16-bit samples.

    Streaming TTS endpoints may chop audio at arbitrary byte boundaries, so a
    chunk can end mid-sample. Dangling bytes are held back and prepended to
    the next chunk so downstream int16 consumers (e.g. SOXR resamplers) never
    see odd-length buffers.
    """

    def __init__(self) -> None:
        self._remainder = b""

    def reset(self) -> None:
        """Discard any held-back bytes (e.g. at the start of a new utterance)."""
        self._remainder = b""

    def align(self, audio: bytes) -> bytes:
        """Return whole 16-bit samples, holding back any dangling byte."""
        audio = self._remainder + audio
        aligned_len = len(audio) - (len(audio) % 2)
        self._remainder = audio[aligned_len:]
        return audio[:aligned_len]


class _TtsPcmProcessor:
    """Strip WAV containers and align PCM for one streaming utterance.

    Gnani streaming may deliver a WAV header as the first chunk (sometimes
    with no PCM) and then raw PCM continuations. Headers can also arrive
    split across network chunks. This processor buffers partial headers,
    strips complete containers, and keeps 16-bit sample alignment.
    """

    def __init__(self) -> None:
        self._aligner = _Pcm16Aligner()
        self._wav_pending = b""

    def reset(self) -> None:
        """Reset state at the start of a new synthesis request."""
        self._aligner.reset()
        self._wav_pending = b""

    def process(self, audio: bytes) -> bytes:
        """Return aligned PCM ready to emit, or ``b\"\"`` when more data is needed."""
        if self._wav_pending or (len(audio) >= 4 and audio[:4] == b"RIFF"):
            buf = self._wav_pending + audio
            self._wav_pending = b""

            if buf[:4] == b"RIFF" and len(buf) < _WAV_HEADER_SIZE:
                self._wav_pending = buf
                return b""

            pcm = _strip_wav_header(buf)
            return self._aligner.align(pcm)

        return self._aligner.align(audio)


def _given_or_none(value):
    return value if is_given(value) else None


def _warn_deprecated_settings(settings) -> None:
    """Warn (once per setting per process) when an ignored, deprecated setting is used."""
    for name in _DEPRECATED_TTS_SETTINGS:
        if _given_or_none(getattr(settings, name, None)) is None or name in _warned_deprecated:
            continue
        _warned_deprecated.add(name)
        message = (
            f"Gnani TTS setting '{name}' is deprecated and ignored (output is always 16-bit "
            "PCM); it will be removed in a future release."
        )
        warnings.warn(message, DeprecationWarning, stacklevel=3)
        logger.warning(message)


def _validate_audio_format(settings) -> None:
    """Reject encodings/containers Pipecat cannot play (only 16-bit PCM is supported)."""
    encoding = _given_or_none(settings.encoding)
    container = _given_or_none(settings.container)
    if encoding is not None and encoding != _PCM_ENCODING:
        raise ValueError(
            f"Unsupported encoding '{encoding}': Pipecat plays raw 16-bit PCM only, "
            f"use '{_PCM_ENCODING}'."
        )
    if container is not None and container not in _PCM_CONTAINERS:
        raise ValueError(
            f"Unsupported container '{container}': use one of {', '.join(_PCM_CONTAINERS)}."
        )


def _build_audio_config(settings, sample_rate: int) -> dict:
    return {
        "sample_rate": sample_rate,
        "encoding": _PCM_ENCODING,
        "num_channels": 1,
        "sample_width": 2,
        "container": _given_or_none(settings.container) or "wav",
    }


def _validate_sample_rate(sample_rate: int | None, *, supported: tuple[int, ...]) -> None:
    if sample_rate is not None and sample_rate not in supported:
        raise ValueError(f"sample_rate must be one of {supported}, got {sample_rate}")


def _negotiate_tts_sample_rate(service: TTSService) -> int:
    """Resolve the output rate at start-up, warning when the pipeline rate is unsupported."""
    resolved = _resolved_tts_sample_rate(service)
    if service.sample_rate != resolved:
        logger.warning(
            "Gnani TTS does not support a {} Hz pipeline rate (supported: {}); "
            "synthesizing at {} Hz instead.",
            service.sample_rate,
            TTS_SUPPORTED_SAMPLE_RATES,
            resolved,
        )
    return resolved


def _resolved_tts_sample_rate(service: TTSService) -> int:
    rate = service.sample_rate
    if rate in TTS_SUPPORTED_SAMPLE_RATES:
        return rate
    init_rate = service._init_sample_rate
    if init_rate in TTS_SUPPORTED_SAMPLE_RATES:
        return init_rate
    return _DEFAULT_TTS_SAMPLE_RATE


def _optional_tts_language_code(settings) -> str | None:
    lang = settings.language
    if lang is None or lang is NOT_GIVEN:
        return None
    if isinstance(lang, Language):
        return tts_language_to_gnani(lang)
    return str(lang) if lang else None


def _settings_voice(settings) -> str | None:
    voice = settings.voice
    if not is_given(voice) or voice is None:
        return None
    return str(voice)


def _settings_model(settings) -> str:
    model = settings.model
    if not is_given(model) or model is None:
        return cast("str", DEFAULT_MODEL)
    return cast("str", model)


def _default_voice(model: str) -> str:
    return "Avinash" if model == TV30 else "Pranav"


def _settings_speed(settings) -> float | None:
    speed = _given_or_none(getattr(settings, "speed", None))
    return None if speed is None else float(speed)


def _validate_tts_settings(settings) -> None:
    """Validate model, voice, language, speed and audio format using the SDK's rules."""
    model = _settings_model(settings)
    _validate_model(model)
    _validate_timbre_options(
        model,
        language=_optional_tts_language_code(settings),
        speed=_settings_speed(settings),
    )
    voice = _settings_voice(settings)
    if voice is not None:
        _validate_voice(voice, model)
    _validate_audio_format(settings)
    _warn_deprecated_settings(settings)


def _build_tts_payload(text: str, settings, sample_rate: int) -> dict:
    model = _settings_model(settings)
    _validate_tts_settings(settings)
    payload = {
        "text": text,
        "voice": _settings_voice(settings) or _default_voice(model),
        "model": model,
        "audio_config": _build_audio_config(settings, sample_rate),
    }
    language = _optional_tts_language_code(settings)
    if model in TIMBRE_MODELS and language is not None:
        payload["language"] = language
    speed = _settings_speed(settings)
    if speed is not None:
        payload["speed"] = speed
    return payload


def _apply_tts_settings_update(service, changed: dict[str, Any]) -> None:
    """Validate a runtime settings update, rolling it back if it is invalid.

    The timbre-v2.5 and timbre-v3.0 voice sets do not overlap, so a model change
    that names no voice keeps the current voice only if the new model has it,
    and otherwise switches to the new model's default voice.

    Raises:
        ValueError: If the updated settings are invalid. The previous settings
            are restored first, so later requests keep working.
    """
    settings = service._settings
    previous_voice = settings.voice
    model = _settings_model(settings)
    if "model" in changed and "voice" not in changed:
        try:
            _validate_voice(_settings_voice(settings), model)
        except ValueError:
            settings.voice = _default_voice(model)

    try:
        _validate_tts_settings(settings)
    except ValueError:
        settings.voice = previous_voice
        for key, old_value in changed.items():
            setattr(settings, key, old_value)
        raise


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass
class GnaniHttpTTSSettings(TTSSettings):
    """Settings for GnaniHttpTTSService and GnaniSSETTSService.

    Inherited ``voice``, ``model`` and ``language`` apply as usual. ``language`` is a
    BCP-47 code (``hi-IN``), a Pipecat ``Language``, or ``"auto"``; it works with both
    ``timbre-v2.5`` and ``timbre-v3.0``.

    Parameters:
        speed: Speaking rate, 0.85 to 1.15 (1.0 is normal). Server default when unset.
        encoding: Audio encoding. Only ``linear_pcm`` (the default) is supported.
        container: ``wav`` (default) or ``raw``. The plugin strips it before emitting audio.
        sample_width: Deprecated and ignored (output is always 16-bit PCM).
        bitrate: Deprecated and ignored (it only applies to MP3, which Pipecat cannot play).
    """

    speed: float | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    encoding: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    container: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    sample_width: int | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    bitrate: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


@dataclass
class GnaniSSETTSSettings(GnaniHttpTTSSettings):
    """Settings for GnaniSSETTSService (SSE streaming).

    Inherits all parameters from :class:`GnaniHttpTTSSettings`.
    """

    pass


@dataclass
class GnaniTTSSettings(GnaniHttpTTSSettings):
    """Settings for GnaniTTSService (WebSocket streaming).

    Inherits all parameters from :class:`GnaniHttpTTSSettings`.
    """

    pass


def _default_tts_settings(
    settings_cls: type[GnaniHttpTTSSettings],
    *,
    model: str,
    voice: str | None,
) -> GnaniHttpTTSSettings:
    """Build a store-mode settings object with every field explicitly set."""
    return settings_cls(
        model=model,
        voice=voice,
        speed=None,
        encoding="linear_pcm",
        container="wav",
        sample_width=None,
        bitrate=None,
        language=None,
    )


# ---------------------------------------------------------------------------
# REST TTS
# ---------------------------------------------------------------------------


class GnaniHttpTTSService(TTSService):
    """REST-based text-to-speech service using Gnani Vachana API.

    Returns complete audio in a single response. Suitable for non-streaming
    use cases where latency is less critical.

    Example::

        tts = GnaniHttpTTSService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniHttpTTSService.Settings(
                voice="Pranav",
            ),
        )
    """

    Settings = GnaniHttpTTSSettings
    _settings: GnaniHttpTTSSettings

    def __init__(
        self,
        *,
        api_key: str,
        aiohttp_session: aiohttp.ClientSession,
        voice_id: str | None = None,
        model: str = DEFAULT_MODEL,
        sample_rate: int | None = None,
        settings: GnaniHttpTTSSettings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani REST TTS service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            aiohttp_session: Shared aiohttp session for HTTP requests.
            voice_id: Default voice name. Defaults to Pranav for timbre-v2.5
                and Avinash for timbre-v3.0.
            model: TTS model identifier.
            sample_rate: Optional output sample rate override. When omitted, negotiated from
                ``StartFrame``.
            settings: Runtime-updatable TTS settings (voice, model, audio format).
            **kwargs: Additional arguments passed to the parent TTSService.
        """
        _validate_sample_rate(sample_rate, supported=TTS_SUPPORTED_SAMPLE_RATES)

        default_settings = _default_tts_settings(
            self.Settings,
            model=model,
            voice=voice_id,
        )
        if settings is not None:
            default_settings.apply_update(settings)
        if _settings_voice(default_settings) is None:
            default_settings.voice = _default_voice(_settings_model(default_settings))

        _validate_tts_settings(default_settings)

        super().__init__(
            sample_rate=sample_rate,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._session = aiohttp_session
        self._pcm_processor = _TtsPcmProcessor()

    async def start(self, frame: StartFrame):
        """Start the service and resolve the output sample rate.

        Args:
            frame: Pipeline start frame with negotiated audio parameters.
        """
        await super().start(frame)
        self._sample_rate = _negotiate_tts_sample_rate(self)

    def can_generate_metrics(self) -> bool:
        """Return whether this service can emit TTS metrics.

        Returns:
            True — metrics are supported for REST synthesis.
        """
        return True

    async def _update_settings(self, delta: TTSSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply runtime TTS settings for the next synthesis request.

        Args:
            delta: Settings delta from a ``TTSUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If ``voice`` is not a supported Gnani voice for ``model``.
                The update is not applied.
        """
        changed = await super()._update_settings(delta)

        if _TTS_HANDLED_SETTINGS & changed.keys():
            _apply_tts_settings_update(self, changed)

        unhandled = {k: v for k, v in changed.items() if k not in _TTS_HANDLED_SETTINGS}
        if unhandled:
            self._warn_unhandled_updated_settings(unhandled)

        return changed

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Synthesize speech via the Gnani REST TTS API.

        Args:
            text: Text to synthesize.
            context_id: Pipeline context identifier for this utterance.

        Yields:
            TTSAudioRawFrame on success. ``TTSTextFrame`` is emitted by the base class
            after synthesis completes. ErrorFrame on failure.
        """
        request_id = _generate_request_id()
        logger.debug(
            "[TTS HTTP] synthesize start | request_id={} | text_length={}",
            request_id,
            len(text),
        )

        try:
            self._pcm_processor.reset()
            rate = _resolved_tts_sample_rate(self)
            payload = _build_tts_payload(text, self._settings, rate)
            headers = {
                "X-API-Key-ID": self._api_key,
                "Content-Type": "application/json",
                **sdk_headers(request_id=request_id),
            }

            async with self._session.post(
                GNANI_TTS_REST_URL, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    msg = f"Gnani TTS API error: {error_text}"
                    logger.error(
                        "[TTS HTTP] synthesize failed | request_id={} | error={}",
                        request_id,
                        msg,
                    )
                    await self.push_error(error_msg=msg)
                    yield ErrorFrame(error=msg)
                    return
                audio_data = await response.read()

            await self.start_tts_usage_metrics(text)
            audio_data = self._pcm_processor.process(audio_data)

            if audio_data:
                logger.debug(
                    "[TTS HTTP] synthesize complete | request_id={} | audio_length={}",
                    request_id,
                    len(audio_data),
                )
                yield TTSAudioRawFrame(
                    audio=audio_data,
                    sample_rate=rate,
                    num_channels=1,
                    context_id=context_id,
                )

        except Exception as e:
            logger.error(
                "[TTS HTTP] synthesize failed | request_id={} | error={}",
                request_id,
                str(e),
            )
            await self.push_error(error_msg=f"Error generating TTS: {e}", exception=e)
            yield ErrorFrame(error=f"Error generating TTS: {e}", exception=e)
        finally:
            await self.stop_ttfb_metrics()


# ---------------------------------------------------------------------------
# SSE Streaming TTS
# ---------------------------------------------------------------------------


class GnaniSSETTSService(TTSService):
    """SSE streaming text-to-speech using Gnani Vachana API.

    Streams audio chunks via Server-Sent Events as they are generated.
    Lower latency than the REST service — playback can start before the
    full response is ready.

    Example::

        tts = GnaniSSETTSService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniSSETTSService.Settings(
                voice="Pranav",
            ),
        )
    """

    Settings = GnaniSSETTSSettings
    _settings: GnaniSSETTSSettings

    def __init__(
        self,
        *,
        api_key: str,
        aiohttp_session: aiohttp.ClientSession,
        voice_id: str | None = None,
        model: str = DEFAULT_MODEL,
        sample_rate: int | None = None,
        settings: GnaniSSETTSSettings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani SSE streaming TTS service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            aiohttp_session: Shared aiohttp session for HTTP requests.
            voice_id: Default voice name. Defaults to Pranav for timbre-v2.5
                and Avinash for timbre-v3.0.
            model: TTS model identifier.
            sample_rate: Optional output sample rate override. When omitted, negotiated from
                ``StartFrame``.
            settings: Runtime-updatable TTS settings (voice, model, audio format).
            **kwargs: Additional arguments passed to the parent TTSService.
        """
        _validate_sample_rate(sample_rate, supported=TTS_SUPPORTED_SAMPLE_RATES)

        default_settings = _default_tts_settings(
            self.Settings,
            model=model,
            voice=voice_id,
        )
        if settings is not None:
            default_settings.apply_update(settings)
        if _settings_voice(default_settings) is None:
            default_settings.voice = _default_voice(_settings_model(default_settings))

        _validate_tts_settings(default_settings)

        super().__init__(
            sample_rate=sample_rate,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._session = aiohttp_session
        self._pcm_processor = _TtsPcmProcessor()

    async def start(self, frame: StartFrame):
        """Start the service and resolve the output sample rate.

        Args:
            frame: Pipeline start frame with negotiated audio parameters.
        """
        await super().start(frame)
        self._sample_rate = _negotiate_tts_sample_rate(self)

    def can_generate_metrics(self) -> bool:
        """Return whether this service can emit TTS metrics.

        Returns:
            True — metrics are supported for SSE streaming synthesis.
        """
        return True

    async def _update_settings(self, delta: TTSSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply runtime TTS settings for the next synthesis request.

        Args:
            delta: Settings delta from a ``TTSUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If ``voice`` is not a supported Gnani voice for ``model``.
                The update is not applied.
        """
        changed = await super()._update_settings(delta)

        if _TTS_HANDLED_SETTINGS & changed.keys():
            _apply_tts_settings_update(self, changed)

        unhandled = {k: v for k, v in changed.items() if k not in _TTS_HANDLED_SETTINGS}
        if unhandled:
            self._warn_unhandled_updated_settings(unhandled)

        return changed

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Stream synthesized speech via the Gnani SSE TTS API.

        Args:
            text: Text to synthesize.
            context_id: Pipeline context identifier for this utterance.

        Yields:
            TTSAudioRawFrame chunks as they arrive. ``TTSTextFrame`` is emitted by the base
            class after streaming completes. ErrorFrame on failure.
        """
        request_id = _generate_request_id()
        logger.debug("[TTS SSE] synthesize start | request_id={}", request_id)

        try:
            self._pcm_processor.reset()
            rate = _resolved_tts_sample_rate(self)
            payload = _build_tts_payload(text, self._settings, rate)
            headers = {
                "X-API-Key-ID": self._api_key,
                "Content-Type": "application/json",
                **sdk_headers(request_id=request_id),
            }

            async with self._session.post(
                GNANI_TTS_SSE_URL, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    msg = f"Gnani TTS SSE error: {error_text}"
                    logger.error(
                        "[TTS SSE] synthesize failed | request_id={} | error={}",
                        request_id,
                        msg,
                    )
                    await self.push_error(error_msg=msg)
                    yield ErrorFrame(error=msg)
                    return

                await self.start_tts_usage_metrics(text)

                current_event = ""
                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    if line.startswith("event:"):
                        current_event = line[len("event:") :].strip()
                        continue

                    if line.startswith("data:"):
                        data_str = line[len("data:") :].strip()
                    else:
                        continue

                    if current_event == "audio_chunk":
                        if not data_str:
                            continue
                        try:
                            audio_bytes = self._pcm_processor.process(base64.b64decode(data_str))
                        except Exception:
                            continue
                        if audio_bytes:
                            await self.stop_ttfb_metrics()
                            yield TTSAudioRawFrame(
                                audio=audio_bytes,
                                sample_rate=rate,
                                num_channels=1,
                                context_id=context_id,
                            )

                    elif current_event == "completed":
                        logger.debug(
                            "[TTS SSE] synthesize complete | request_id={}",
                            request_id,
                        )
                        return

                    elif current_event == "error":
                        try:
                            err_data = json.loads(data_str)
                            msg = err_data.get("message", data_str)
                        except (json.JSONDecodeError, ValueError):
                            msg = data_str
                        logger.error(
                            "[TTS SSE] synthesize failed | request_id={} | error={}",
                            request_id,
                            msg,
                        )
                        yield ErrorFrame(error=f"Gnani TTS SSE: {msg}")
                        return

                    else:
                        try:
                            data = json.loads(data_str)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if data.get("status") == "error":
                            yield ErrorFrame(error=f"Gnani TTS SSE: {data.get('message', '')}")
                            return
                        audio_b64 = data.get("audio", "")
                        if audio_b64:
                            audio_bytes = self._pcm_processor.process(base64.b64decode(audio_b64))
                            if audio_bytes:
                                await self.stop_ttfb_metrics()
                                yield TTSAudioRawFrame(
                                    audio=audio_bytes,
                                    sample_rate=rate,
                                    num_channels=1,
                                    context_id=context_id,
                                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                "[TTS SSE] synthesize failed | request_id={} | error={}",
                request_id,
                str(e),
            )
            await self.push_error(error_msg=f"Error in SSE TTS: {e}", exception=e)
            yield ErrorFrame(error=f"Error in SSE TTS: {e}", exception=e)
        finally:
            await self.stop_ttfb_metrics()


# ---------------------------------------------------------------------------
# WebSocket Streaming TTS
# ---------------------------------------------------------------------------


class GnaniTTSService(InterruptibleTTSService):
    """WebSocket streaming text-to-speech using Gnani Vachana.

    Lowest latency option with real-time audio generation and interruption
    handling via a persistent WebSocket connection to
    wss://api.vachana.ai/api/v1/tts.

    Example::

        tts = GnaniTTSService(
            api_key="your-api-key",
            settings=GnaniTTSService.Settings(
                voice="Pranav",
            ),
        )
    """

    Settings = GnaniTTSSettings
    _settings: GnaniTTSSettings

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str | None = None,
        model: str = DEFAULT_MODEL,
        sample_rate: int | None = None,
        settings: GnaniTTSSettings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani WebSocket streaming TTS service.

        Args:
            api_key: Gnani Vachana API key for authentication.
            voice_id: Default voice name. Defaults to Pranav for timbre-v2.5
                and Avinash for timbre-v3.0.
            model: TTS model identifier.
            sample_rate: Optional output sample rate override. When omitted, negotiated from
                ``StartFrame``.
            settings: Runtime-updatable TTS settings (voice, model, audio format).
            **kwargs: Additional arguments passed to the parent InterruptibleTTSService.
        """
        _validate_sample_rate(sample_rate, supported=TTS_SUPPORTED_SAMPLE_RATES)

        default_settings = _default_tts_settings(
            self.Settings,
            model=model,
            voice=voice_id,
        )
        if settings is not None:
            default_settings.apply_update(settings)
        if _settings_voice(default_settings) is None:
            default_settings.voice = _default_voice(_settings_model(default_settings))

        _validate_tts_settings(default_settings)

        super().__init__(
            sample_rate=sample_rate,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._ws = None
        self._receive_task = None
        self._awaiting_first_chunk = False
        self._teardown_done = False
        self._pcm_processor = _TtsPcmProcessor()
        self._request_id: str | None = None

    def can_generate_metrics(self) -> bool:
        """Return whether this service can emit TTS metrics.

        Returns:
            True — metrics are supported for WebSocket streaming synthesis.
        """
        return True

    async def _update_settings(self, delta: TTSSettings) -> dict[str, Any]:  # type: ignore[override]
        """Apply runtime TTS settings for the next synthesis request.

        Voice, model, and audio-format settings take effect on the next ``run_tts`` call
        without reconnecting the WebSocket.

        Args:
            delta: Settings delta from a ``TTSUpdateSettingsFrame``.

        Returns:
            Dict mapping changed field names to their previous values.

        Raises:
            ValueError: If ``voice`` is not a supported Gnani voice for ``model``.
                The update is not applied.
        """
        changed = await super()._update_settings(delta)

        if _TTS_HANDLED_SETTINGS & changed.keys():
            _apply_tts_settings_update(self, changed)

        unhandled = {k: v for k, v in changed.items() if k not in _TTS_HANDLED_SETTINGS}
        if unhandled:
            self._warn_unhandled_updated_settings(unhandled)

        return changed

    async def start(self, frame: StartFrame):
        """Start the service and open the Gnani WebSocket connection.

        Args:
            frame: Pipeline start frame with negotiated audio parameters.
        """
        await super().start(frame)
        self._sample_rate = _negotiate_tts_sample_rate(self)
        self._teardown_done = False
        await self._connect_websocket()

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
        await self._disconnect_websocket()

    async def _connect(self):
        """Open the WebSocket.

        ``InterruptibleTTSService`` calls ``_disconnect()`` then ``_connect()`` when
        the user interrupts the bot, so the server stops streaming the interrupted
        reply. The base implementations only toggle a flag, so the socket has to
        be opened and closed here.
        """
        await super()._connect()
        await self._connect_websocket()

    async def _disconnect(self):
        """Close the WebSocket and cancel the receive task."""
        await super()._disconnect()
        await self._disconnect_websocket()

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Send a synthesis request over the Gnani WebSocket TTS connection.

        Args:
            text: Text to synthesize.
            context_id: Pipeline context identifier for this utterance.

        Yields:
            ``None`` after sending the request; audio arrives via ``_receive_messages``.
            ``TTSTextFrame`` is emitted by the base class after synthesis completes.
        """
        request_id = _generate_request_id()
        self._request_id = request_id
        logger.debug("[TTS WS] synthesize start | request_id={}", request_id)

        if not self._ws:
            await self._connect_websocket()

        if not self._ws:
            logger.error(
                "[TTS WS] synthesize failed | request_id={} | error=not connected",
                request_id,
            )
            await self.push_error(error_msg="Gnani TTS WebSocket not connected")
            yield ErrorFrame(error="Gnani TTS WebSocket not connected")
            return

        try:
            rate = _resolved_tts_sample_rate(self)
            request_body = _build_tts_payload(text, self._settings, rate)

            self._awaiting_first_chunk = True
            self._pcm_processor.reset()
            await self._ws.send(json.dumps(request_body))
            await self.start_tts_usage_metrics(text)

        except Exception as e:
            logger.error(
                "[TTS WS] synthesize failed | request_id={} | error={}",
                request_id,
                str(e),
            )
            await self.push_error(error_msg=f"Error sending TTS request: {e}", exception=e)
            yield ErrorFrame(error=f"Error sending TTS request: {e}", exception=e)

        yield None

    async def _connect_websocket(self):
        try:
            if self._ws:
                return

            request_id = _generate_request_id()
            logger.debug("[TTS WS] connect | request_id={}", request_id)
            headers = {
                "Content-Type": "application/json",
                "X-API-Key-ID": self._api_key,
                "X-API-Request-ID": request_id,
                **sdk_headers(),
            }

            self._ws = await websocket_connect(
                GNANI_TTS_WS_URL,
                **ws_header_kwargs(headers),
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )

            self._receive_task = asyncio.create_task(
                self._receive_messages(), name="gnani-tts-recv"
            )

            await self._call_event_handler("on_connected")

        except Exception as e:
            logger.error("[TTS WS] connect failed | error={}", str(e))
            self._ws = None
            await self.push_error(error_msg=f"Failed to connect to Gnani TTS: {e}", exception=e)
            await self._call_event_handler("on_connection_error", f"{e}")

    async def _disconnect_websocket(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws:
            try:
                logger.debug("[TTS WS] disconnect")
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _receive_messages(self):
        ws = self._ws
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    await self._handle_audio_chunk(msg)
                    continue

                data = json.loads(msg)
                msg_type = data.get("type", "")

                # The server nests the base64 audio under "data": {"audio": ...};
                # fall back to a top-level "audio" for forward compatibility.
                def _audio_b64(payload: dict) -> str:
                    nested = payload.get("data")
                    if isinstance(nested, dict) and nested.get("audio"):
                        return cast("str", nested["audio"])
                    return cast("str", payload.get("audio", ""))

                if msg_type == "audio":
                    audio_b64 = _audio_b64(data)
                    if audio_b64:
                        await self._handle_audio_chunk(base64.b64decode(audio_b64))

                elif msg_type == "complete":
                    audio_b64 = _audio_b64(data)
                    if audio_b64:
                        await self._handle_audio_chunk(base64.b64decode(audio_b64))
                    logger.debug(
                        "[TTS WS] synthesize complete | request_id={}",
                        self._request_id,
                    )
                    await self._finish_audio_context()

                elif msg_type == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(
                        "[TTS WS] stream error | request_id={} | error={}",
                        self._request_id,
                        error_msg,
                    )
                    await self.push_error(error_msg=f"Gnani TTS: {error_msg}")
                    await self._finish_audio_context()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                "[TTS WS] receive error | request_id={} | error={}",
                self._request_id,
                str(e),
            )
            await self.push_error(error_msg=f"Gnani TTS receive error: {e}", exception=e)
            await self._call_event_handler("on_connection_error", f"{e}")

        # The socket ended on its own (server close, idle timeout, network drop).
        # Forget it so the next run_tts() reconnects instead of sending into it.
        if self._ws is ws:
            self._ws = None
            await ws.close()

    async def _handle_audio_chunk(self, audio_bytes: bytes):
        audio_bytes = self._pcm_processor.process(audio_bytes)
        if audio_bytes:
            if self._awaiting_first_chunk:
                self._awaiting_first_chunk = False
                await self.stop_ttfb_metrics()
            # Audio must go through the active audio context, tagged with its id. Pushing
            # it straight downstream bypasses the context, so Pipecat (>= 1.15) reports
            # "completed with no audio" for every utterance.
            context_id = self.get_active_audio_context_id()
            await self.append_to_audio_context(
                context_id,
                TTSAudioRawFrame(
                    audio=audio_bytes,
                    sample_rate=_resolved_tts_sample_rate(self),
                    num_channels=1,
                    context_id=context_id,
                ),
            )

    async def _finish_audio_context(self):
        """Close the active audio context: emit its stop frame in order, then retire it."""
        context_id = self.get_active_audio_context_id()
        if context_id and self.audio_context_available(context_id):
            await self.append_to_audio_context(context_id, TTSStoppedFrame(context_id=context_id))
            await self.remove_audio_context(context_id)
