# VaakSetu — Code Walkthrough

A guided tour: run it, then follow each request through the code. Architecture and roadmap are in `plan.md`.

---

## 1. Run it in five minutes

```bash
cp .env.example .env            # set SARVAM_API_KEY and LLM_API_KEY
python -m venv venv && venv\Scripts\activate      # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q             # offline, fakes the LLM and auth; should print "8 passed"
python -m uvicorn backend.main:app --port 8000 --reload
cd frontend && npm install && npm run dev          # http://localhost:3000
```

Sanity checks:
- `http://localhost:8000/health` returns `{"status":"healthy"}`.
- `http://localhost:8000/docs` shows the OpenAPI UI with every route.
- `python -m ai_core.config` prints which keys are set and which LLM is configured.

---

## 2. Repository map

```
backend/                    FastAPI app — HTTP/WS surface + persistence
  main.py                   app, CORS, router registration, /health, /live
  database.py               SQLite schema + async CRUD (agents, sessions, messages)
  twilio_config.py          Twilio env vars + validation
  routes/
    agents.py               /api/agents        CRUD
    sessions.py             /api/sessions*, /api/transcribe, /api/tts
    live_mic.py             WS /api/live/stream
    calls.py                /api/calls/outbound|twiml|status|{sid}/summary
    twilio_media.py         WS /api/calls/media-stream
  static/live.html          standalone live-capture page

ai_core/                    AI building blocks (no FastAPI imports)
  config.py                 env → constants; `python -m ai_core.config` to check
  llm.py                    chat_model() / chat_client() / strip_reasoning()
  dialogue_agent.py         DialogueAgent — turn loop for agent sessions
  field_extractor.py        FieldExtractor — LLM → {field: value}
  graph_agent.py            LangGraph summariser for observed conversations
  conversation_processor.py per-session state around the graph agent
  domain_schemas.py         Pydantic extraction schemas per domain (+ generic fallback)
  asr.py  tts.py            Sarvam speech in / out
  reward_engine.py          session quality score + DPO label
  audio_binaries.py         finds ffmpeg for pydub

frontend/src/
  app/(dashboard)/          pages: / healthcare banking platform analysis session/[agentId](/stats)
  components/               Navbar, AgentWizard, ThemeProvider, …
  data/                     static content for the sample use-case pages
  lib/useCaseDemoPdf.js     PDF export for the demo pages

tests/test_api_smoke.py     agent CRUD + full text session with fake LLM/TTS
```

Conventions you'll see everywhere:
- AI components are **lazily created singletons**. For example, `_get_agent()` in `routes/sessions.py` builds the agent on first use, so importing the app needs no API keys.
- Sync SDK calls are wrapped in `asyncio.to_thread`.

---

## 3. Flow A: an agent session (text or voice)

This is what `/session/[agentId]` in the frontend drives.

1. **Create an agent.** The `AgentWizard` on `/analysis` sends `POST /api/agents` to `routes/agents.py` and on to `database.create_agent`. The agent config holds `fields` (what to collect), `prompt`, `greeting`, `triggers` (escalation phrases) and `default_language`. If no greeting is given, one is generated.

2. **Start.** `POST /api/sessions {agent_id}` is handled by `routes/sessions.py::api_start_session`:
   - creates the session row;
   - `DialogueAgent.start_session()` returns the greeting, which is stored as message turn 0;
   - `tts.synthesise_b64()` produces optional greeting audio (base64 WAV, or `null` without a Sarvam key).

3. **Each turn.** `POST /api/sessions/{id}/message {content}` calls `DialogueAgent.respond()` in `dialogue_agent.py`:
   1. **Escalation check.** If any trigger phrase appears, it returns `escalation_message` with `is_escalation=true`.
   2. **Two LLM calls run in parallel** (`asyncio.gather`):
      - `FieldExtractor.extract_fields()` asks the LLM for JSON values of the *missing* fields. `"__NULL__"` means "user doesn't know". If the LLM gives nothing usable, a regex heuristic fills in obvious values.
      - The reply call uses `_build_system_prompt()`, which tells the LLM what is collected, what is missing, and what to ask next.
   3. It merges the extracted fields, appends the turn to the in-memory history, and computes `missing_fields` and `is_complete`.
   4. Back in the route, the messages and `collected_fields` are persisted and TTS runs on the reply.

4. **Voice input.** The session page records WebM with `MediaRecorder` and sends `POST /api/transcribe`. That calls `ASRPipeline.transcribe_bytes()` in `asr.py`:
   - the audio is converted to 16 kHz mono WAV (pydub + ffmpeg);
   - Sarvam `saaras:v3` transcribes it, falling back to IndicWhisper if installed;
   - the returned text is sent to `/message` like typed text.

5. **End and score.** `POST /api/sessions/{id}/end` calls `RewardEngine.score()` in `reward_engine.py`:
   - The programmatic score covers turn efficiency, sentiment, resolution and safety.
   - The LLM judge is a JSON score on 5 dimensions via `chat_client()`.
   - The combined score is weighted 0.4 / 0.6 and gets a `chosen`/`rejected` label.
   - The result is stored in `sessions.reward_scores` and shown on `/session/[agentId]/stats`.

---

## 4. Flow B: live capture (observe mode)

