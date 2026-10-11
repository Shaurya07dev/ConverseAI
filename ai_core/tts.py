"""
VaakSetu AI Core — Text-to-Speech (TTS) Pipeline (Fixed)

Uses Sarvam AI Bulbul v2 TTS.
Fixed: robust response parsing, detailed logging, proper base64 handling.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from ai_core.config import SARVAM_API_KEY

logger = logging.getLogger("vaaksetu.tts")

DEFAULT_VOICE    = "aditya"  # must be a bulbul:v3 speaker
DEFAULT_LANGUAGE = None  # None → detect from text, else en-IN

_SCRIPT_RANGES = [
    # Regional TTS reads both the native script and English, so script wins
    ("஀", "௿", "ta-IN"), ("ऀ", "ॿ", "hi-IN"),
    ("ఀ", "౿", "te-IN"), ("ঀ", "৿", "bn-IN"),
    ("ಀ", "೿", "kn-IN"), ("ഀ", "ൿ", "ml-IN"),
    ("઀", "૿", "gu-IN"), ("଀", "୿", "od-IN"),
    ("਀", "੿", "pa-IN"),
]
_HINGLISH_WORDS = {'hai','hain','ki','ko','se','aur','mein','ka','ke','kya','aap','nahi','yeh','woh','karo','kar','raha','rahi','hoon','hu','mera','tum','tumhara','kaise','bukhar','kripya','bataiye','madad'}
_ISO_TO_TTS = {
    'hi': 'hi-IN', 'en': 'en-IN', 'bn': 'bn-IN', 'kn': 'kn-IN',
    'ml': 'ml-IN', 'mr': 'mr-IN', 'pa': 'pa-IN', 'ta': 'ta-IN',
    'te': 'te-IN', 'gu': 'gu-IN', 'or': 'od-IN',
    # langdetect often mislabels romanised Hindi / short English as these
    'id': 'hi-IN', 'so': 'hi-IN', 'tl': 'hi-IN', 'fi': 'en-IN',
}


def _detect_language(text: str) -> Optional[str]:
    """Best-effort Sarvam TTS language code for text, or None if unsure."""
    for lo, hi, code in _SCRIPT_RANGES:
        if any(lo <= c <= hi for c in text):
            return code
    words = set(text.lower().replace(',', '').replace('?', '').replace('.', '').split())
    if len(words & _HINGLISH_WORDS) >= 2:
        return 'hi-IN'
    try:
        from langdetect import detect
        return _ISO_TO_TTS.get(detect(text))
    except Exception as e:
        logger.debug(f"Language detection failed: {e}")
        return None


class TTSPipeline:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from sarvamai import SarvamAI
            self._client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        return self._client

    async def synthesise(
        self,
        text: str,
        language_code: str = DEFAULT_LANGUAGE,
        speaker: str = DEFAULT_VOICE,
    ) -> Optional[bytes]:
        if not SARVAM_API_KEY:
            logger.warning("SARVAM_API_KEY not set — TTS disabled")
            return None

        if not text or not text.strip():
            return None

        text = text.strip()[:500]

        # ── Language Detection ──────────────────────────────────────────────
        # The reply language follows the user, so detect it per call; the
        # caller's language_code (agent default) is only the fallback.
        language_code = _detect_language(text) or language_code or "en-IN"

        logger.info(f"TTS synthesising {len(text)} chars in {language_code} (speaker={speaker})")

        try:
            result = await asyncio.to_thread(
                self._synthesise_sync, text, language_code, speaker
            )
            if result:
                logger.info(f"TTS OK — {len(result)} bytes")
            return result
        except Exception as e:
            logger.error(f"TTS synthesis failed: {type(e).__name__}: {e}", exc_info=True)
            return None

    def _synthesise_sync(self, text: str, language_code: str, speaker: str) -> bytes:
        client = self._get_client()

        response = client.text_to_speech.convert(
            text=text,
            language_code=language_code,
            speaker=speaker,
            model="bulbul:v3",
            enable_preprocessing=True,
        )

        logger.debug(f"TTS raw response type: {type(response)}, attrs: {[a for a in dir(response) if not a.startswith('_')]}")

        # ── Shape 1: response.audios = [base64_string, ...] ──────
        if hasattr(response, "audios") and response.audios:
            item = response.audios[0]
            logger.debug(f"TTS audios[0] type={type(item)}, len={len(item) if item else 0}")
            if isinstance(item, str):
                # It's already base64 — decode to bytes
                return base64.b64decode(item)
            if isinstance(item, (bytes, bytearray)):
                return bytes(item)

        # ── Shape 2: response.audio = base64 str or bytes ────────
        if hasattr(response, "audio") and response.audio:
            item = response.audio
            if isinstance(item, str):
                return base64.b64decode(item)
            if isinstance(item, (bytes, bytearray)):
                return bytes(item)

        # ── Shape 3: response is bytes directly ──────────────────
        if isinstance(response, (bytes, bytearray)):
            return bytes(response)

        # ── Shape 4: iterate if iterable ─────────────────────────
        try:
            raw = b"".join(bytes(chunk) for chunk in response if chunk)
            if raw:
                return raw
        except Exception:
            pass

        raise RuntimeError(
            f"Cannot extract audio from TTS response. "
            f"Type={type(response)}, repr={repr(response)[:200]}"
        )

    async def synthesise_b64(
        self,
        text: str,
        language_code: str = DEFAULT_LANGUAGE,
        speaker: str = DEFAULT_VOICE,
    ) -> Optional[str]:
        raw = await self.synthesise(text, language_code, speaker)
        if raw is None:
            return None
        b64 = base64.b64encode(raw).decode("utf-8")
        logger.info(f"TTS b64 length: {len(b64)}")
        return b64


# ── Singleton ─────────────────────────────────────────────────────────────────
_tts_pipeline: Optional[TTSPipeline] = None


def get_tts_pipeline() -> TTSPipeline:
    global _tts_pipeline
    if _tts_pipeline is None:
        _tts_pipeline = TTSPipeline()
    return _tts_pipeline
