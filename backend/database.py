"""
VaakSetu Backend — Database Layer

Postgres (asyncpg) when DATABASE_URL is set — production on Neon.
SQLite (aiosqlite, ./vaaksetu.db) otherwise — local dev and tests.
The same SQL runs on both; `?` placeholders are rewritten for Postgres.

Tables:
  • agents    — agent configurations built in the UI (owned by a user)
  • sessions  — conversation sessions tied to agents (owned by a user)
  • messages  — individual messages in each session
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosqlite

logger = logging.getLogger("vaaksetu.database")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "vaaksetu.db"
DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool = None  # asyncpg pool when running on Postgres


def _schema(pg: bool) -> list[str]:
    id_col = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        """CREATE TABLE IF NOT EXISTS agents (
            id              TEXT PRIMARY KEY,
            owner_id        TEXT NOT NULL DEFAULT 'local',
            name            TEXT NOT NULL,
            domain          TEXT NOT NULL,
            custom_domain   TEXT DEFAULT '',
            inputs          TEXT DEFAULT '["Voice"]',
            fields          TEXT DEFAULT '[]',
            system_prompt   TEXT DEFAULT '',
            greeting        TEXT DEFAULT '',
            triggers        TEXT DEFAULT '[]',
            escalation      TEXT DEFAULT '{}',
            escalation_message TEXT DEFAULT '',
            default_language TEXT DEFAULT 'hi-IN',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            owner_id        TEXT NOT NULL DEFAULT 'local',
            agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            status          TEXT DEFAULT 'active',
            collected_fields TEXT DEFAULT '{}',
            is_complete     INTEGER DEFAULT 0,
            turn_count      INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL,
            ended_at        TEXT,
            reward_scores   TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS messages (
            id              {id_col},
            session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            turn_number     INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id)",
    ]


# Columns added after the first release; ALTER fails harmlessly when already present.
_MIGRATIONS = [
    "ALTER TABLE agents ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'",
    "ALTER TABLE sessions ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'",
]
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions(owner_id)",
]


def _pg_sql(sql: str) -> str:
    """Rewrite SQLite `?` placeholders to Postgres `$1, $2, …`."""
    counter = iter(range(1, 10_000))
    return re.sub(r"\?", lambda _: f"${next(counter)}", sql)


def _pg_dsn(url: str) -> str:
    # asyncpg doesn't understand libpq's channel_binding parameter
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "channel_binding"])
    return urlunsplit(parts._replace(query=query))


async def _fetch(sql: str, params: tuple = ()) -> list[dict]:
    """Run a statement and return its rows as dicts (also for INSERT … RETURNING)."""
    if _pool is not None:
        async with _pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch(_pg_sql(sql), *params)]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(sql, params)
        rows = [dict(r) for r in await cursor.fetchall()]
        await db.commit()
        return rows


async def _execute(sql: str, params: tuple = ()) -> int:
    """Run a statement and return the number of affected rows."""
    if _pool is not None:
        async with _pool.acquire() as conn:
            status = await conn.execute(_pg_sql(sql), *params)  # e.g. "DELETE 1"
            return int(status.split()[-1]) if status.split()[-1].isdigit() else 0
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount


async def init_db():
    """Connect (Postgres) and create/upgrade the schema."""
    global _pool
    pg = bool(DATABASE_URL)
    if pg and _pool is None:
        import asyncpg

        # Neon suspends idle compute after ~5 min; drop idle connections before that
        _pool = await asyncpg.create_pool(
            _pg_dsn(DATABASE_URL), min_size=1, max_size=5, max_inactive_connection_lifetime=60
        )
    if not pg:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("PRAGMA journal_mode=WAL")

    for stmt in _schema(pg):
        await _execute(stmt)
    for stmt in _MIGRATIONS:
        try:
            await _execute(stmt)
        except Exception:
            pass  # column already exists
    for stmt in _INDEXES:
        await _execute(stmt)
    logger.info(f"Database initialized ({'Postgres' if pg else f'SQLite at {DB_PATH}'})")


async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _agent_values(agent_data: dict) -> tuple:
    return (
        agent_data["name"],
        agent_data["domain"],
        agent_data.get("customDomain", ""),
        json.dumps(agent_data.get("inputs", ["Voice"])),
        json.dumps(agent_data.get("fields", [])),
        agent_data.get("prompt", ""),
        agent_data.get("greeting", ""),
        json.dumps(agent_data.get("triggers", [])),
        json.dumps(agent_data.get("escalation", {})),
        agent_data.get("escalation_message", ""),
        agent_data.get("default_language", "hi-IN"),
    )


