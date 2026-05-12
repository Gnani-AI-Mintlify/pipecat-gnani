"""Gnani Vachana text-to-speech service implementation.

This module provides TTS services using Gnani Vachana's API with support for
Indian languages and multiple voices.

**Voices:** sia (default), raju, kanika, nikita, ravan, simran, karan, neha

**Transport options:**
- GnaniHttpTTSService: REST-based single-request synthesis
- GnaniTTSService: WebSocket-based streaming synthesis with interruption handling
"""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import aiohttp
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
from pipecat.services.settings import NOT_GIVEN, TTSSettings, _NotGiven, is_given
from pipecat.services.tts_service import InterruptibleTTSService, TTSService
from pipecat.transcriptions.language import Language, resolve_language
from pipecat.utils.tracing.service_decorators import traced_tts

from pipecat_gnani._sdk import sdk_headers

try:
    from websockets.asyncio.client import connect as websocket_connect
    from websockets.protocol import State
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Gnani Vachana TTS, you need to "
        "`pip install pipecat-gnani` or `pip install websockets gnani-vachana`."
    )
    raise Exception(f"Missing module: {e}")


GNANI_TTS_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"
GNANI_TTS_WS_URL = "wss://api.vachana.ai/api/v1/tts"

SUPPORTED_VOICES = frozenset({
    "sia", "raju", "kanika", "nikita", "ravan", "simran", "karan", "neha",
})


def language_to_gnani_language(language: Language) -> str | None:
    """Convert Pipecat Language enum to Gnani Vachana language codes."""
    LANGUAGE_MAP = {
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
        Language.PA: "pa-IN",
        Language.PA_IN: "pa-IN",
        Language.TA: "ta-IN",
        Language.TA_IN: "ta-IN",
        Language.TE: "te-IN",
        Language.TE_IN: "te-IN",
    }
    return resolve_language(language, LANGUAGE_MAP, use_base_code=False)


@dataclass
class GnaniHttpTTSSettings(TTSSettings):
    """Settings for GnaniHttpTTSService.

    Parameters:
        encoding: Audio encoding (linear_pcm or oggopus).
        container: Audio container (raw, mp3, wav, mulaw, ogg).
        sample_width: Sample width in bytes (1-4). Defaults to 2.
    """

    encoding: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    container: str | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)
    sample_width: int | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


@dataclass
class GnaniTTSSettings(GnaniHttpTTSSettings):
    """Settings for GnaniTTSService (WebSocket).

    Extends GnaniHttpTTSSettings for WebSocket streaming.
    """

    pass


