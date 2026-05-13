# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/Gnani-AI-Mintlify/pipecat-gnani/releases/tag/v0.2.0
[0.1.0]: https://github.com/Gnani-AI-Mintlify/pipecat-gnani/releases/tag/v0.1.0
