"""
VaakSetu — Twilio Configuration

Centralized Twilio credentials and helpers.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

# The public URL where Twilio can reach our server (set by ngrok or similar)
# This MUST be set before making calls — see walkthrough.md.
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")


def validate_twilio_config() -> list[str]:
    """Return warnings for missing Twilio config."""
    warnings = []
    if not TWILIO_ACCOUNT_SID:
        warnings.append("TWILIO_ACCOUNT_SID not set")
    if not TWILIO_AUTH_TOKEN:
        warnings.append("TWILIO_AUTH_TOKEN not set")
    if not TWILIO_PHONE_NUMBER:
        warnings.append("TWILIO_PHONE_NUMBER not set")
    if not PUBLIC_BASE_URL:
        warnings.append("PUBLIC_BASE_URL not set — Twilio cannot reach your server. Run ngrok and set this.")
    return warnings
