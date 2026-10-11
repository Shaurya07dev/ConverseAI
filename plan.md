# VaakSetu — Architecture & Plan

*वाक् + सेतु — the voice bridge.* A configurable business voice agent that records and documents conversations. Single source of truth for **what VaakSetu is, how it is built today, and where it is going.**
For how to run it see `README.md`; for a guided tour of the code see `walkthrough.md`.

---

## 1. Context

**VaakSetu is a configurable voice agent for businesses.** Any place where a conversation must be held *and* documented well can deploy it, tailored to its own use case:

- **Front desks:** hotel reception, hospital or clinic desks, bank branches, office lobbies.
- **Customer calls:** inbound support, outbound follow-ups, sales and collections.
- **Personal and team use:** meeting summaries, interviews, consultations.

**The problem.** Conversations carry the information a business runs on, but documenting them is still manual. Staff take notes by hand after the conversation, details get lost, and records are inconsistent and hard to audit. In India, customers also switch freely between English and regional languages mid-sentence, which breaks rigid IVR bots and form-based tools.

**What VaakSetu does.** It **runs or listens to a multilingual conversation and turns it into a structured record plus a readable summary**, with a quality score for every session. Every deployment is an **agent config**: role, prompt, greeting, fields to capture and escalation triggers. Adding a new industry is configuration, not new code.

**History.** VaakSetu began as a hackathon prototype by Team AGNISHAKTI (SRMIST Kattankulathur) aimed at healthcare and loan-collection workflows. It is now being built into a general business product. The web app (dashboard and API) is the current focus; a Flutter mobile app is scaffolded for later.

### Example deployments
| Use case | Mode | Typical fields captured | Escalation examples |
|---|---|---|---|
| Hotel front desk | agent responds | guest name, room, request type, check-in/out dates, special needs | complaint, emergency |
| Hospital / clinic reception | agent responds | visitor name, reason for visit, department, preferred slot | medical emergency |
| Customer support line | agent responds | customer id, issue, product, resolution, follow-up | angry customer, legal threat |
| Collections / follow-up call | agent drives | customer, account, payment status, promised date, reason | dispute, fraud |
| Meeting / consultation notes | agent observes | participants, decisions, action items, next steps | — |
| Anything else | any | defined per agent in the UI | defined per agent |

There are no per-industry services. Every row above is the same primitive with a different config.

---

## 2. Current architecture (as built)

```
 Browser → Next.js 16 (Vercel)                Twilio (PSTN, optional)
   │  Neon Auth sign-in; JWT on every API call  │ webhooks + media WS
   │  direct to NEXT_PUBLIC_API_URL              │
   ▼                                             ▼
 FastAPI backend  (backend/, Render, Docker)  ─────────────────────────────
   routes/agents.py      CRUD for agent configs
   routes/sessions.py    text/voice sessions, /transcribe, /tts, end+score
   routes/live_mic.py    WS /api/live/stream — passive "observe" capture
   routes/calls.py       outbound call, TwiML, status, call summary
   routes/twilio_media.py WS /api/calls/media-stream — call audio in
   auth.py               verifies Neon Auth JWTs (JWKS), per-user ownership
   database.py           Postgres on Neon (asyncpg) / SQLite locally
   static/live.html      standalone live-capture UI (/live)
        │
        ▼
 AI core (ai_core/)  ───────────────────────────────────────────────
   llm.py               single factory for the chat LLM (LLM_* env)
   dialogue_agent.py    slot-filling agent: reply + extraction in parallel
   field_extractor.py   LLM → JSON field values (+ regex fallback)
   graph_agent.py       LangGraph: roles → structured extract → narrative
   conversation_processor.py  per-session state for the graph agent
   domain_schemas.py    Pydantic extraction schemas per domain
   asr.py               Sarvam saaras:v3 STT (+ optional IndicWhisper)
   tts.py               Sarvam bulbul:v3 TTS, per-call language detection
   reward_engine.py     RLAIF score: 40% programmatic + 60% LLM judge
   audio_binaries.py    locates ffmpeg/ffprobe for pydub
```

