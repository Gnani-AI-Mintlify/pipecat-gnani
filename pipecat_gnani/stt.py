"""Gnani Vachana Speech-to-Text service implementation.

This module provides a streaming STT service using Gnani Vachana's WebSocket API.
It supports real-time transcription with VAD for Indian language speech recognition.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from loguru import logger

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.settings import NOT_GIVEN, STTSettings, _NotGiven, is_given
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language, resolve_language
from pipecat.utils.time import time_now_iso8601
from pipecat_gnani._sdk import sdk_headers

try:
    import websockets
    from websockets.asyncio.client import connect as websocket_connect
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Gnani Vachana STT, you need to "
        "`pip install pipecat-gnani` or `pip install websockets gnani-vachana`."
    )
    raise Exception(f"Missing module: {e}")


GNANI_STT_WS_URL = "wss://api.vachana.ai/stt/v3/stream"

SUPPORTED_SAMPLE_RATES = (8000, 16000)
STREAM_CHUNK_BYTES = 1024


def language_to_gnani_language(language: Language) -> str:
    """Convert a Language enum to Gnani's language code format."""
    LANGUAGE_MAP = {
        Language.BN_IN: "bn-IN",
        Language.EN_IN: "en-IN",
        Language.GU_IN: "gu-IN",
        Language.HI_IN: "hi-IN",
        Language.KN_IN: "kn-IN",
        Language.ML_IN: "ml-IN",
        Language.MR_IN: "mr-IN",
        Language.PA_IN: "pa-IN",
        Language.TA_IN: "ta-IN",
        Language.TE_IN: "te-IN",
    }
    return resolve_language(language, LANGUAGE_MAP, use_base_code=False)


@dataclass
class GnaniSTTSettings(STTSettings):
    """Settings for GnaniSTTService.

    Parameters:
        sample_rate: Audio sample rate (8000 or 16000 Hz).
    """

    sample_rate: int | None | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


class GnaniSTTService(STTService):
    """Gnani Vachana speech-to-text service.

    Provides real-time speech recognition using Gnani Vachana's WebSocket API
    for Indian languages.

    Event handlers available (in addition to STTService events):

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
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        sample_rate: int | None = None,
        settings: Settings | None = None,
        keepalive_timeout: float | None = None,
        keepalive_interval: float = 5.0,
        **kwargs,
    ):
        """Initialize the Gnani Vachana STT service.

        Args:
            api_key: Gnani API key for authentication.
            sample_rate: Audio sample rate (8000 or 16000). Defaults to 16000.
            settings: Runtime-updatable settings.
            keepalive_timeout: Seconds of no audio before sending silence.
            keepalive_interval: Seconds between idle checks when keepalive is enabled.
            **kwargs: Additional arguments passed to the parent STTService.
        """
        default_settings = self.Settings(
            language=Language.EN_IN,
        )

        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            sample_rate=sample_rate or 16000,
            keepalive_timeout=keepalive_timeout,
            keepalive_interval=keepalive_interval,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._ws = None
        self._receive_task = None

    def language_to_service_language(self, language: Language) -> str:
        return language_to_gnani_language(language)

    def can_generate_metrics(self) -> bool:
        return True

    async def start(self, frame: StartFrame):
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._disconnect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if not self._ws:
            yield None
            return

        try:
            await self._ws.send(audio)
        except Exception as e:
            yield ErrorFrame(error=f"Error sending audio to Gnani: {e}", exception=e)

        yield None

    async def _connect(self):
        logger.debug("Connecting to Gnani Vachana STT")

        try:
            lang = self._get_language_string()
            headers = {
                "x-api-key-id": self._api_key,
                "lang_code": lang or "en-IN",
                **sdk_headers(),
            }

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
                logger.info(
                    f"Gnani STT connected: {connected_data.get('message', '')}"
                )
            else:
                logger.warning(f"Unexpected first message from Gnani STT: {connected_data}")

            self._receive_task = asyncio.create_task(
                self._receive_messages(), name="gnani-stt-recv"
            )

            await self._call_event_handler("on_connected")

        except Exception as e:
            logger.error(f"Failed to connect to Gnani STT: {e}")
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
                    continue

                data = json.loads(msg)
                msg_type = data.get("type", "")

                if msg_type == "transcript":
                    text = data.get("text", "")
                    if text:
                        await self.push_frame(
                            TranscriptionFrame(
                                text=text,
                                user_id=self._user_id if hasattr(self, "_user_id") else "",
                                timestamp=time_now_iso8601(),
                                language=self._get_language_string(),
                            )
                        )

                elif msg_type in ("speech_start", "vad_start"):
                    pass

                elif msg_type in ("speech_end", "vad_end"):
                    pass

                elif msg_type == "error":
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"Gnani STT stream error: {error_msg}")
                    await self.push_frame(ErrorFrame(error=f"Gnani STT: {error_msg}"))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Gnani STT receive error: {e}")
            await self._call_event_handler("on_connection_error", str(e))

    def _get_language_string(self) -> str | None:
        if self._settings.language:
            if isinstance(self._settings.language, Language):
                return language_to_gnani_language(self._settings.language)
            return str(self._settings.language)
        return "en-IN"
