"""Supabase auth — verify a user's access token.

We validate the bearer token by calling Supabase's `/auth/v1/user` endpoint. This
is robust regardless of the project's JWT signing config (symmetric or asymmetric)
and needs no shared secret — only the public anon/publishable key as the `apikey`.
Results are cached briefly to keep per-request overhead low.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException

def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")


def _anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY") or os.environ.get(
        "NEXT_PUBLIC_SUPABASE_ANON_KEY", ""
    )


_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, "AuthUser"]] = {}


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    email: str | None


async def verify_token(token: str) -> AuthUser:
    if not token:
        raise HTTPException(status_code=401, detail="missing access token")
    url, anon = _supabase_url(), _anon_key()
    if not url or not anon:
        raise HTTPException(status_code=500, detail="Supabase env not configured on the API")

    now = time.monotonic()
    hit = _cache.get(token)
    if hit and hit[0] > now:
        return hit[1]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": anon},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    data = resp.json()
    user = AuthUser(id=uuid.UUID(data["id"]), email=data.get("email"))
    _cache[token] = (now + _CACHE_TTL, user)
    return user


async def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """FastAPI dependency: extract and verify the bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return await verify_token(authorization[7:].strip())


CurrentUser = Depends(current_user)
