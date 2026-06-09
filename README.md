# pipecat-gnani

[![PyPI](https://img.shields.io/pypi/v/pipecat-gnani)](https://pypi.org/project/pipecat-gnani/)
[![License](https://img.shields.io/badge/License-BSD%202--Clause-blue.svg)](LICENSE)

[Pipecat](https://github.com/pipecat-ai/pipecat) service integration for **[Gnani Vachana](https://gnani.ai/)** — high-accuracy Speech-to-Text and low-latency Text-to-Speech for Indian languages.

> **Vachana** is a production-ready speech AI platform by [Gnani.ai](https://gnani.ai) supporting 10+ Indian languages with 6 voices, real-time streaming, multilingual transcription, and code-switching capabilities.

## Installation

```bash
pip install pipecat-gnani
```

This will also install the [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) (>= 0.4.3) core SDK as a dependency.

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
        language="hi-IN",
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
        language="hi-IN",
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
        language="IND-IN",
    ),
)
```

## Services

### STT Services

| Service | Transport | Base Class | Description |
|---------|-----------|------------|-------------|
| `GnaniHttpSTTService` | REST POST | `SegmentedSTTService` | File-based transcription via `POST /stt/v3`. Requires VAD in pipeline. |
| `GnaniSTTService` | WebSocket | `STTService` | Real-time streaming via `wss://api.vachana.ai/stt/v3/stream` with VAD events. |

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

For the full list of supported languages, see [TTS — Supported Languages](https://docs.inya.ai/vachana/TTS/tts-inference#supported-languages).

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
gnani-vachana (>=0.4.3)  ← Core SDK (REST, SSE, WebSocket clients)
        ↑
pipecat-gnani            ← This package (Pipecat service adapters)
  ├── STT: REST + WebSocket
  └── TTS: REST + SSE + WebSocket
```

This package wraps the `gnani-vachana` SDK into Pipecat's `SegmentedSTTService`, `STTService`, `TTSService`, and `InterruptibleTTSService` base classes.

## Documentation

- [Vachana API Docs](https://docs.inya.ai/vachana/introduction/introduction)
- [Pipecat Docs](https://docs.pipecat.ai/)
- [gnani-vachana SDK](https://pypi.org/project/gnani-vachana/)
- [STT REST API](https://docs.inya.ai/vachana/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.inya.ai/vachana/STT/stt-websocket)
- [TTS REST API](https://docs.inya.ai/vachana/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.inya.ai/vachana/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.inya.ai/vachana/TTS/tts-websocket)

## License

BSD 2-Clause — see [LICENSE](LICENSE).