async def create_agent(agent_data: dict) -> dict:
    """Insert a new agent. agent_data must include id and owner_id."""
    now = _now()
    await _execute(
        """INSERT INTO agents (name, domain, custom_domain, inputs, fields,
           system_prompt, greeting, triggers, escalation, escalation_message,
           default_language, id, owner_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _agent_values(agent_data) + (agent_data["id"], agent_data["owner_id"], now, now),
    )
    return await get_agent(agent_data["id"])


async def get_agent(agent_id: str) -> dict | None:
    """Fetch a single agent by ID (no ownership check — callers do that)."""
    rows = await _fetch("SELECT * FROM agents WHERE id = ?", (agent_id,))
    return _row_to_agent(rows[0]) if rows else None


async def list_agents(owner_id: str) -> list[dict]:
    """List a user's agents, newest first."""
    rows = await _fetch(
        "SELECT * FROM agents WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
    )
    return [_row_to_agent(r) for r in rows]


async def update_agent(agent_id: str, agent_data: dict) -> dict | None:
    """Update an existing agent."""
    await _execute(
        """UPDATE agents SET name=?, domain=?, custom_domain=?, inputs=?, fields=?,
           system_prompt=?, greeting=?, triggers=?, escalation=?, escalation_message=?,
           default_language=?, updated_at=?
           WHERE id=?""",
        _agent_values(agent_data) + (_now(), agent_id),
    )
    return await get_agent(agent_id)


async def delete_agent(agent_id: str) -> bool:
    """Delete an agent and its sessions/messages."""
    return await _execute("DELETE FROM agents WHERE id = ?", (agent_id,)) > 0


def _row_to_agent(row: dict) -> dict:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "name": row["name"],
        "domain": row["domain"],
        "customDomain": row["custom_domain"],
        "inputs": json.loads(row["inputs"]),
        "fields": json.loads(row["fields"]),
        "prompt": row["system_prompt"],
        "greeting": row["greeting"],
        "triggers": json.loads(row["triggers"]),
        "escalation": json.loads(row["escalation"]),
        "escalation_message": row["escalation_message"],
        "default_language": row["default_language"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Session CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def create_session(session_id: str, agent_id: str, owner_id: str) -> dict:
    """Create a new conversation session."""
    await _execute(
        """INSERT INTO sessions (id, owner_id, agent_id, status, collected_fields,
           is_complete, turn_count, created_at)
           VALUES (?, ?, ?, 'active', '{}', 0, 0, ?)""",
        (session_id, owner_id, agent_id, _now()),
    )
    return await get_session(session_id)


async def get_session(session_id: str) -> dict | None:
    """Fetch a session by ID (no ownership check — callers do that)."""
    rows = await _fetch("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return _row_to_session(rows[0]) if rows else None


_SESSION_COLUMNS = {"collected_fields", "is_complete", "turn_count", "status", "ended_at", "reward_scores"}


async def update_session(session_id: str, **kwargs) -> dict | None:
    """Update the given session columns."""
    sets, values = [], []
    for key, val in kwargs.items():
        if key not in _SESSION_COLUMNS:
            continue
        if key in ("collected_fields", "reward_scores"):
            val = json.dumps(val)
        elif key == "is_complete":
            val = 1 if val else 0
        sets.append(f"{key} = ?")
        values.append(val)

    if sets:
        await _execute(
            f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?",
            tuple(values) + (session_id,),
        )
    return await get_session(session_id)


async def list_sessions(owner_id: str) -> list[dict]:
    """List a user's sessions, newest first."""
    rows = await _fetch(
        "SELECT * FROM sessions WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
    )
    return [_row_to_session(r) for r in rows]


async def delete_session(session_id: str) -> bool:
    """Delete a session and all of its messages."""
    return await _execute("DELETE FROM sessions WHERE id = ?", (session_id,)) > 0


def _row_to_session(row: dict) -> dict:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "agent_id": row["agent_id"],
        "status": row["status"],
        "collected_fields": json.loads(row["collected_fields"]),
        "is_complete": bool(row["is_complete"]),
        "turn_count": row["turn_count"],
        "created_at": row["created_at"],
        "ended_at": row["ended_at"],
        "reward_scores": json.loads(row["reward_scores"]) if row["reward_scores"] else None,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Message CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def add_message(session_id: str, role: str, content: str, turn_number: int) -> dict:
    """Add a message to a session."""
    now = _now()
    rows = await _fetch(
        """INSERT INTO messages (session_id, role, content, turn_number, created_at)
           VALUES (?, ?, ?, ?, ?) RETURNING id""",
        (session_id, role, content, turn_number, now),
    )
    return {
        "id": rows[0]["id"],
        "session_id": session_id,
        "role": role,
        "content": content,
        "turn_number": turn_number,
        "created_at": now,
    }


async def get_messages(session_id: str) -> list[dict]:
    """Get all messages for a session ordered by turn number."""
    return await _fetch(
        """SELECT id, session_id, role, content, turn_number, created_at
           FROM messages WHERE session_id = ? ORDER BY turn_number ASC, id ASC""",
        (session_id,),
    )
