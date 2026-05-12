# pipecat-gnani

[![PyPI](https://img.shields.io/pypi/v/pipecat-gnani)](https://pypi.org/project/pipecat-gnani/)
[![License](https://img.shields.io/badge/License-BSD%202--Clause-blue.svg)](LICENSE)

[Pipecat](https://github.com/pipecat-ai/pipecat) service integration for **[Gnani Vachana](https://gnani.ai/)** — high-accuracy Speech-to-Text and low-latency Text-to-Speech for Indian languages.

> **Vachana** is a production-ready speech AI platform by [Gnani.ai](https://gnani.ai) supporting 10+ Indian languages with real-time streaming, multilingual transcription, and code-switching capabilities.

## Installation

```bash
pip install pipecat-gnani
```

This will also install the [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) core SDK as a dependency.

## Prerequisites

You need a Gnani API key. Email **[speechstack@gnani.ai](mailto:speechstack@gnani.ai)** to get started — all new accounts receive free credits, no credit card required.

```bash
export GNANI_API_KEY="your-api-key"
```

## Quick Start

### Speech-to-Text (Streaming)

```python
from pipecat_gnani import GnaniSTTService

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
        voice="sia",
        language="hi-IN",
    ),
)
```

### Text-to-Speech (Streaming WebSocket)

```python
from pipecat_gnani import GnaniTTSService

tts = GnaniTTSService(
    api_key="your-api-key",
    settings=GnaniTTSService.Settings(
        voice="sia",
        language="IND-IN",
    ),
)
```

## Services

### GnaniSTTService

Real-time streaming speech-to-text via WebSocket with VAD (Voice Activity Detection) support.

- Connects to `wss://api.vachana.ai/stt/v3/stream`
- Sends raw PCM audio in 1024-byte chunks
- Receives transcription events with segment metadata
- Supports 8 kHz and 16 kHz sample rates

### GnaniHttpTTSService

REST-based text-to-speech for non-streaming use cases.

- Uses `POST /api/v1/tts/inference`
- Returns complete audio in a single response
- Suitable for batch synthesis

### GnaniTTSService

WebSocket-based streaming text-to-speech with interruption handling.

- Connects to `wss://api.vachana.ai/api/v1/tts`
- Streams audio chunks in real-time
- Extends `InterruptibleTTSService` for proper interruption support
- Ideal for conversational voice agents

## Supported Languages

| Language        | Code    |
|-----------------|---------|
| Bengali         | `bn-IN` |
| English (India) | `en-IN` |
| Gujarati        | `gu-IN` |
| Hindi           | `hi-IN` |
| Kannada         | `kn-IN` |
| Malayalam       | `ml-IN` |
| Marathi         | `mr-IN` |
| Punjabi         | `pa-IN` |
| Tamil           | `ta-IN` |
| Telugu          | `te-IN` |

## Available Voices

| Voice   | ID        |
|---------|-----------|
| Sia     | `sia`     |
| Raju    | `raju`    |
| Kanika  | `kanika`  |
| Nikita  | `nikita`  |
| Ravan   | `ravan`   |
| Simran  | `simran`  |
| Karan   | `karan`   |
| Neha    | `neha`    |

## Architecture

```
gnani-vachana      ← Core SDK (REST, WebSocket, SSE clients)
    ↑
pipecat-gnani      ← This package (Pipecat service adapter)
```

This package is a thin adapter that wraps the `gnani-vachana` SDK into Pipecat's `STTService`, `TTSService`, and `InterruptibleTTSService` base classes. All connection logic, authentication, and audio format handling lives in the core SDK.

## Documentation

- [Vachana API Docs](https://docs.inya.ai/vachana/introduction/introduction)
- [Pipecat Docs](https://docs.pipecat.ai/)
- [gnani-vachana SDK](https://pypi.org/project/gnani-vachana/)

## License

BSD 2-Clause — see [LICENSE](LICENSE).
