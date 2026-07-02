# pipecat-gnani

[![PyPI](https://img.shields.io/pypi/v/pipecat-gnani)](https://pypi.org/project/pipecat-gnani/)
[![License](https://img.shields.io/badge/License-BSD%202--Clause-blue.svg)](LICENSE)

[Pipecat](https://github.com/pipecat-ai/pipecat) service integration for **[Gnani](https://gnani.ai/)** — high-accuracy Speech-to-Text and low-latency Text-to-Speech for Indian languages.

> **Gnani** is a production-ready speech AI platform supporting 10+ Indian languages with 6 voices, real-time streaming, multilingual transcription, and code-switching capabilities.

## Installation

```bash
pip install pipecat-gnani
```

This will also install the [`gnani`](https://pypi.org/project/gnani/) (>= 0.6.0) core SDK as a dependency.

## Prerequisites

You need a Gnani API key. Email **[speechstack@gnani.ai](mailto:speechstack@gnani.ai)** to get started — all new accounts receive free credits, no credit card required.

```bash
export GNANI_API_KEY="your-api-key"
```

## Quick Start

### Speech-to-Text (REST)

```python
from pipecat_gnani import GnaniHttpSTTService
from pipecat.transcriptions.language import Language

stt = GnaniHttpSTTService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniHttpSTTService.Settings(
        language=Language.HI_IN,
    ),
)
```

### Speech-to-Text (Streaming WebSocket)

```python
from pipecat_gnani import GnaniSTTService
from pipecat.transcriptions.language import Language

stt = GnaniSTTService(
    api_key="your-api-key",
    settings=GnaniSTTService.Settings(
        language=Language.HI_IN,
    ),
)
```

### Text-to-Speech (REST)

```python
from pipecat_gnani import GnaniHttpTTSService

tts = GnaniHttpTTSService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniHttpTTSService.Settings(
        voice="Karan",
    ),
)
```

### Text-to-Speech (SSE Streaming)

```python
from pipecat_gnani import GnaniSSETTSService

tts = GnaniSSETTSService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniSSETTSService.Settings(
        voice="Karan",
    ),
)
```

### Text-to-Speech (WebSocket Streaming)

```python
from pipecat_gnani import GnaniTTSService

tts = GnaniTTSService(
    api_key="your-api-key",
    settings=GnaniTTSService.Settings(
        voice="Karan",
    ),
)
```

## Services

### STT Services

| Service | Transport | Base Class | Description |
|---------|-----------|------------|-------------|
| `GnaniHttpSTTService` | REST POST | `SegmentedSTTService` | File-based transcription via `POST /stt/v3`. Requires VAD in pipeline. |
| `GnaniSTTService` | WebSocket | `STTService` | Real-time streaming via `wss://api.vachana.ai/stt/v3/stream` with VAD events. |

#### Streaming PCM Specification

All streaming audio must be sent as **raw PCM binary frames** — no container format (WAV, MP3) mid-stream.

| Property          | 16 kHz                                    | 8 kHz                                     |
|-------------------|-------------------------------------------|-------------------------------------------|
| Encoding          | PCM signed 16-bit little-endian           | PCM signed 16-bit little-endian           |
| Sample Rate       | 16,000 Hz                                 | 8,000 Hz                                  |
| Channels          | 1 (mono)                                  | 1 (mono)                                  |
| Samples per chunk | 512                                       | 512                                       |
| **Bytes per frame** | **1,024 bytes** (512 samples × 2 bytes) | **1,024 bytes** (512 samples × 2 bytes)   |
| Frame duration    | 32 ms                                     | 64 ms                                     |

Frames must be sent at **real-time cadence**. See **[STT Realtime — PCM Specification](https://docs.gnani.ai/api/STT/stt-websocket#pcm-specification)** for full details.

### TTS Services

| Service | Transport | Base Class | Description |
|---------|-----------|------------|-------------|
| `GnaniHttpTTSService` | REST POST | `TTSService` | Single-request synthesis via `POST /api/v1/tts/inference`. |
| `GnaniSSETTSService` | SSE | `TTSService` | Streaming synthesis via `POST /api/v1/tts/sse`. Lower latency than REST. |
| `GnaniTTSService` | WebSocket | `InterruptibleTTSService` | Streaming via `wss://api.vachana.ai/api/v1/tts`. Lowest latency, interruption support. |

## Supported Languages

### STT Languages (Speech-to-Text)

STT uses BCP-47 locale codes (e.g. `hi-IN`).

| Language        | Code    |
|-----------------|---------|
| Assamese        | `as-IN` |
| Bengali         | `bn-IN` |
| English (India) | `en-IN` |
| Gujarati        | `gu-IN` |
| Hindi           | `hi-IN` |
| Kannada         | `kn-IN` |
| Malayalam       | `ml-IN` |
| Marathi         | `mr-IN` |
| Odia            | `or-IN` |
| Punjabi         | `pa-IN` |
| Tamil           | `ta-IN` |
| Telugu          | `te-IN` |

### TTS Languages (Text-to-Speech)

TTS uses ISO 639 language codes (e.g. `hi`, `bn`). Note: TTS does **not** use the `-IN` suffix.

For the full list of supported languages, see [TTS — Supported Languages](https://docs.gnani.ai/api/TTS/tts-inference#supported-languages).

## Available Voices

| Voice  | Gender | Description              |
|--------|--------|--------------------------|
| Karan  | Male   | Bold, Trustworthy        |
| Simran | Female | Confident, Bright        |
| Nara   | Female | Gentle, Expressive       |
| Riya   | Female | Cheerful, Energetic      |
| Viraj  | Male   | Commanding, Dynamic      |
| Raju   | Male   | Grounded, Conversational |

## Architecture

```
gnani (>=0.6.0)          ← Core SDK (REST, SSE, WebSocket clients)
        ↑
pipecat-gnani            ← This package (Pipecat service adapters)
  ├── STT: REST + WebSocket
  └── TTS: REST + SSE + WebSocket
```

This package wraps the `gnani` SDK into Pipecat's `SegmentedSTTService`, `STTService`, `TTSService`, and `InterruptibleTTSService` base classes.

## Documentation

- [Gnani API Docs](https://docs.gnani.ai/)
- [Pipecat Docs](https://docs.pipecat.ai/)
- [gnani SDK](https://pypi.org/project/gnani/)
- [STT REST API](https://docs.gnani.ai/api/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.gnani.ai/api/STT/stt-websocket)
- [TTS REST API](https://docs.gnani.ai/api/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.gnani.ai/api/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.gnani.ai/api/TTS/tts-websocket)

## License

BSD 2-Clause — see [LICENSE](LICENSE).
