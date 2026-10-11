"""
VaakSetu Backend — request authentication

Verifies Neon Auth (managed Better Auth) JWTs sent as `Authorization: Bearer <jwt>`
(or `?token=<jwt>` on WebSockets) and returns the caller's user id.

With NEON_AUTH_JWKS_URL unset (local dev, tests) auth is off and every request
acts as the single user "local".
"""

import os
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request, WebSocket

JWKS_URL = os.getenv("NEON_AUTH_JWKS_URL", "")
LOCAL_USER = "local"

_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True) if JWKS_URL else None
# Neon sets both iss and aud to the auth server's origin
ISSUER = "{0.scheme}://{0.netloc}".format(urlsplit(JWKS_URL)) if JWKS_URL else None


def verify_token(token: str) -> str:
    """Return the user id of a valid token from an email-verified account."""
    try:
        signing_key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["EdDSA"], issuer=ISSUER, audience=ISSUER)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session — sign in again")
    # Unverified accounts get no access, even if the auth server let them sign in
    if not claims.get("emailVerified"):
        raise HTTPException(status_code=403, detail="Verify your email address first")
    if claims.get("banned"):
        raise HTTPException(status_code=403, detail="This account is suspended")
    return claims["sub"]


async def current_user(request: Request) -> str:
    """FastAPI dependency: the signed-in user's id."""
    if _jwks is None:
        return LOCAL_USER
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return verify_token(header[7:])


def websocket_user(websocket: WebSocket) -> str | None:
    """User id for a WebSocket (token in the query string), or None if rejected."""
    if _jwks is None:
        return LOCAL_USER
    try:
        return verify_token(websocket.query_params.get("token", ""))
    except HTTPException:
        return None


def owned(resource: dict | None, user: str, kind: str) -> dict:
    """Return the resource if the user owns it; 404 otherwise (don't reveal it exists)."""
    if resource is None or resource.get("owner_id") != user:
        raise HTTPException(status_code=404, detail=f"{kind} not found")
    return resource
