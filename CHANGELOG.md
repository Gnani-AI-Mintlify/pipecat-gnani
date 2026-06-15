# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-06-15 

- Changing Gnani Url in the documentation

## [0.3.0] - 2026-06-09

### Added

- **GnaniHttpSTTService** — REST-based STT via `POST /stt/v3`, extending `SegmentedSTTService` (requires VAD in pipeline).
- **GnaniSSETTSService** — SSE streaming TTS via `POST /api/v1/tts/sse`, extending `TTSService`. Lower latency than REST.
- Shared `_common.py` module with constants, language maps, and helpers to reduce duplication.

### Changed

- **BREAKING:** Updated TTS model from `vachana-voice-v2` to `vachana-voice-v3` (the only model supported by `gnani-vachana` 0.4.3).
- **BREAKING:** Updated TTS voices to match `gnani-vachana` 0.4.3 — now 6 voices with capitalized names: `Karan`, `Simran`, `Nara`, `Riya`, `Viraj`, `Raju`. Replaces old lowercase 8-voice set (`sia`, `raju`, `kanika`, `nikita`, `ravan`, `simran`, `karan`, `neha`).
- **BREAKING:** Default voice changed from `sia` to `Karan`.
- Bumped `gnani-vachana` dependency to `>=0.4.3,<1.0`.
- Added Assamese (`as-IN`) and Odia (`or-IN`) to both STT and TTS language maps.
- Added Hinglish experimental language codes (`en-hi-IN-latn`, `en-hi-in-cm`) to STT supported languages.
- Added `processing` to handled STT WebSocket event types.
- Updated documentation with complete service matrix (2 STT + 3 TTS) and full Vachana API doc links.

## [0.2.0] - 2026-05-13

### Changed

- Version bump to align with livekit-plugins-gnani v0.2.0 release.

## [0.1.0] - 2026-05-12

### Added

- **GnaniSTTService** — real-time streaming STT via WebSocket (`wss://api.vachana.ai/stt/v3/stream`) with VAD event support.
- **GnaniHttpTTSService** — REST-based TTS synthesis (`POST /api/v1/tts/inference`) for non-streaming use cases.
- **GnaniTTSService** — WebSocket-based streaming TTS (`wss://api.vachana.ai/api/v1/tts`) with interruption handling via `InterruptibleTTSService`.
- Support for 10 Indian languages: Bengali, English (India), Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil, Telugu.
- 8 voice options for TTS: sia, raju, kanika, nikita, ravan, simran, karan, neha.
- Configurable audio output: sample rate, encoding (linear_pcm, oggopus), container (raw, mp3, wav, mulaw, ogg).
- Built on top of the [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) core SDK.

[0.3.0]: https://github.com/Gnani-AI-Mintlify/pipecat-gnani/releases/tag/v0.3.0
[0.2.0]: https://github.com/Gnani-AI-Mintlify/pipecat-gnani/releases/tag/v0.2.0
[0.1.0]: https://github.com/Gnani-AI-Mintlify/pipecat-gnani/releases/tag/v0.1.0
