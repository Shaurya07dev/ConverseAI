"""
VaakSetu — Twilio Media Stream WebSocket Handler

This is the core of the real-call integration.
Twilio streams mulaw/8kHz audio chunks to this WebSocket endpoint.
We:
  1. Decode mulaw → PCM → 16kHz WAV
  2. Buffer audio chunks into ~5 second segments
  3. Run ASR (Sarvam) on each segment
  4. Feed the transcript into the LangGraph agent for incremental summarisation
  5. Store final summary when the stream closes (call ends)
"""

import audioop
import base64
import io
import json
import logging
import tempfile
import wave
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("vaaksetu.twilio.media")
router = APIRouter(prefix="/api/calls", tags=["Twilio Media Stream"])

# ── Per-call state ──────────────────────────────────────────────
# Maps call_sid → accumulated call data
_call_data: dict[str, dict] = defaultdict(lambda: {
    "audio_buffer": bytearray(),
    "transcript": [],
    "narrative": "",
    "structured_data": {},
    "speaker_map": {},
    "stream_sid": None,
    "call_sid": None,
    "domain": "healthcare",
    "chunk_count": 0,
})

# Mulaw audio parameters from Twilio
TWILIO_SAMPLE_RATE = 8000       # Twilio sends 8kHz mulaw
TARGET_SAMPLE_RATE = 16000      # Our ASR models expect 16kHz
BUFFER_DURATION_SEC = 5         # Accumulate N seconds of audio before running ASR
BUFFER_SIZE_BYTES = TWILIO_SAMPLE_RATE * BUFFER_DURATION_SEC  # 8000 * 5 = 40000 mulaw bytes


def get_call_data(call_sid: str) -> dict | None:
    """Retrieve call data for the summary endpoint."""
    if call_sid in _call_data:
        return dict(_call_data[call_sid])
    return None


def _mulaw_buffer_to_wav(mulaw_bytes: bytes) -> bytes:
    """
    Convert raw mulaw 8kHz bytes → 16kHz PCM WAV bytes.
    Steps:
      1. audioop.ulaw2lin: mulaw → 16-bit PCM at 8kHz
      2. audioop.ratecv: upsample 8kHz → 16kHz
      3. Write into an in-memory WAV file
    """
    # Decode mulaw to linear PCM (16-bit, 8kHz)
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)

    # Upsample to 16kHz
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, TWILIO_SAMPLE_RATE, TARGET_SAMPLE_RATE, None)

    # Write to WAV in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(TARGET_SAMPLE_RATE)
        wf.writeframes(pcm_16k)

    return wav_buffer.getvalue()


# One shared ASR pipeline and graph processor: the processor keeps per-call
# state keyed by call_sid, so it must outlive individual audio chunks.
_asr_pipeline = None
_stream_processor = None


async def _transcribe_buffer(wav_bytes: bytes) -> str:
    """Run ASR on a WAV buffer and return the transcript text."""
    global _asr_pipeline
    from ai_core.asr import ASRPipeline

    # Write WAV to temp file (ASR expects a file path)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        if _asr_pipeline is None:
            _asr_pipeline = ASRPipeline()
        result = await _asr_pipeline.transcribe(tmp_path)
        return result.transcript
    except Exception as e:
        logger.error(f"ASR failed for buffer: {e}")
        return ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def _run_graph_agent(call_sid: str, transcript_chunk: str):
    """Push transcript chunk into the LangGraph agent and update call state."""
    global _stream_processor
    from ai_core.conversation_processor import StreamConversationProcessor

    if _stream_processor is None:
        _stream_processor = StreamConversationProcessor()
    domain = _call_data[call_sid]["domain"]

    result = await _stream_processor.ingest_chunk(call_sid, domain, transcript_chunk)

    if result.get("status") == "success":
        _call_data[call_sid]["narrative"] = result.get("narrative", "")
        _call_data[call_sid]["structured_data"] = result.get("structured_data", {})
        _call_data[call_sid]["speaker_map"] = result.get("speaker_map", {})
        logger.info(f"[{call_sid}] Graph agent updated narrative ({len(result.get('narrative', ''))} chars)")


