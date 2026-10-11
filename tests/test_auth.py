"""
Auth + tenancy: requests need a valid Neon Auth JWT from an email-verified
account, and users only ever see their own agents and sessions.

Tokens are signed with a throwaway Ed25519 key in place of Neon's JWKS.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.auth as auth
import backend.database as database
from backend.main import app

KEY = Ed25519PrivateKey.generate()
ISS = "https://auth.example.com"


def token(sub: str, verified: bool = True, exp_in: int = 900) -> str:
    claims = {
        "sub": sub, "email": f"{sub}@example.com", "emailVerified": verified,
        "iss": ISS, "aud": ISS, "exp": int(time.time()) + exp_in,
    }
    return jwt.encode(claims, KEY, algorithm="EdDSA")


def headers(sub: str, **kw) -> dict:
    return {"Authorization": f"Bearer {token(sub, **kw)}"}


class FakeJWKS:
    def get_signing_key_from_jwt(self, _token):
        return SimpleNamespace(key=KEY.public_key())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(auth, "_jwks", FakeJWKS())
    monkeypatch.setattr(auth, "ISSUER", ISS)
    with TestClient(app) as c:
        yield c


def test_requires_sign_in(client):
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/agents", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/agents", headers=headers("alice", exp_in=-10)).status_code == 401
    forged = jwt.encode({"sub": "alice", "emailVerified": True, "iss": "https://evil.example", "aud": ISS,
                         "exp": int(time.time()) + 900}, KEY, algorithm="EdDSA")
    assert client.get("/api/agents", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/health").status_code == 200  # public


def test_unverified_email_rejected(client):
    assert client.get("/api/agents", headers=headers("mallory", verified=False)).status_code == 403
    assert client.get("/api/agents", headers=headers("alice")).status_code == 200


def test_users_are_isolated(client):
    alice, bob = headers("alice"), headers("bob")
    agent_id = client.post("/api/agents", json={"name": "Desk", "domain": "Hotel"}, headers=alice).json()["agent"]["id"]

    assert [a["id"] for a in client.get("/api/agents", headers=alice).json()["agents"]] == [agent_id]
    assert client.get("/api/agents", headers=bob).json()["agents"] == []
    assert client.get(f"/api/agents/{agent_id}", headers=bob).status_code == 404
    assert client.put(f"/api/agents/{agent_id}", json={"name": "x"}, headers=bob).status_code == 404
    assert client.delete(f"/api/agents/{agent_id}", headers=bob).status_code == 404
    assert client.post("/api/sessions", json={"agent_id": agent_id}, headers=bob).status_code == 404
    assert client.get(f"/api/agents/{agent_id}", headers=alice).status_code == 200


def test_websocket_rejects_missing_token(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/live/stream") as ws:
            ws.receive_text()
