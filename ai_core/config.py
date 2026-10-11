"""
VaakSetu AI Core — Centralized Configuration

Loads all environment variables from .env and exposes them
as typed constants. Import this module anywhere in ai_core
to access settings without re-reading .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Resolve project paths ──────────────────────────────────────
# ai_core/config.py → project root is two levels up
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Load .env from project root ────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

# ── Sarvam AI (ASR + TTS) ──────────────────────────────────────
SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
SARVAM_STT_MODEL: str = "saaras:v3"        # Latest SOTA model
SARVAM_STT_MODE: str = "transcribe"         # transcribe | translate | codemix

# ── HuggingFace token for Diarization ─────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")

# ── Chat LLM (dialogue agent, extractor, summaries, reward judge) ──
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # any OpenAI-compatible endpoint
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.sarvam.ai/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "sarvam-105b-conversations")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_TEMPERATURE: float = 0.7

# ── Domain Config Defaults ──────────────────────────────────────
MAX_CONVERSATION_TURNS: int = 20

# ── RLAIF Reward Engine Defaults ────────────────────────────────
REWARD_LLM_WEIGHT: float = 0.6
REWARD_PROGRAMMATIC_WEIGHT: float = 0.4
DPO_THRESHOLD: float = 0.70  # >= this → "chosen", < this → "rejected"
IDEAL_TURN_MIN: int = 4
IDEAL_TURN_MAX: int = 8


def validate_config() -> list[str]:
    """
    Check that critical environment variables are set.
    Returns a list of warning messages (empty = all good).
    """
    warnings = []
    if not SARVAM_API_KEY:
        warnings.append("⚠ SARVAM_API_KEY not set — ASR and TTS will fail. Set it in .env")
    if not LLM_API_KEY:
        warnings.append("⚠ LLM_API_KEY not set — agent replies and scoring will fail. Set it in .env")
    return warnings


if __name__ == "__main__":
    # Quick validation when run directly
    print(f"Project Root : {PROJECT_ROOT}")
    print(f"Sarvam Key   : {'✅ set' if SARVAM_API_KEY else '❌ missing'}")
    print(f"LLM Key      : {'✅ set' if LLM_API_KEY else '❌ missing'}")
    print(f"LLM          : {LLM_PROVIDER} {LLM_MODEL} @ {LLM_BASE_URL}")

    issues = validate_config()
    if issues:
        print("\n--- Issues ---")
        for w in issues:
            print(w)
    else:
        print("\n✅ All config validated!")