# ── WebSocket Handler ───────────────────────────────────────────

@router.websocket("/media-stream")
async def twilio_media_stream(websocket: WebSocket):
    """
    Receives Twilio Media Stream messages.
    
    Twilio sends JSON messages with these events:
      - connected: WebSocket connection established
      - start: Stream metadata (callSid, streamSid, tracks, encoding)
      - media: Audio payload (base64-encoded mulaw)
      - stop: Stream ended (call hung up)
    """
    await websocket.accept()
    call_sid = None
    domain = websocket.query_params.get("domain", "healthcare")

    logger.info("Twilio Media Stream WebSocket accepted")

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info(f"Twilio stream connected: {data.get('protocol', 'unknown')}")

            elif event == "start":
                start_data = data.get("start", {})
                call_sid = start_data.get("callSid", "unknown")
                stream_sid = start_data.get("streamSid", "unknown")
                _call_data[call_sid]["call_sid"] = call_sid
                _call_data[call_sid]["stream_sid"] = stream_sid
                _call_data[call_sid]["domain"] = domain
                logger.info(
                    f"Stream started: CallSid={call_sid}, StreamSid={stream_sid}, "
                    f"tracks={start_data.get('tracks')}, encoding={start_data.get('mediaFormat', {}).get('encoding')}"
                )

            elif event == "media":
                if not call_sid:
                    continue

                # Decode base64 mulaw audio payload
                payload = data.get("media", {}).get("payload", "")
                audio_chunk = base64.b64decode(payload)
                _call_data[call_sid]["audio_buffer"].extend(audio_chunk)
                _call_data[call_sid]["chunk_count"] += 1

                # When buffer reaches ~5 seconds, process it
                if len(_call_data[call_sid]["audio_buffer"]) >= BUFFER_SIZE_BYTES:
                    buffer_bytes = bytes(_call_data[call_sid]["audio_buffer"])
                    _call_data[call_sid]["audio_buffer"] = bytearray()  # Reset

                    # Convert mulaw → WAV → transcribe → feed LangGraph
                    wav_bytes = _mulaw_buffer_to_wav(buffer_bytes)
                    transcript = await _transcribe_buffer(wav_bytes)

                    if transcript.strip():
                        _call_data[call_sid]["transcript"].append(transcript)
                        logger.info(f"[{call_sid}] Transcribed chunk: '{transcript[:80]}...'")

                        # Feed into LangGraph for incremental summarisation
                        await _run_graph_agent(call_sid, transcript)

            elif event == "stop":
                logger.info(f"Stream stopped for CallSid={call_sid}")

                # Process any remaining audio in the buffer
                if call_sid and len(_call_data[call_sid]["audio_buffer"]) > 0:
                    remaining = bytes(_call_data[call_sid]["audio_buffer"])
                    _call_data[call_sid]["audio_buffer"] = bytearray()

                    wav_bytes = _mulaw_buffer_to_wav(remaining)
                    transcript = await _transcribe_buffer(wav_bytes)

                    if transcript.strip():
                        _call_data[call_sid]["transcript"].append(transcript)
                        await _run_graph_agent(call_sid, transcript)

                # Final summary pass with all transcript
                if call_sid and _call_data[call_sid]["transcript"]:
                    full_transcript = "\n".join(_call_data[call_sid]["transcript"])
                    logger.info(
                        f"[{call_sid}] Call ended. Full transcript ({len(full_transcript)} chars). "
                        f"Final narrative: {len(_call_data[call_sid].get('narrative', ''))} chars."
                    )

                break  # Exit the loop — stream is done

    except WebSocketDisconnect:
        logger.info(f"Twilio Media Stream disconnected (CallSid={call_sid})")
    except Exception as e:
        logger.error(f"Twilio Media Stream error: {e}", exc_info=True)
    finally:
        if call_sid:
            logger.info(
                f"[{call_sid}] Stream processing complete. "
                f"Chunks: {_call_data[call_sid]['chunk_count']}, "
                f"Segments: {len(_call_data[call_sid]['transcript'])}"
            )
