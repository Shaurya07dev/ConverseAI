"""
Offline smoke test: agent CRUD + a full text session (start → message → end)
against a temp SQLite DB, with the LLM and TTS replaced by fakes.

Run: python -m pytest -q
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_core.dialogue_agent as agent_mod
import ai_core.reward_engine as reward_mod
import ai_core.field_extractor as extractor_mod
import backend.database as database
import backend.routes.sessions as routes_sessions
from ai_core.llm import strip_reasoning
from backend.main import app


class FakeChatModel:
    """Stands in for the LangChain chat model; answers like a reasoning model."""

    def invoke(self, messages):
        prompt = messages[-1].content
        if "data extraction engine" in prompt:
            return SimpleNamespace(content='<think>scan</think>```json\n{"symptoms": "fever"}\n```')
        return SimpleNamespace(content="<think>plan</think>How long have you had the fever?")


class FakeJudgeClient:
    """Stands in for openai.AsyncOpenAI."""

    def __init__(self):
        async def create(**kwargs):
            content = (
                '<think>x</think>{"politeness": 5, "accuracy": 4, "indic_fluency": 4,'
                ' "policy_compliance": 5, "resolution_quality": 3, "feedback": "ok"}'
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


class NoTTS:
    async def synthesise_b64(self, *args, **kwargs):
        return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(agent_mod, "chat_model", lambda **kw: FakeChatModel())
    monkeypatch.setattr(extractor_mod, "chat_model", lambda **kw: FakeChatModel())
    monkeypatch.setattr(reward_mod, "chat_client", lambda: FakeJudgeClient())
    # Fresh lazy singletons so the fakes are picked up
    monkeypatch.setattr(routes_sessions, "_dialogue_agent", None)
    monkeypatch.setattr(routes_sessions, "_reward_engine", None)
    monkeypatch.setattr(routes_sessions, "_tts_pipeline", NoTTS())
    with TestClient(app) as c:
        yield c


def test_strip_reasoning():
    assert strip_reasoning("<think>a\nb</think> hi ") == "hi"
    assert strip_reasoning(None) == ""


def test_health(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_agent_crud(client):
    created = client.post("/api/agents", json={"name": "Asha", "domain": "healthcare", "fields": ["symptoms"]})
    assert created.status_code == 200
    agent_id = created.json()["agent"]["id"]

    assert any(a["id"] == agent_id for a in client.get("/api/agents").json()["agents"])
    updated = client.put(f"/api/agents/{agent_id}", json={"name": "Asha 2"})
    assert updated.json()["agent"]["name"] == "Asha 2"
    assert client.delete(f"/api/agents/{agent_id}").status_code == 200
    assert client.get(f"/api/agents/{agent_id}").status_code == 404


def test_text_session_flow(client):
    agent_id = client.post(
        "/api/agents", json={"name": "Asha", "domain": "healthcare", "fields": ["symptoms", "duration"]}
    ).json()["agent"]["id"]

    started = client.post("/api/sessions", json={"agent_id": agent_id})
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    reply = client.post(f"/api/sessions/{session_id}/message", json={"content": "Mujhe bukhar hai"}).json()
    assert reply["response"] == "How long have you had the fever?"
    assert reply["collected_fields"].get("symptoms") == "fever"

    ended = client.post(f"/api/sessions/{session_id}/end").json()
    scores = ended["reward_scores"]
    assert "error" not in scores, scores
    assert scores["llm_judge"]["politeness"] == 5
