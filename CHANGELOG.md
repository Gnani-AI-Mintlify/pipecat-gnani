# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.9] - 2026-07-16

### Fixed

- **TTS click/tick at segment start** — Gnani streaming sends a 44-byte WAV header (often with zero PCM) as the first chunk of each utterance, then raw PCM continuations. The SDK `_strip_wav_header` only stripped when `len(data) > 44`, so header-only first chunks were emitted as audio and sounded like a click at every segment boundary. Added a local `_strip_wav_header` (matching `livekit-plugins-gnani`) and `_TtsPcmProcessor` to buffer split headers across network chunks. Applies to HTTP, SSE, and WebSocket TTS.

## [0.5.8] - 2026-07-16

### Changed

- **BREAKING:** Default TTS model renamed from `vachana-voice-v3` to `timbre-v2.0` (requires `gnani-vachana>=0.7.7`).
- **`timbre-v2.5` support** — 42 voices with optional `language` in settings (timbre-v2.5 only; included in REST/SSE/WebSocket payloads).
- **Model-aware voice validation** via SDK `_validate_voice(voice, model)`.
- **Re-exported Timbre constants** — `DEFAULT_MODEL`, `TIMBRE_V20_VOICES`, `TIMBRE_V25_VOICES`, `SUPPORTED_TTS_LANGUAGES`.
- **WebSocket TTS uses `timbre-v2.0` directly** — removed `_wire_tts_model` mapping to `vachana-voice-v3`; REST, SSE, and WebSocket payloads now share the same model names.
- **Bumped `gnani-vachana` dependency to `>=0.7.7,<1.0`**.

## [0.5.7] - 2026-07-15


### Removed

- **`GnaniHttpSTTSettings.preferred_language`** — code-switching is no longer supported; use a single BCP-47 `language` per request.

## [0.5.5] - 2026-07-14

## [0.5.3] - 2026-07-14

### Changed

- **Bumped `gnani-vachana` dependency to `>=0.7.3,<1.0`** (from `>=0.7.2`).
- **`STT_SUPPORTED_SAMPLE_RATES`** now re-exports `STREAM_SUPPORTED_SAMPLE_RATES` from the SDK (`SAMPLE_RATE_44K`, `SAMPLE_RATE_48K`, etc.) instead of hardcoding `44100` and `48000`.
- **WebSocket header compatibility** — STT and TTS WebSocket connections use `ws_header_kwargs()` so `additional_headers` (websockets >= 13) and `extra_headers` (< 13) are selected automatically, matching `gnani-vachana` 0.7.2+.
- **`websockets` lower bound relaxed to `>=12.0`** to align with the core SDK and support environments that pin `websockets < 13`.

## [0.5.2] - 2026-07-14

### Changed