**Dependency direction:** `backend` → `ai_core`, never the reverse.

### 2.1 External services
| Service | Used for | Config |
|---|---|---|
| OpenAI-compatible chat LLM (default **Sarvam `sarvam-105b-conversations`**) | dialogue replies, field extraction, call/live summaries, reward judge | `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` |
| Sarvam AI | speech-to-text (`saaras:v3`), text-to-speech (`bulbul:v3`) | `SARVAM_API_KEY` |
| Twilio | outbound calls + media streams | `TWILIO_*`, `PUBLIC_BASE_URL` |
| ngrok (docker-compose) | exposes :8000 to Twilio | `NGROK_AUTHTOKEN` |
| HuggingFace (optional) | IndicWhisper offline ASR fallback | `HF_TOKEN`, plus `torch` and `transformers` |

The LLM provider changed in Oct 2026: the GitHub Models endpoint (`OPENAI_*` / `MODEL_NAME`) was retired, and agentrouter.org (tried next) only serves approved coding-agent clients, so it cannot back an app. The default is now Sarvam chat (same key as speech). All chat calls now go through `ai_core/llm.py`, so switching provider is an `.env` change. Reasoning models' `<think>…</think>` output is stripped before parsing (`strip_reasoning`).

### 2.2 The four conversation flows
| Flow | Entry point | Mode | What happens |
|---|---|---|---|
| **Agent session** (text/voice) | `POST /api/sessions` → `/message` → `/end` | agent **responds** | Greeting, then per turn: escalation check, then extraction and reply in parallel; optional TTS audio. `/end` scores the session. |
| **Voice input** | `POST /api/transcribe` | — | Browser records WebM; Sarvam STT returns text, which feeds `/message`. |
| **Live capture** | `WS /api/live/stream` (and `/live` page) | agent **observes** | Browser Web Speech API sends text chunks; the graph agent updates the narrative and structured data incrementally; `stop` produces a final summary, persisted under agent `live-mic`. |
| **Phone call** | `POST /api/calls/outbound` → TwiML → `WS /api/calls/media-stream` | agent **observes** | Twilio streams μ-law 8 kHz audio, buffered in ~5 s chunks, converted to WAV, transcribed and fed into the graph agent. Summary at `GET /api/calls/{sid}/summary`. |

### 2.3 Data model (Neon Postgres in production, SQLite `vaaksetu.db` locally; created/upgraded on startup)
- **agents**: `id, name, domain, custom_domain, inputs[], fields[], system_prompt, greeting, triggers[], escalation{}, escalation_message, default_language, timestamps`
- **sessions**: `id, agent_id → agents, status, collected_fields{}, is_complete, turn_count, created_at, ended_at, reward_scores{}`
- **messages**: `id, session_id → sessions, role, content, turn_number, created_at`

Agents and sessions carry an `owner_id` (the Neon Auth user id); every route filters by it, and other users' records return 404. Lists and dicts are stored as JSON text. Deleting an agent cascades to its sessions and messages.

### 2.4 Quality loop (RLAIF)
`reward_engine.RewardEngine.score()` runs on `/end`:
- **Programmatic (40%)**: turn efficiency (ideal 4–8 turns), sentiment delta, resolution (all fields collected), content safety.
- **LLM judge (60%)**: politeness, accuracy, language fluency, policy compliance (stays within its role), resolution quality (1–5 each), plus one feedback sentence.
- **Combined** score ≥ 0.70 → `chosen`, otherwise `rejected`. These are DPO labels for future preference tuning.

### 2.5 Frontend (`frontend/`)
- **Marketing pages:** `/`, `/platform`, and two sample use-case pages, `/healthcare` (clinic desk) and `/banking` (customer calls), each with a PDF export.
- **Operations:** `/analysis` has CRUD for agents and sessions, plus the `AgentWizard` that creates or edits agents.
- **Sessions:**
  - `/session/[agentId]` is the chat or voice session with an agent.
  - `/session/[agentId]/stats` shows the transcript, collected fields and reward scores, and exports a PDF.
