# pipecat-gnani

[![PyPI](https://img.shields.io/pypi/v/pipecat-gnani)](https://pypi.org/project/pipecat-gnani/)
[![License](https://img.shields.io/badge/License-BSD%202--Clause-blue.svg)](LICENSE)

[Pipecat](https://github.com/pipecat-ai/pipecat) service integration for **[Gnani](https://gnani.ai/)** — high-accuracy Speech-to-Text and low-latency Text-to-Speech for Indian languages.

> **Gnani** is a production-ready speech AI platform supporting 10+ Indian languages, real-time streaming, and multilingual transcription.

> This integration is maintained by [Gnani.ai](https://gnani.ai/).

## Installation

```bash
pip install pipecat-gnani
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pipecat-gnani
```

This will also install the [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) (>= 0.9.0) core SDK as a dependency. Requires **Python 3.11+** and **Pipecat 1.5 or newer (1.x)**. The Python import package name remains `gnani`.

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

You need a Gnani API key. [Gnani APIs](https://app.gnani.ai/voice) have this.

Set your credentials as environment variables:

```bash
export GNANI_API_KEY="your-api-key"
```

## Quickstart example

The example lives in this repository's `examples/foundational/` directory (not in the PyPI wheel). Clone the repo, then run a small WebRTC bot: Gnani WebSocket STT/TTS, Groq LLM, and the Pipecat runner CLI.

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

## Models

| | Model | Notes |
|---|-------|-------|
| STT | `prisma-v2.5` (default) | Languages: the 10 listed below. Formats: `verbatim`, `transcribe`. |
| STT | `prisma-v3.0` | Adds `indic-auto` language detection, language candidates, extra formats (`codemix`, `transliterate`) and context hints. Set `model="prisma-v3.0"`. |
| TTS | `timbre-v2.5` (default) | 42 voices. |
| TTS | `timbre-v3.0` | 13 voices. Set `model="timbre-v3.0"` and pick a v3.0 voice (a voice must belong to the chosen model). |

`timbre-v2.0` has been retired and is rejected.

## Settings

Pass settings through the service's `Settings` class, for example `GnaniSTTService.Settings(language=Language.HI_IN)`. Invalid values raise `ValueError` when the service is created (and when settings are updated at runtime), before any request is sent.

### STT settings

| Setting | Services | Default | Description |
|---------|----------|---------|-------------|
| `language` | both | `Language.EN_IN` | A `Language`, a locale string (`"hi-IN"`), or `INDIC_AUTO` for automatic detection (`prisma-v3.0`). |
| `model` | both | server default (`prisma-v2.5`) | `"prisma-v2.5"` or `"prisma-v3.0"`. |
| `format` | both | `verbatim` | `verbatim` or `transcribe` (inverse text normalization: numbers, dates, currency). `codemix` and `transliterate` need `prisma-v3.0`. |
| `itn_native_numerals` | both | off | With `format="transcribe"`, write digits in the native script. |
| `language_candidates` | both | none | 2-4 likely languages. Only with `language=INDIC_AUTO` and `prisma-v3.0`. A hint, not a lock. |
| `keyterms` | both | none | Up to 200 words or phrases to favour. `prisma-v3.0` only. |
| `topic` | both | none | Free-text description of the audio, up to 1,600 characters. `prisma-v3.0` only. |
| `previous_text` | both | none | What was said just before (last 600 characters are used). `prisma-v3.0` only. |
| `speaker_names` | both | none | 1-4 speaker names. `prisma-v3.0` only. |
| `sample_rate` | WebSocket | `16000` | `8000`, `16000`, `44100` or `48000`. |

Changing `language`, `format`, `model`, candidates or context hints on a running WebSocket STT service reconnects it with the new values.

#### Automatic language detection

```python
from pipecat_gnani import INDIC_AUTO, GnaniSTTService

stt = GnaniSTTService(
    api_key=os.environ["GNANI_API_KEY"],
    settings=GnaniSTTService.Settings(
        model="prisma-v3.0",
        language=INDIC_AUTO,
        language_candidates=[Language.HI_IN, Language.EN_IN],  # recommended
        keyterms=["Gnani", "Vachana"],
    ),
)
```

Each `TranscriptionFrame.language` carries the language the API detected (falling back to the configured one), so downstream processors can react to it.

> **Tip:** pass `language_candidates` when you use `INDIC_AUTO`. Bare `INDIC_AUTO` on short utterances followed by silence can mis-detect the language (for example English audio reported as Telugu on the REST endpoint). Candidates, or a fixed language, are more reliable.

### TTS settings

| Setting | Default | Description |
|---------|---------|-------------|
| `voice` | `Pranav` | Voice name. Must belong to the selected model. |
| `model` | `timbre-v2.5` | `timbre-v2.5` or `timbre-v3.0`. |
| `language` | none | `"auto"`, a locale such as `"hi-IN"`, or a `Language`. Works on both models. |
| `speed` | server default (1.0) | Speaking rate, `0.85` to `1.15`. Can be changed at runtime. |
| `sample_rate` (constructor) | from the pipeline | `8000`, `16000`, `22050`, `24000`, `44100` or `48000`. If the pipeline asks for another rate, the service warns and uses 16 kHz. |

Audio is always 16-bit PCM, which is what Pipecat plays. The `encoding` and `container` settings only accept `linear_pcm` and `wav` / `raw`; other formats (mp3, ogg, mulaw, alaw) raise `ValueError`. Telephony transports convert to mulaw/alaw themselves.

> **Deprecated:** the `sample_width` and `bitrate` TTS settings, and the `SUPPORTED_ENCODINGS`, `SUPPORTED_CONTAINERS` and `SUPPORTED_BITRATES` exports, are ignored or misleading and will be removed in a future release. They currently log a `DeprecationWarning`.

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

STT uses BCP-47 locale codes with the `-IN` suffix: `bn-IN`, `en-IN`, `gu-IN`, `hi-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `pa-IN`, `ta-IN`, `te-IN`. `INDIC_AUTO` (`prisma-v3.0`) detects the language automatically.

For the full list of supported languages, see [STT — Supported Languages](https://docs.gnani.ai/api/STT/speech-to-text#supported-languages).

### TTS Languages (Text-to-Speech)

TTS uses the same `-IN` locale codes as STT (`hi-IN`, `en-IN`, ...), plus `auto`. Pipecat `Language` values are converted for you; languages Gnani TTS does not support (for example `or-IN`) raise `ValueError`.

For the full list of supported languages, see [TTS — Supported Languages](https://docs.gnani.ai/api/TTS/tts-inference#supported-languages).

## Available Voices

The full catalog, with gender and style, is in the [official voice list](https://docs.gnani.ai/api/TTS/available-voices). Every voice belongs to one model:

- **`timbre-v2.5`**: 42 voices, for example `Pranav` (default), `Kaveri`, `Nalini`, `Asmita`, `Deepak`.
- **`timbre-v3.0`**: 13 voices: `Avinash`, `Chetana`, `Devansh`, `Harshad`, `Kalpana`, `Lakshmi`, `Prakash`, `Riyaa`, `Shivani`, `Shubham`, `Tarika`, `Vasudha`, `Yashraj`.

The lists are available in code as `pipecat_gnani.TIMBRE_V25_VOICES` and `pipecat_gnani.TIMBRE_V30_VOICES`.

## Architecture

```
gnani-vachana (>=0.9.0)  ← Core SDK on PyPI (import as `gnani`)
        ↑
pipecat-gnani            ← This package (Pipecat service adapters)
  ├── STT: REST + WebSocket
  └── TTS: REST + SSE + WebSocket
```

The `gnani` SDK supplies the model catalog, voices, languages and validation rules; this package makes the API calls and adapts them to Pipecat's `SegmentedSTTService`, `STTService`, `TTSService`, and `InterruptibleTTSService` base classes.

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

Supports **Pipecat 1.5 and newer 1.x releases** (`pipecat-ai>=1.5.0,<2.0`). Tested on 1.5.0 and 1.15.0.

## License

BSD 2-Clause — see [LICENSE](LICENSE).