- **Minimum Python version is now 3.11** — `pipecat-ai` 1.5.0 (required by the `[example]` extra) needs Python ≥ 3.11; `requires-python`, CI matrix, and tool configs were updated accordingly.
- **Local development uses [uv](https://docs.astral.sh/uv/)** — `scripts/setup.sh` creates `.venv` with `uv venv` and installs via `uv sync --extra dev`. `Makefile`, `release.sh`, and CI workflows use `uv run`. `uv.lock` is generated locally for reproducible installs.

### Added

- **Phase 2 — Pipecat pattern alignment**
  - **Tracing** — `@traced_stt` moved to `_handle_transcription()` on HTTP and WebSocket STT (was on `run_stt()` for REST).
  - **Errors** — WebSocket STT/TTS connection and receive paths now call `push_error()` per the community integrations guide; HTTP STT/TTS/SSE API errors also call `push_error()` before yielding `ErrorFrame`.
  - **Runtime settings** — `GnaniSTTService._update_settings()` reconnects when connect-time fields change (`language`, `format`, `sample_rate`, `itn_native_numerals`); all TTS services validate voice changes and warn on unhandled settings via `_warn_unhandled_updated_settings()`.
  - **Frame types** — WebSocket STT honours `is_final` on transcript events (`InterimTranscriptionFrame` vs `TranscriptionFrame`). Streaming TTS `TTSTextFrame`s are emitted by the Pipecat base class after each synthesis request.
  - **Sample rate** — STT/TTS services defer `sample_rate` to `StartFrame` when not set in the constructor (constructor override still supported).
  - **Docstrings** — Google-style `Args:` / `Returns:` on service `__init__`, public methods, and `_common.py` helpers per Pipecat CONTRIBUTING conventions.
  - **`tests/test_runtime_settings.py`** — unit tests for settings updates and sample-rate negotiation.
  - **`tests/test_tracing_and_error_handling.py`** — tests for tracing (`_handle_transcription`), `push_error()` paths, interim transcripts, WebSocket message handling, TTS audio payloads, and sample-rate helpers.
- **`examples/foundational/`** — foundational WebRTC voice bot (`agent.py` + `env.example`) matching the [community integration layout](https://github.com/simpli-smart/pipecat-simplismart/tree/main/examples/foundational). Uses Gnani WebSocket STT + TTS with OpenAI LLM; run via `python agent.py -t webrtc` from that directory.
- **`[example]` optional dependency** — `pipecat-ai[runner,webrtc,silero,openai]` plus `python-dotenv` and `loguru` for running the foundational example.
- **README — quickstart example** — installation via `pip`/`uv` with `[example]` extra, `cd examples/foundational` run instructions, environment variable table, and Pipecat v1.5.0 compatibility note.
- **WebSocket lifecycle teardown** — `GnaniSTTService` and `GnaniTTSService` now share an idempotent `_teardown()` helper invoked from `stop()`, `cancel()`, and `cleanup()`, preventing leaked WebSocket connections when pipeline end/cancel frames do not propagate. `start()` resets the teardown guard so pipelines can reconnect on restart.
- **`tests/test_lifecycle.py`** — unit tests for idempotent teardown and `cleanup()`-without-prior-`stop()` behavior.
- **CI workflow** — GitHub Actions `CI` workflow (`.github/workflows/ci.yml`) runs ruff (lint + format check), mypy (advisory), and the test suite across Python 3.10–3.13 on every push and pull request.
- **Test suite is now committed** — `tests/`, `Makefile`, and `scripts/` are no longer gitignored, so the full unit + live integration suite can be run in CI and verified independently (`git clone` → `pip install -e ".[dev]"` → `pytest tests/`). The published wheel still ships only `pipecat_gnani/`, so tests never reach `pip install` users.
- **`DEVELOPMENT.md`** — development & release runbook covering setup, testing, and the tag-based PyPI publish flow.
- **`build`, `twine`** added to the `dev` optional dependencies; `make build` target builds the distribution and runs `twine check`.
- **`release-major`** Makefile target.

### Fixed

- **STT sample-rate resolution** — `_resolve_sample_rate()` now honors constructor `sample_rate=` before falling back to the 16 kHz default (connect headers were ignoring explicit overrides when `start()` had not run yet).
- **README dependency name** — corrected PyPI package reference from `gnani` to `gnani-vachana` (import package remains `gnani`).
- **REST STT sent raw PCM as a WAV file** — `GnaniHttpSTTService.run_stt` receives raw, headerless PCM from pipecat's VAD segmenter but uploaded it labelled `audio.wav` without a RIFF/WAV header, so the API's ffmpeg decode failed (`invalid start code in RIFF header`). In practice this broke REST STT in every real pipeline. `run_stt` now wraps raw PCM in a WAV container (at `self.sample_rate`) before upload, passing an already-WAV payload through untouched. Found via the TTS→STT roundtrip live test.
- **WebSocket TTS produced no audio** — `GnaniTTSService._receive_messages` read the base64 audio from the top-level `audio` key, but the server nests it under `data.audio` (`{"type": "audio", "data": {"audio": "…"}}`), matching the core SDK. Every audio chunk was silently dropped and WebSocket streaming TTS emitted only a `TTSStoppedFrame`. It now reads `data.audio` (with a top-level fallback), so streaming TTS emits audio.

### Changed

- **Fixed the SDK dependency name and bumped it to `gnani-vachana>=0.7.1,<1.0`** (was `gnani>=0.6.0,<1.0`). The core SDK is published on PyPI as `gnani-vachana` (the `gnani` distribution does not exist there), so the previous requirement made `pip install pipecat-gnani` unresolvable. The import package remains `gnani`. The bump also picks up the `websockets` 12.x compatibility fix and the additional STT streaming sample rates (44100, 48000 Hz).
- **PyPI publish** — the publish workflow now also triggers on `v*.*.*` tag pushes (and `workflow_dispatch`), validates that the tag matches the `pyproject.toml` version, and runs `twine check` on the built distribution before uploading.
- **Release script** — `scripts/release.sh` now promotes an existing `## [0.5.4] - 2026-07-14` changelog section to the new version (falling back to inserting an empty section) and supports non-interactive pushes via `--push` / `PUSH=1`.

## [0.5.1] - 2026-07-02

### Changed

- **TTS voices** — updated to 4 official voices: Pranav, Kaveri, Shubhra, Deepak. Removed legacy voices (Karan, Simran, Nara, Riya, Viraj, Raju). Default voice changed from `"Karan"` to `"Pranav"`. See [Available Voices](https://docs.gnani.ai/api/TTS/tts-sse#available-voices).

## [0.5.0] - 2026-07-01

### Added

- `TTS_LANGUAGE_MAP` and `tts_language_to_gnani()` helper re-added to `_common.py` for upstream Pipecat shim compatibility.
- Comprehensive QA test suite (unit + live integration tests) for all STT and TTS services.
- `Makefile` with `install`, `test`, `lint`, `format`, `check`, `fix` targets.
- `scripts/bump_version.py` and `scripts/release.sh` for versioning automation.

### Changed

- Bumped `gnani` SDK dependency to `>=0.6.0,<1.0` (from `>=0.4.3,<1.0`).
- Updated all docstrings to Google-style per Pipecat CONTRIBUTING.md conventions.
- Sorted `__all__` exports alphabetically.
- Added ruff lint ignore rules for pre-existing patterns (`B904`, `SIM105`).

## [0.4.1] - 2026-06-23

### Removed

- **`language` parameter from TTS** — removed `language` from all TTS service settings defaults and WebSocket request body. `GnaniHttpTTSService`, `GnaniSSETTSService`, and `GnaniTTSService` no longer set or send a language parameter. Removed `TTS_LANGUAGE_MAP`, `tts_language_to_gnani()`, and `language_to_service_language()` from TTS services.

### Changed

- **STT documentation** — clarified that only REST and Streaming (WebSocket) modes are integrated; no batch STT. Added PCM specification details with link to [STT Realtime — PCM Specification](https://docs.gnani.ai/api/STT/stt-websocket#pcm-specification).

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
