"""
VaakSetu — Twilio Call Routes

Handles:
  1. POST /api/calls/outbound         — Initiate an outbound call via Twilio
  2. POST /api/calls/twiml            — TwiML webhook Twilio hits when call connects (returns <Stream>)
  3. POST /api/calls/status            — Twilio status callback (call ended, etc.)
  4. GET  /api/calls/{call_sid}/summary — Retrieve the final summary after a call ends
"""

import logging
from datetime import datetime, timezone

from fastapi import Depends, APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.twilio_config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    PUBLIC_BASE_URL,
    validate_twilio_config,
)

from backend.auth import current_user

logger = logging.getLogger("vaaksetu.routes.calls")
router = APIRouter(prefix="/api/calls", tags=["Twilio Calls"])

# In-memory store for call metadata (maps CallSid → metadata)
# In production this goes into PostgreSQL
_call_registry: dict[str, dict] = {}


# ── Request Models ──────────────────────────────────────────────

class OutboundCallRequest(BaseModel):
    to_number: str = Field(..., description="Phone number to call in E.164 format, e.g. +919876543210")
    domain: str = Field(default="healthcare", description="Domain for structured extraction: healthcare | finance")


# ── 1. Initiate Outbound Call ───────────────────────────────────

@router.post("/outbound")
async def initiate_outbound_call(req: OutboundCallRequest, user: str = Depends(current_user)):
    """
    Make an outbound call via Twilio.
    When the call connects, Twilio hits our /twiml webhook which returns
    TwiML instructing Twilio to stream the call audio to our WebSocket.
    """
    issues = validate_twilio_config()
    if issues:
        raise HTTPException(status_code=500, detail=f"Twilio config issues: {', '.join(issues)}")

    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    twiml_url = f"{PUBLIC_BASE_URL}/api/calls/twiml?domain={req.domain}"
    status_url = f"{PUBLIC_BASE_URL}/api/calls/status"

    try:
        call = client.calls.create(
            to=req.to_number,
            from_=TWILIO_PHONE_NUMBER,
            url=twiml_url,
            status_callback=status_url,
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
            record=True,  # Also record the call as a backup
        )

        # Register the call
        _call_registry[call.sid] = {
            "call_sid": call.sid,
            "to": req.to_number,
            "from": TWILIO_PHONE_NUMBER,
            "domain": req.domain,
            "status": "initiated",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
        }

        logger.info(f"Outbound call initiated: {call.sid} → {req.to_number}")
        return {
            "status": "ok",
            "call_sid": call.sid,
            "message": f"Call initiated to {req.to_number}. Audio will stream to our pipeline.",
        }

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. TwiML Webhook ───────────────────────────────────────────

@router.post("/twiml")
async def twiml_webhook(request: Request):
    """
    Twilio hits this URL when the call connects.
    We return TwiML that:
      1. Says a brief message
      2. Starts streaming the call audio to our WebSocket endpoint
      3. Keeps the call alive while recording
    """
    params = request.query_params
    domain = params.get("domain", "healthcare")

    # Build websocket URL — Twilio needs wss://
    ws_base = PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_base}/api/calls/media-stream?domain={domain}"

    # Get the CallSid from Twilio's POST form data
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")

    logger.info(f"TwiML webhook hit for CallSid={call_sid}, streaming to {stream_url}")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">This call is being recorded and analyzed by VaakSetu AI. Please proceed with your conversation.</Say>
    <Start>
        <Stream url="{stream_url}" name="vaaksetu_stream" />
    </Start>
    <Pause length="3600"/>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# ── 3. Status Callback ─────────────────────────────────────────

@router.post("/status")
async def status_callback(request: Request):
    """
    Twilio sends call status updates here.
    When status = 'completed', we finalize the summary.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")
    duration = form.get("CallDuration", "0")

    logger.info(f"Call status update: {call_sid} → {call_status} (duration: {duration}s)")

    if call_sid in _call_registry:
        _call_registry[call_sid]["status"] = call_status
        if call_status == "completed":
            _call_registry[call_sid]["ended_at"] = datetime.now(timezone.utc).isoformat()
            _call_registry[call_sid]["duration_seconds"] = int(duration)

    return {"status": "ok"}


# ── 4. Get Call Summary ─────────────────────────────────────────

@router.get("/{call_sid}/summary")
async def get_call_summary(call_sid: str, user: str = Depends(current_user)):
    """
    Retrieve the final summary, structured data, and transcript
    for a completed call. The media-stream WebSocket handler
    populates this data as audio streams in.
    """
    from backend.routes.twilio_media import get_call_data

    call_meta = _call_registry.get(call_sid)
    call_data = get_call_data(call_sid)

    if not call_data and not call_meta:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "status": "ok",
        "call_metadata": call_meta,
        "transcript": call_data.get("transcript", []) if call_data else [],
        "narrative": call_data.get("narrative", "") if call_data else "",
        "structured_data": call_data.get("structured_data", {}) if call_data else {},
        "speaker_map": call_data.get("speaker_map", {}) if call_data else {},
    }
