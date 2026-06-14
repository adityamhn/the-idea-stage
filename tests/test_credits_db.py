"""Credit-integrity + billing tests that need a real Postgres (row locking can't be
proven on SQLite). They SKIP when DATABASE_URL is unset, so the default offline suite
stays green; run them against the Supabase Postgres to prove the anti-bypass guarantees.

Each test seeds a throwaway user (random UUID) and deletes it (cascade) on teardown.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv

load_dotenv()  # make DATABASE_URL from the repo .env visible locally; CI without it skips

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="needs a Postgres DATABASE_URL"
)


@pytest.fixture(autouse=True)
async def _fresh_engine_per_test():
    """pytest-asyncio gives each test its own event loop, but api.db caches one global
    async engine. Dispose + reset it after each test so the next one builds an engine
    bound to its own loop (otherwise pooled connections from a closed loop blow up)."""
    yield
    from api import db

    if db._engine is not None:
        await db._engine.dispose()
        db._engine = None
        db._sessionmaker = None


async def _seed_user(credits: int) -> uuid.UUID:
    from sqlalchemy import insert
    from api.db import session
    from api.models_db import User

    uid = uuid.uuid4()
    async with session() as sess:
        await sess.execute(insert(User).values(
            id=uid, email=f"test-{uid}@example.com", credits=credits,
            created_at=datetime.now(timezone.utc),
        ))
        await sess.commit()
    return uid


async def _delete_user(uid: uuid.UUID) -> None:
    from sqlalchemy import delete
    from api.db import session
    from api.models_db import User

    async with session() as sess:
        await sess.execute(delete(User).where(User.id == uid))
        await sess.commit()


async def _balance(uid: uuid.UUID) -> int:
    from api import credits
    from api.db import session

    async with session() as sess:
        return await credits.get_balance(sess, uid)


async def test_reserve_and_refund_roundtrip():
    from api import credits
    from api.db import session

    uid = await _seed_user(3)
    try:
        async with session() as sess:
            assert await credits.reserve(sess, uid, 2, "stage:x", None) is True
            await sess.commit()
        assert await _balance(uid) == 1

        async with session() as sess:
            assert await credits.reserve(sess, uid, 2, "stage:y", None) is False  # can't afford
            await sess.commit()
        assert await _balance(uid) == 1  # unchanged

        async with session() as sess:
            await credits.refund(sess, uid, 2, "refund:x", None)
            await sess.commit()
        assert await _balance(uid) == 3
    finally:
        await _delete_user(uid)


async def test_concurrent_reservations_cannot_exceed_balance():
    """The core anti-bypass proof: many runs reserving at once never overspend."""
    from api import credits
    from api.db import session

    uid = await _seed_user(2)  # only 2 credits

    async def try_reserve() -> bool:
        async with session() as sess:
            ok = await credits.reserve(sess, uid, 1, "stage:race", None)
            await sess.commit()
            return ok

    try:
        results = await asyncio.gather(*[try_reserve() for _ in range(8)])
        assert sum(results) == 2          # exactly the affordable number succeeded
        assert await _balance(uid) == 0   # never went negative
    finally:
        await _delete_user(uid)


async def test_add_credits_rejects_non_positive():
    from api import credits
    from api.db import session

    uid = await _seed_user(5)
    try:
        async with session() as sess:
            with pytest.raises(ValueError):
                await credits.add_credits(sess, uid, -1000, "evil")
        assert await _balance(uid) == 5
    finally:
        await _delete_user(uid)


async def test_ensure_user_grants_free_credits_once():
    from api import store
    from api.auth import AuthUser
    from api.credits import FREE_SIGNUP_CREDITS

    uid = uuid.uuid4()
    user = AuthUser(id=uid, email=f"test-{uid}@example.com")
    try:
        await store.ensure_user(user)
        assert await _balance(uid) == FREE_SIGNUP_CREDITS
        await store.ensure_user(user)  # second login must NOT stack
        assert await _balance(uid) == FREE_SIGNUP_CREDITS
    finally:
        await _delete_user(uid)


def _signed(payload: str, secret: str) -> str:
    # Razorpay signs the raw body with HMAC-SHA256 and sends the bare hex digest.
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def test_webhook_grants_once_and_validates_amount(monkeypatch):
    from api import billing
    from api.db import session
    from api.models_db import Payment

    secret = "whsec_test_secret"
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", secret)
    # _client() (used for signature verification) needs auth env vars; any values work
    # since verify_webhook_signature only uses the webhook secret, not the API key.
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_x")

    # Derive expected values from the live pack table so this test survives repricing.
    pack = billing.PACKS["starter"]
    pack_credits, pack_cents = pack["credits"], pack["amount_cents"]

    uid = await _seed_user(0)
    link_id = f"plink_test_{uuid.uuid4().hex}"
    async with session() as sess:
        sess.add(Payment(user_id=uid, razorpay_payment_link_id=link_id, amount_cents=pack_cents,
                         credits=pack_credits, status="pending",
                         created_at=datetime.now(timezone.utc)))
        await sess.commit()

    def event(credits_n: int) -> str:
        return json.dumps({
            "event": "payment_link.paid",
            "payload": {"payment_link": {"entity": {"id": link_id, "notes": {
                "user_id": str(uid), "credits": str(credits_n), "pack": "starter"}}}},
        })

    try:
        # A credits value that doesn't match the 'starter' pack must NOT grant.
        bad = event(pack_credits + 99999)
        await billing.handle_webhook(bad.encode(), _signed(bad, secret))
        assert await _balance(uid) == 0

        # The correct event grants exactly once, even delivered twice (idempotent).
        good = event(pack_credits)
        await billing.handle_webhook(good.encode(), _signed(good, secret))
        await billing.handle_webhook(good.encode(), _signed(good, secret))
        assert await _balance(uid) == pack_credits
    finally:
        await _delete_user(uid)