- All backend calls go through `src/lib/api.js` (`apiFetch`), straight to `NEXT_PUBLIC_API_URL` with `Authorization: Bearer <JWT>`.
- **Auth:** `/auth/sign-up` and `/auth/sign-in` (`components/AuthForm.jsx`) use Neon Auth (managed Better Auth) through the `/api/auth/*` proxy. Sign-up requires a 6-digit email code; `src/proxy.js` redirects signed-out visitors away from `/analysis` and `/session/*`.

### 2.6 Known limitations (current tech debt)
| Area | Limitation | Upgrade path |
|---|---|---|
| State | Dialogue history, graph-agent state and the call registry live in process memory and are lost on restart. A single worker is assumed. | Persist turn state in the DB (§3, event log) |
| Security | Auth + per-user ownership are in place (§2.7), but there are no per-user usage quotas, and Twilio webhooks are **not** signature-validated (call routes are only mounted when Twilio is configured). | Quotas per account; §3 invariant 10 |
| Extraction | Free-form JSON parsed from the LLM, with no grounding to source turns | §3 invariants 6 and 12, T07 |
| Calls | Listen-only `<Start><Stream>`: the agent cannot speak on calls. Fixed 5 s buffers, and audio is upsampled to 16 kHz. | T16–T19, T23 |
| Structured output | `graph_agent` uses `with_structured_output`; not yet verified against `sarvam-105b-conversations` | Verify; fall back to JSON mode |
| Frontend | `npm run lint` reports 7 `react-hooks/set-state-in-effect` errors; the build passes | Refactor effects |
| Tests | Offline smoke + auth/tenancy suites (fake LLM, signed test JWTs); also pass against Neon Postgres. No ASR/TTS/Twilio tests. | Add per-flow tests |

### 2.7 Deployment & auth (live)
| Piece | Where | Notes |
|---|---|---|
| Frontend | Vercel (`frontend/`) | env: `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`, `NEXT_PUBLIC_API_URL` |
| Backend | Render free web service, Docker (`Dockerfile`, Singapore) | env: `LLM_*`, `SARVAM_API_KEY`, `DATABASE_URL`, `NEON_AUTH_JWKS_URL`, `ALLOWED_ORIGINS`. Sleeps after ~15 min idle; first request then takes up to a minute. |
| Database + auth | Neon project `vaaksetu` (`aws-ap-southeast-1`), branch `main` | Postgres for app data; Neon Auth stores users/sessions in the `neon_auth` schema |

**Why accounts can't be farmed for free usage:** an account only gets API access once its email is verified with a code sent to that inbox. The backend checks the JWT's `emailVerified` claim on every request (and also rejects `banned` users), so this holds even if the Neon setting were switched off. Admins can ban users from Neon Console → Auth → Users.

---

## 3. Target architecture (roadmap)

This replaces the earlier `MASTER_PLAN.md` / `CLAUDE.md` specs (available in git history at commit `b3a60b1`). The direction is a **multi-tenant platform where one primitive serves three surfaces**:

- **Personal recorder**: a mobile app records conversations and meetings and returns summaries.
- **Client agent**: a configurable receptionist, kiosk or role assistant (hospital, bank, hotel).
- **Calling agent**: an outbound and inbound phone agent that talks, acts and summarises.

```
Session = (mode, channel, persona) → Transcript + Record + Narrative + Actions
mode     OBSERVE (listen) | RESPOND (listen+speak+act) | DRIVE (agent leads)
channel  MOBILE_MIC | MEETING_BOT | PSTN_IN | PSTN_OUT | KIOSK | TEXT
```
Today's flows map onto this as: agent session = `RESPOND/TEXT`, live capture = `OBSERVE/MOBILE_MIC`, phone call = `OBSERVE/PSTN_OUT`.

**Live path:** ingress adapter → media (VAD, endpointing) → ASR → bus → agent_runtime → TTS → egress, with action_service handling side effects.
**Async path:** `session.ended` → diarise → reconcile transcript → schema-constrained extract → narrate → embed → score → tenant webhook.

