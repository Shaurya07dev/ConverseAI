"""
VaakSetu AI Core — speech, dialogue, extraction, scoring

Main modules:
  • asr            — Speech-to-Text (Sarvam STT + IndicWhisper fallback)
  • dialogue_agent — slot-filling dialogue agent (chat LLM via llm.py)
  • reward_engine  — RLAIF scoring (programmatic + LLM judge)
"""

from ai_core.config import validate_config

# Run config validation on import — print warnings if keys are missing
_warnings = validate_config()
if _warnings:
    import sys
    for w in _warnings:
        print(w, file=sys.stderr)
