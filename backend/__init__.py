"""
VaakSetu Backend — FastAPI app (agents, sessions, live capture, calls).
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env before any backend module reads os.environ (real env vars win)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