### 3.1 Invariants (violating one is a bug even if tests pass)
1. `session_events` is append-only; turns, records and narratives are projections rebuildable from it.
2. Every tenant table has `tenant_id NOT NULL` plus Postgres row-level security. Never filter by tenant in Python only.
3. The media path never blocks on an LLM or TTS call; components communicate over the bus.
4. All ingress normalises to PCM16 / 16 kHz / mono / 20 ms frames inside the adapter.
5. No fixed-size audio buffers in RESPOND or DRIVE mode; turn boundaries come from VAD endpointing.
6. Structured extraction uses schema-constrained decoding, never `json.loads` on free text.
7. Side effects run in `action_service` with an idempotency key; the agent only returns intent.
8. Personas are immutable once published; sessions pin `persona_version`.
9. No PII in event payloads; store references to encrypted columns so erasure requests can be honoured.
10. Telephony webhooks validate the provider signature first. Unsigned requests get a 403 and the body is not logged.
11. Speech is untrusted input: tool arguments are schema-validated, and irreversible actions need confirmation.
12. Every AI-generated field carries a `source_turn_id`; ungrounded fields are dropped.

### 3.2 Target stack
- **Language and web:** Python 3.12, `uv`, FastAPI, Pydantic v2.
- **Data:** SQLAlchemy 2 async + Alembic, Postgres 16 + pgvector, Redis 7, with Redis Streams behind an `EventBus` protocol (NATS later).
- **Storage:** S3/MinIO.
- **Quality:** pytest + testcontainers; ruff + mypy (strict on core).
- **Logging:** structlog JSON logs, PII-redacted, bound to `session_id` and `tenant_id`.

**Target layout:** `app/{core, api/v1, services/{agent_runtime, action_service, intelligence}, ingress, media, inference/{asr,llm,tts,embed}, infra, workers}`.
- `core` has zero I/O.
- `api` never imports `inference`.

**Conventions:**
- Async everywhere.
- Typed errors.
- UTC timestamps.
- `_ms` durations.
- Integer paise for money.
- UUIDv7 IDs.
- Every task ships its tests.

### 3.3 Task graph
| Phase | Tasks | Gate |
|---|---|---|
| **0 Skeleton (no audio)** | T01 scaffold + `/healthz` `/readyz` · T02 domain model, state machine, protocols · T03 persona spec + validator · T04 schema + RLS · T05 event log + projections · T06 inference layer + fallback chain + budgets · T07 schema-constrained, grounded extraction · T08 narrative (incremental preview + final) · T09 TEXT adapter end-to-end | 10-turn `hospital_reception` text session yields a populated Record and Narrative |
| **1 Passive audio (recorder ships)** | T10 chunked resumable upload · T11 idempotent, resumable async pipeline + DLQ · T12 diarisation + reconciliation (live ASR wins text, offline diariser wins speakers) · T13 review/edit API (human edits never overwrite the AI original) · T14 hybrid FTS + vector search · T15 consent, retention, erasure | Upload → summary → edit → search → erase |
| **2 Real-time loop (kiosk first)** | T16 framing, VAD, per-persona endpointing · T17 media_gateway (never awaits inference) · T18 agent_runtime (guardrails in code: turn cap, repeat detector, sentiment, scope) · T19 streaming TTS + barge-in + backchannel · T20 per-stage latency telemetry · T21 action_service (idempotent, approval levels) · T22 KIOSK adapter | Kiosk greeting → slots → tool → close within the latency budget |
| **3 Telephony** | T23 provider abstraction (Twilio + Exotel, bidirectional media, signature validation) · T24 outbound campaigns (answering-machine detection, number-pool rotation with a 50–80 calls/day/number cap) · T25 warm transfer, with escalation treated as an outcome | — |
| **4 Meetings** | T26 vendor-backed meeting capture · T27 calendar-triggered join with typed rejection reasons | — |
| **5 Self-service** | T28 persona builder · T29 tool registry · T30 HMAC-signed tenant webhooks · T31 judge calibration against 5% human review · T32 golden eval harness (50+ labelled recordings per domain and language) | — |

