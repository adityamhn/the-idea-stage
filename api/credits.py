"""Credits: a free grant on first login, then per-stage charging.

Balance lives on ``users.credits`` (fast checks); every change is mirrored to
``credit_ledger`` for audit. Credits are **reserved up front** under a row lock the
moment a stage is allowed to start, and **refunded** if that stage fails — so a
failed stage never costs the founder, and concurrent runs can't drive the balance
negative (the ``SELECT ... FOR UPDATE`` serialises a user's reservations).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .models_db import CreditLedger, User

# Per-stage credit cost, weighted to track real model spend so a credit means
# roughly the same dollar amount at every stage (measured cost in parens, Opus
# pricing): hypothesis $0.54, pressure_test $0.63, market $1.74, discovery $0.27,
# outreach $0.39, solution $0.16. A full validation is 2+3+6+1+2+1 = 15 credits.
# Credits are sold at ~4x cost (see api/billing.PACKS), so a full journey nets a
# healthy margin over its ~$3.74 compute cost.
STAGE_COST: dict[str, int] = {
    "hypothesis": 2,
    "pressure_test": 3,  # multi-turn interview + synthesis; cost grows with turns
    "market": 6,  # heaviest — three web-searching analysts + synthesis
    "discovery": 1,
    "outreach": 2,
    "solution": 1,
}

# New accounts get a one-time taster. Stages run in order, so 3 credits buys the
# hypothesis (2) — the first cited problem statement + Coach review — and strands
# one credit toward a later top-up. Kept small to bound free-tier API exposure
# (a fully-used free grant costs us ~$0.54) on a high-traffic launch.
FREE_SIGNUP_CREDITS = 3


def stage_cost(stage_key: str) -> int:
    return STAGE_COST.get(stage_key, 1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_balance(sess, user_id: uuid.UUID) -> int:
    u = (await sess.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    return u.credits if u else 0


async def reserve(sess, user_id: uuid.UUID, amount: int, reason: str, run_id: str | None) -> bool:
    """Atomically deduct ``amount`` credits if available, recording the ledger row.

    Takes a row lock on the user (``FOR UPDATE``) so concurrent reservations across a
    user's runs are serialised — this is what makes the credit limit un-bypassable.
    Returns False (no change) if the balance is insufficient. The caller owns the commit.
    """
    if amount <= 0:
        raise ValueError(f"reserve amount must be positive, got {amount}")
    u = (
        await sess.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if u is None or u.credits < amount:
        return False
    u.credits -= amount
    sess.add(CreditLedger(user_id=user_id, delta=-amount, reason=reason, run_id=run_id,
                          balance_after=u.credits, created_at=_now()))
    return True


async def refund(sess, user_id: uuid.UUID, amount: int, reason: str, run_id: str | None) -> int:
    """Return previously-reserved credits after a stage fails. Locks the user row so the
    refund can't race a concurrent reservation. The caller owns the commit."""
    if amount <= 0:
        raise ValueError(f"refund amount must be positive, got {amount}")
    u = (
        await sess.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()
    u.credits += amount
    sess.add(CreditLedger(user_id=user_id, delta=amount, reason=reason, run_id=run_id,
                          balance_after=u.credits, created_at=_now()))
    return u.credits


async def add_credits(sess, user_id: uuid.UUID, amount: int, reason: str) -> int:
    """Grant credits (a purchase). Positive amounts only — a negative grant would be a
    silent debit and must never slip in through, e.g., a malformed webhook."""
    if amount <= 0:
        raise ValueError(f"add_credits amount must be positive, got {amount}")
    u = (
        await sess.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()
    u.credits += amount
    sess.add(CreditLedger(user_id=user_id, delta=amount, reason=reason, run_id=None,
                          balance_after=u.credits, created_at=_now()))
    return u.credits
