# pipecat-gnani

[![PyPI](https://img.shields.io/pypi/v/pipecat-gnani)](https://pypi.org/project/pipecat-gnani/)
[![License](https://img.shields.io/badge/License-BSD%202--Clause-blue.svg)](LICENSE)

[Pipecat](https://github.com/pipecat-ai/pipecat) service integration for **[Gnani](https://gnani.ai/)** — high-accuracy Speech-to-Text and low-latency Text-to-Speech for Indian languages.

> **Gnani** is a production-ready speech AI platform supporting 10+ Indian languages, real-time streaming, multilingual transcription, and code-switching capabilities.

> This integration is maintained by [Gnani.ai](https://gnani.ai/).

## Installation

```bash
pip install pipecat-gnani
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pipecat-gnani
```

This will also install the [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) (>= 0.7.2) core SDK as a dependency. The Python import package name remains `gnani`.

The WebRTC quickstart below needs the **`example`** extra (Pipecat runner, Silero VAD, WebRTC stack, and Groq LLM):

```bash
pip install "pipecat-gnani[example]"
# or: uv add "pipecat-gnani[example]"
```

**From source**:

```bash
git clone https://github.com/Gnani-AI-Mintlify/pipecat-gnani.git
cd pipecat-gnani
uv pip install -e ".[example]"
```

## Prerequisites

You need a Gnani API key. Email **[speechstack@gnani.ai](mailto:speechstack@gnani.ai)** to get started — all new accounts receive free credits, no credit card required.

## Quickstart example

The example lives in this repository's `examples/foundational/` directory (not in the PyPI wheel). Clone the repo, then run a small WebRTC bot: Gnani WebSocket STT/TTS, OpenAI LLM, and the Pipecat runner CLI.

1. Copy `examples/foundational/env.example` to `examples/foundational/.env` and set `GNANI_API_KEY` and `GROQ_API_KEY`.
2. With the **`example`** extra installed (see **Install**), from the clone root:

```bash
cd examples/foundational
python agent.py -t webrtc
```

If you use **uv** in a git checkout, from the repository root:

```bash
uv sync --extra example
cd examples/foundational
uv run --extra example python agent.py -t webrtc
```

3. Open the **Pipecat playground** at [http://localhost:7860/client](http://localhost:7860/client), connect, and speak.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `GNANI_API_KEY` | API key for Gnani Vachana STT and TTS |
| `GROQ_API_KEY` | API key for the Groq LLM in the foundational example |

## Quick Start — Pipeline snippet

The snippet below shows the core `Pipeline([...])` wiring used in the foundational example. See [`examples/foundational/agent.py`](examples/foundational/agent.py) for the full runnable version.

```python
import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transcriptions.language import Language
from pipecat_gnani import GnaniSTTService, GnaniTTSService

# transport = ...  # WebRTC — see examples/foundational/agent.py

stt = GnaniSTTService(
    api_key=os.environ["GNANI_API_KEY"],
    settings=GnaniSTTService.Settings(language=Language.HI_IN),
)

tts = GnaniTTSService(
    api_key=os.environ["GNANI_API_KEY"],
    settings=GnaniTTSService.Settings(voice="Pranav"),
)

llm = GroqLLMService(
    api_key=os.environ["GROQ_API_KEY"],
    settings=GroqLLMService.Settings(
        model="llama-3.1-8b-instant",
    ),
)

context = LLMContext()
aggregators = LLMContextAggregatorPair(
    context,
    user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
)

pipeline = Pipeline(
    [
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ]
)

task = PipelineTask(
    pipeline,
    params=PipelineParams(enable_metrics=True),
)
```

Swap service classes in `agent.py` for REST or SSE variants — see the file for options (WebSocket STT + TTS is the default for lowest latency and interruption support).

## Service Construction

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
        voice="Pranav",
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
        voice="Pranav",
    ),
)
```

### Text-to-Speech (WebSocket Streaming)

```python
from pipecat_gnani import GnaniTTSService

tts = GnaniTTSService(
    api_key="your-api-key",
    settings=GnaniTTSService.Settings(
        voice="Pranav",
    ),
)
```

## Services

### STT Services

| Service | Transport | Base Class | Description |
|---------|-----------|------------|-------------|
| `GnaniHttpSTTService` | REST POST | `SegmentedSTTService` | File-based transcription via `POST /stt/v3`. Requires VAD in pipeline. |
| `GnaniSTTService` | WebSocket | `STTService` | Real-time streaming via `wss://api.vachana.ai/stt/v3/stream` with VAD events. Emits `TranscriptionFrame` (final) and `InterimTranscriptionFrame` when the API sets `is_final: false` (today Gnani sends final transcripts only). |

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
| `GnaniTTSService` | WebSocket | `InterruptibleTTSService` | Streaming via `wss://api.vachana.ai/api/v1/tts`. Lowest latency, interruption support. `TTSTextFrame`s are emitted by the Pipecat base class after each synthesis request. |

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

See the [official voice list](https://docs.gnani.ai/api/TTS/tts-sse#available-voices) for the latest supported voices.

| Voice   | Gender | Description              |
|---------|--------|--------------------------|
| Pranav  | Male   | Bold, Trustworthy        |
| Kaveri  | Female | Confident, Bright        |
| Shubhra | Female | Gentle, Expressive       |
| Deepak  | Male   | Grounded, Conversational |

## Architecture

```
gnani-vachana (>=0.7.2)  ← Core SDK on PyPI (import as `gnani`)
        ↑
pipecat-gnani            ← This package (Pipecat service adapters)
  ├── STT: REST + WebSocket
  └── TTS: REST + SSE + WebSocket
```

This package wraps the `gnani` SDK into Pipecat's `SegmentedSTTService`, `STTService`, `TTSService`, and `InterruptibleTTSService` base classes.

## Documentation

- [Gnani API Docs](https://docs.gnani.ai/)
- [Pipecat Docs](https://docs.pipecat.ai/)
- [gnani-vachana SDK on PyPI](https://pypi.org/project/gnani-vachana/)
- [STT REST API](https://docs.gnani.ai/api/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.gnani.ai/api/STT/stt-websocket)
- [TTS REST API](https://docs.gnani.ai/api/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.gnani.ai/api/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.gnani.ai/api/TTS/tts-websocket)

## Pipecat Compatibility

Tested with **Pipecat v1.5.0**.

## License

BSD 2-Clause — see [LICENSE](LICENSE).