### 3.4 Latency budget (end of speech → first audio: ≤ 900 ms p50, ≤ 1.5 s p95)
| Stage | Endpoint detection | ASR flush | Routing | LLM first token | TTS first chunk | Network |
|---|---|---|---|---|---|---|
| p50 | 250 ms | 150 ms | 20 ms | 350 ms | 200 ms | 80 ms |

### 3.5 Persona (successor to today's agent config)
```yaml
persona:
  id: hospital_reception
  version: 1
  mode: RESPOND
  channels: [KIOSK, PSTN_IN]
  language: {primary: ta-IN, accepted: [ta-IN, en-IN, hi-IN], code_mixed: true, respond_in: MIRROR_USER}
  identity: {role_description, opening_utterance, disclosure}   # disclosure required unless OBSERVE
  guardrails: [...]                                              # injected AND enforced in code
  turn_taking: {trailing_silence_ms: 900, speculative_generation: false, backchannel_after_ms: 800}
  goals: [{id: identify_patient, required_slots: [name, phone, dob_or_id]}]
  schema: {fields: [{name, type, description, required, pii}]}   # valid JSON Schema
  tools: [{name: book_appointment, approval: CONFIRM_IN_CONVERSATION, idempotency: required, timeout_ms: 3000, on_failure: ESCALATE}]
  escalation: {max_turns: 20, max_duration_ms: 600000, on_sentiment_below: -0.6, on_repeat_count: 2}
  retention: {audio_days: 30, transcript_days: 365, pii_masking: ON_STORE}
```

### 3.6 Open decisions
| # | Question | Default until decided |
|---|---|---|
| O1 | Bus: Redis Streams vs NATS | Redis Streams |
| O2 | Meeting-capture vendor | Interface + stub |
| O3 | Primary ASR per language (benchmark on real 8 kHz telephony audio) | Fallback chain |
| O4 | Dialogue LLM: hosted vs self-hosted | Hosted fast tier (today: Sarvam 105B) |
| O5 | Telephony commercial terms (India + international) | Both adapters |
| O6 | ABDM / FHIR scope | Do not claim compliance |
| O7 | Per-tenant concurrency caps | Global cap |

---

## 4. Mobile app plan (`mobile/`, Flutter; scaffold only)
**Surface A, the personal recorder.** Core loop: **record → upload → read summary → correct → find again.** The recording is table stakes; the product is a summary you can trust and verify.

**Platform constraints that shape the design:**
- The app cannot record phone calls; say so during onboarding.
- iOS may kill background recording, so the UI must be gap-tolerant and honest.
- Android needs a foreground-service notification while recording.
- Meetings are captured by a *visible* bot participant.
- Processing takes minutes, so never block on it; notify instead.

**Screens:**
- **Onboarding:**
  - S01 welcome
  - S02 phone OTP sign-in
  - S03 language and code-mixing setup
  - S04 permissions primer
- **Library:**
  - S10 recordings list, whose per-row status is the key detail: recording / saved locally / uploading / queued / processing / ready / failed / no audio
  - S11 search
  - S20 session detail (summary / transcript / notes tabs plus a player). Every fact jumps to its source moment, and low-confidence fields are flagged.
  - S21–S24: edit summary (the AI original is kept), correct transcript, speaker labels, share/export
- **Meetings:** S30–S32 (calendar, visible-bot disclosure, typed join failures)
- **Settings:** S40–S44, including real "delete all my data"
- **Record:**
  - S50 consent in under 2 s
  - S51 recording with a data-driven waveform; it fails loudly, never silently
  - S52 optional live view (off by default)
  - S53 post-record

**Design rules:**
- Offline-first.
- Dark mode required.
- 48 dp touch targets.
- Recording state is never shown by colour alone.
- UI language is independent of transcription language (v1 UI: English, Hindi, Tamil).
- Undo rather than confirm, except for genuinely irreversible actions.

**Open questions:**
- Ship live mode in v1?
- Bot display name.
- Free-tier limits.
- Speaker naming in v1.

**API it needs:** the `/v1` endpoints from §3 phase 1: sessions, chunks, finalize, record/turn PATCH, search, subject erasure, and a stream WebSocket.