This flow drives `http://localhost:8000/live` (`static/live.html`) through `WS /api/live/stream` in `routes/live_mic.py`.

```
client → {"type":"start","domain":"healthcare"}         server → session_started
client → {"type":"transcript_text","text":"..."}        server → transcript_ack, agent_update{narrative, structured_data}
client → {"type":"audio_chunk","data":"<b64>"}          (optional server-side ASR)
client → {"type":"stop"}                                 server → processing, summary_complete{transcript, narrative, structured_data}
```

- The browser's Web Speech API produces the text, so no server-side ASR is needed on the main path.
- Each chunk goes into `StreamConversationProcessor.ingest_chunk()`, which runs the **graph agent** (`graph_agent.py`):
  - `ingest` increments the turn count.
  - `classify_roles` runs in the first turns and maps speakers to roles.
  - `extract_structured` runs every 5th turn. It uses `with_structured_output` against the domain schema in `domain_schemas.py`.
  - `update_narrative` incrementally extends a third-person summary.
- On `stop`, a single final LLM call (`_generate_final_summary`) re-summarises the full transcript. The session is saved under the built-in agent `live-mic`.

---

## 5. Flow C: an outbound phone call

Prerequisites:
- `docker compose up -d` starts the ngrok tunnel.
- Put the public https URL into `PUBLIC_BASE_URL`.
- Fill in the `TWILIO_*` values.

1. `POST /api/calls/outbound {to_number, domain}` (`routes/calls.py`) calls the Twilio REST API to create the call. Its `url` points at `/api/calls/twiml` and its status callback at `/api/calls/status`.
2. When the call is answered, Twilio fetches **TwiML**. The response speaks a recording notice, then `<Start><Stream>` to `wss://…/api/calls/media-stream`.
3. **`routes/twilio_media.py`** receives the JSON events `connected`, `start`, `media` (base64 μ-law, 8 kHz) and `stop`:
   - It buffers 5 s of audio per call.
   - It converts the audio with `audioop`: μ-law to PCM, then 8 to 16 kHz WAV.
   - It runs ASR on each buffer and pushes the transcript into the **shared** `StreamConversationProcessor`, so state accumulates per `call_sid`.
4. `/api/calls/status` records the lifecycle. `GET /api/calls/{sid}/summary` returns the transcript, narrative, structured data and speaker map.

The stream is listen-only, so the agent does not speak on calls yet (see `plan.md` §2.6).

---

## 6. How to change things

| Task | Where |
|---|---|
| Switch LLM provider/model | `.env`: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (any OpenAI-compatible API). Code: `ai_core/llm.py`. |
| New use case (hotel desk, support line, …) | No code needed. Create an agent in the UI with its role prompt, greeting, fields to capture and escalation triggers. |
| New domain schema for observed calls / live capture | Add a Pydantic model and map entry in `ai_core/domain_schemas.py` |
| Change scoring weights or threshold | `ai_core/config.py` (`REWARD_*`, `DPO_THRESHOLD`, `IDEAL_TURN_*`) |
| TTS voice / language behaviour | `ai_core/tts.py` (`DEFAULT_VOICE`, `_detect_language`) |
| Add an API route | New module in `backend/routes/`, then `app.include_router(...)` in `backend/main.py` |
| DB column | `SCHEMA_SQL` and the row mappers in `backend/database.py`. There are no migrations yet, so delete `vaaksetu.db` in dev. |

---

## 7. Deployment

Production runs on free tiers (details in `plan.md` §2.7):

- **Backend:** Render builds `Dockerfile` from `main` on every push. Set its env vars in the Render dashboard; `ALLOWED_ORIGINS` must include the Vercel URL.
- **Frontend:** Vercel builds `frontend/` on every push.
- **Database + auth:** Neon. To allow a new frontend domain, add it under Neon Console → Auth → Configuration → trusted domains.

Auth locally: leave `NEON_AUTH_JWKS_URL` empty in `.env` and the backend runs as a single user `local` (that's what the tests use). To test real sign-in locally, set `NEON_AUTH_JWKS_URL` in `.env` and the three variables from `frontend/.env.example` in `frontend/.env.local`; localhost is a trusted origin by default.

## 8. Testing & debugging

- **Tests:** `python -m pytest -q`.
  - `tests/test_api_smoke.py` points `database.DB_PATH` at a temp file.
  - It monkeypatches `chat_model` / `chat_client` with fakes that emit `<think>` blocks and fenced JSON, the way real reasoning models do.
  - It runs agent CRUD plus start, message and end.
- **Logs:** uvicorn stdout, in the format `HH:MM:SS | LEVEL | logger | message`. Startup warns about missing keys and Twilio config.
- **Common failures:**

| Symptom | Cause |
|---|---|
| "Maaf kijiye, technical problem" reply | LLM call failed: check `LLM_API_KEY` / `LLM_BASE_URL` |
| `reward_scores: {"error": ...}` | Judge call failed for the same reason |
| `greeting_audio: null` | No `SARVAM_API_KEY`, or Sarvam TTS error (see log) |
| `/transcribe` 500 | Sarvam key missing, or ffmpeg not found. Put ffmpeg on `PATH` or in `tools/ffmpeg/`. |
| Twilio never connects | `PUBLIC_BASE_URL` isn't the current ngrok https URL |