class GnaniHttpTTSService(TTSService):
    """REST-based text-to-speech service using Gnani Vachana API.

    Converts text to speech using Gnani Vachana's REST endpoint. Suitable for
    non-streaming use cases where latency is less critical.

    Example::

        tts = GnaniHttpTTSService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniHttpTTSService.Settings(
                voice="sia",
                language=Language.HI,
            ),
        )
    """

    Settings = GnaniHttpTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        aiohttp_session: aiohttp.ClientSession,
        voice_id: str | None = None,
        model: str = "vachana-voice-v2",
        sample_rate: int | None = None,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani Vachana HTTP TTS service.

        Args:
            api_key: Gnani API key for authentication.
            aiohttp_session: Shared aiohttp session for making requests.
            voice_id: Speaker voice ID. Defaults to "sia".
            model: TTS model to use. Defaults to "vachana-voice-v2".
            sample_rate: Audio sample rate in Hz. Defaults to 24000.
            settings: Runtime-updatable settings.
            **kwargs: Additional arguments passed to parent TTSService.
        """
        default_settings = self.Settings(
            model=model,
            voice=voice_id or "sia",
            language="en-IN",
            encoding="linear_pcm",
            container="wav",
            sample_width=2,
        )

        if settings is not None:
            default_settings.apply_update(settings)

        if default_settings.voice and default_settings.voice not in SUPPORTED_VOICES:
            raise ValueError(
                f"Voice '{default_settings.voice}' not supported. "
                f"Choose from: {sorted(SUPPORTED_VOICES)}"
            )

        super().__init__(
            sample_rate=sample_rate or 24000,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._session = aiohttp_session

    def can_generate_metrics(self) -> bool:
        return True

    def language_to_service_language(self, language: Language) -> str | None:
        return language_to_gnani_language(language)

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"{self}: Generating TTS [{text}]")

        try:
            payload = {
                "text": text,
                "voice": self._settings.voice or "sia",
                "model": self._settings.model or "vachana-voice-v2",
                "audio_config": {
                    "sample_rate": self.sample_rate,
                    "encoding": self._settings.encoding or "linear_pcm",
                    "num_channels": 1,
                    "sample_width": self._settings.sample_width or 2,
                    "container": self._settings.container or "wav",
                },
            }

            headers = {
                "X-API-Key-ID": self._api_key,
                "Content-Type": "application/json",
                **sdk_headers(),
            }

            async with self._session.post(
                GNANI_TTS_REST_URL, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield ErrorFrame(error=f"Gnani TTS API error: {error_text}")
                    return

                audio_data = await response.read()

            await self.start_tts_usage_metrics(text)

            if len(audio_data) > 44 and audio_data.startswith(b"RIFF"):
                audio_data = audio_data[44:]

            yield TTSAudioRawFrame(
                audio=audio_data,
                sample_rate=self.sample_rate,
                num_channels=1,
                context_id=context_id,
            )

        except Exception as e:
            yield ErrorFrame(error=f"Error generating TTS: {e}", exception=e)
        finally:
            await self.stop_ttfb_metrics()


class GnaniTTSService(InterruptibleTTSService):
    """WebSocket-based text-to-speech service using Gnani Vachana.

    Provides streaming TTS with real-time audio generation and interruption
    handling via WebSocket.

    Example::

        tts = GnaniTTSService(
            api_key="your-api-key",
            settings=GnaniTTSService.Settings(
                voice="sia",
                language=Language.HI,
            ),
        )
    """

    Settings = GnaniTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str | None = None,
        model: str = "vachana-voice-v2",
        sample_rate: int | None = None,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the Gnani Vachana WebSocket TTS service.

        Args:
            api_key: Gnani API key for authentication.
            voice_id: Speaker voice ID. Defaults to "sia".
            model: TTS model to use. Defaults to "vachana-voice-v2".
            sample_rate: Audio sample rate in Hz. Defaults to 24000.
            settings: Runtime-updatable settings.
            **kwargs: Additional arguments passed to parent.
        """
        default_settings = self.Settings(
            model=model,
            voice=voice_id or "sia",
            language="IND-IN",
            encoding="linear_pcm",
            container="wav",
            sample_width=2,
        )

        if settings is not None:
            default_settings.apply_update(settings)

        if default_settings.voice and default_settings.voice not in SUPPORTED_VOICES:
            raise ValueError(
                f"Voice '{default_settings.voice}' not supported. "
                f"Choose from: {sorted(SUPPORTED_VOICES)}"
            )

        super().__init__(
            sample_rate=sample_rate or 24000,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._ws = None
        self._receive_task = None
        self._bot_speaking = False

    def can_generate_metrics(self) -> bool:
        return True

    def language_to_service_language(self, language: Language) -> str | None:
        return language_to_gnani_language(language)

    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._disconnect()

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"{self}: Streaming TTS [{text}]")

        if not self._ws:
            await self._connect()

        if not self._ws:
            yield ErrorFrame(error="Gnani TTS WebSocket not connected")
            return

        try:
            request_body = {
                "text": text,
                "voice": self._settings.voice or "sia",
                "model": self._settings.model or "vachana-voice-v2",
                "language": self._settings.language or "IND-IN",
                "audio_config": {
                    "sample_rate": self.sample_rate,
                    "encoding": self._settings.encoding or "linear_pcm",
                    "num_channels": 1,
                    "sample_width": self._settings.sample_width or 2,
                    "container": self._settings.container or "wav",
                },
            }

            self._bot_speaking = True
            await self._ws.send(json.dumps(request_body))

            await self.start_tts_usage_metrics(text)

        except Exception as e:
            yield ErrorFrame(error=f"Error sending TTS request: {e}", exception=e)
        finally:
            await self.stop_ttfb_metrics()

        yield None

    async def _connect(self):
        logger.debug("Connecting to Gnani Vachana TTS WebSocket")

        try:
            headers = {
                "Content-Type": "application/json",
                "X-API-Key-ID": self._api_key,
                **sdk_headers(),
            }

            self._ws = await websocket_connect(
                GNANI_TTS_WS_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )

            self._receive_task = asyncio.create_task(
                self._receive_messages(), name="gnani-tts-recv"
            )

            await self._call_event_handler("on_connected")

        except Exception as e:
            logger.error(f"Failed to connect to Gnani TTS: {e}")
            self._ws = None
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
                    await self._handle_audio_chunk(msg)
                    continue

                data = json.loads(msg)
                msg_type = data.get("type", "")

                if msg_type == "audio":
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        await self._handle_audio_chunk(audio_bytes)

                elif msg_type == "complete":
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        await self._handle_audio_chunk(audio_bytes)
                    self._bot_speaking = False
                    await self.push_frame(TTSStoppedFrame())

                elif msg_type == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"Gnani TTS stream error: {error_msg}")
                    self._bot_speaking = False
                    await self.push_frame(ErrorFrame(error=f"Gnani TTS: {error_msg}"))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Gnani TTS receive error: {e}")
            self._bot_speaking = False
            await self._call_event_handler("on_connection_error", str(e))

    async def _handle_audio_chunk(self, audio_bytes: bytes):
        if len(audio_bytes) > 44 and audio_bytes.startswith(b"RIFF"):
            audio_bytes = audio_bytes[44:]

        if audio_bytes:
            await self.push_frame(
                TTSAudioRawFrame(
                    audio=audio_bytes,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                )
            )
