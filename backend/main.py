"""
VaakSetu Backend — FastAPI Application

Entry point: python -m uvicorn backend.main:app --port 8000 --reload
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import close_db, init_db
from backend.routes.agents import router as agents_router
from backend.routes.sessions import router as sessions_router
from backend.routes.live_mic import router as live_mic_router
from backend.twilio_config import validate_twilio_config

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vaaksetu.backend")


# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("=" * 60)
    logger.info("VaakSetu Backend — Starting up...")
    logger.info("=" * 60)

    # Initialize database
    await init_db()

    logger.info(f"✓ Twilio calls {'enabled' if TWILIO_ENABLED else 'disabled (TWILIO_* / PUBLIC_BASE_URL not set)'}")
    logger.info("✓ Backend ready")
    logger.info("=" * 60)

    yield

    logger.info("VaakSetu Backend — Shutting down...")
    await close_db()


# ── App ────────────────────────────────────────────────────────
app = FastAPI(
    title="VaakSetu API",
    description="AI-Powered Multilingual Conversational Intelligence Platform",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — comma-separated ALLOWED_ORIGINS, e.g. "https://app.vercel.app,http://localhost:3000"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(agents_router)
app.include_router(sessions_router)
app.include_router(live_mic_router)

# Twilio webhooks can't carry a user token, so call routes only exist when Twilio is configured
TWILIO_ENABLED = not validate_twilio_config()
if TWILIO_ENABLED:
    from backend.routes.calls import router as calls_router
    from backend.routes.twilio_media import router as twilio_media_router

    app.include_router(calls_router)
    app.include_router(twilio_media_router)

# Serve the static UI files
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    return {
        "service": "VaakSetu API",
        "version": "2.0.0",
        "status": "operational",
        "live_ui": "/live",
    }


@app.get("/live")
async def live_ui():
    """Serve the live conversation recording UI."""
    html_path = Path(__file__).parent / "static" / "live.html"
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "healthy"}
