# Copyright (c) 2024-2026, Gnani.ai
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Voice agent using Gnani Vachana STT + TTS with Groq for the LLM.
#
# Usage:
#   cd examples/foundational
#   python agent.py -t webrtc
# Then open http://localhost:7860/client

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from pipecat_gnani import GnaniSTTService, GnaniTTSService

load_dotenv(override=True)

SYSTEM_PROMPT = (
    "You are a helpful voice assistant powered by Gnani Vachana. "
    "Keep your answers short and conversational — two or three sentences at most. "
    "Avoid markdown, bullet points, and any formatting that doesn't read naturally aloud."
)

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    gnani_api_key = os.environ.get("GNANI_API_KEY")
    if not gnani_api_key:
        raise RuntimeError("GNANI_API_KEY is not set. Copy env.example to .env and fill it in.")

    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Copy env.example to .env and fill it in.")

    # WebSocket STT — real-time streaming with built-in VAD events.
    # Languages (both models): Language.BN_IN, EN_IN, GU_IN, HI_IN, KN_IN,
    #   ML_IN, MR_IN, PA_IN, TA_IN, TE_IN
    # For callers who may speak any of ten Indian languages, use the multilingual
    # prisma-v3.0 model and let it identify the language. Candidates (2-4) make
    # detection more reliable, and keywords bias recognition towards your vocabulary:
    #   GnaniSTTService.Settings(
    #       model="prisma-v3.0",
    #       language="indic-auto",
    #       language_candidates=[Language.EN_IN, Language.HI_IN],
    #       keywords=["Gnani", "Vachana"],
    #   )
    # Each TranscriptionFrame then carries the detected language in frame.language.
    stt = GnaniSTTService(
        api_key=gnani_api_key,
        sample_rate=16000,
        settings=GnaniSTTService.Settings(
            language=Language.EN_IN,
        ),
    )

    # WebSocket TTS — lowest latency, supports interruption.
    # timbre-v2.5 (default): 42 voices, e.g. Nalini, Kaveri, Pranav
    # timbre-v3.0: 13 voices that speak every supported language, e.g.:
    #   settings=GnaniTTSService.Settings(voice="Shivani", model="timbre-v3.0", language="hi-IN")
    tts = GnaniTTSService(
        api_key=gnani_api_key,
        sample_rate=16000,
        settings=GnaniTTSService.Settings(
            voice="Nalini",
            model="timbre-v2.5",
            language=Language.EN_IN,
        ),
    )

    llm = GroqLLMService(
        api_key=groq_api_key,
        settings=GroqLLMService.Settings(
            model="llama-3.1-8b-instant",
            system_instruction=SYSTEM_PROMPT,
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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # Kick off the conversation.
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
