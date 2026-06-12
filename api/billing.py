"""Razorpay credit packs.

A Payment Link per purchase (no dashboard product setup) — needs RAZORPAY_KEY_ID +
RAZORPAY_KEY_SECRET (+ RAZORPAY_WEBHOOK_SECRET for the webhook). Credits are granted on
the `payment_link.paid` webhook, idempotently keyed by the Razorpay payment-link id.
If keys are absent, the endpoints report "not configured" rather than crashing.

Pricing is in USD: charging USD on Razorpay requires International Payments enabled +
activated on the account, otherwise live checkout fails.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .auth import AuthUser
from .credits import add_credits
from .db import session
from .models_db import Payment

logger = logging.getLogger("idea_stage.billing")

# Credit packs (USD). Priced at ~4x the underlying compute cost: a full 15-credit
# validation costs us ~$3.74, so the price/credit below ($0.85–$1.25, cheaper in
# bulk) yields a ~3.4x–5x margin per journey. Razorpay is charged amount_cents (paise).
PACKS: dict[str, dict] = {
    "starter": {"credits": 20, "amount_cents": 2500, "name": "Starter — 20 credits"},
    "growth": {"credits": 60, "amount_cents": 5900, "name": "Growth — 60 credits"},
    "scale": {"credits": 200, "amount_cents": 16900, "name": "Scale — 200 credits"},
}


def configured() -> bool:
    return bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))


def _client():
    import razorpay

    return razorpay.Client(
        auth=(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_checkout(user: AuthUser, pack_id: str, success_url: str) -> str:
    pack = PACKS[pack_id]
    data = {
        "amount": pack["amount_cents"],
        "currency": "USD",
        "accept_partial": False,
        "description": pack["name"],
        "reference_id": uuid.uuid4().hex,  # Razorpay requires this unique per link
        "notify": {"email": False, "sms": False},  # we redirect; don't let Razorpay message
        "reminder_enable": False,
        "callback_url": success_url,
        "callback_method": "get",
        "notes": {"user_id": str(user.id), "credits": str(pack["credits"]), "pack": pack_id},
    }
    if user.email:
        data["customer"] = {"email": user.email}
    link = _client().payment_link.create(data)
    async with session() as db:
        db.add(Payment(user_id=user.id, razorpay_payment_link_id=link["id"],
                       amount_cents=pack["amount_cents"], credits=pack["credits"],
                       status="pending", created_at=_now()))
        await db.commit()
    return link["short_url"]


async def handle_webhook(payload: bytes, sig_header: str) -> None:
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        # Without the secret we cannot verify the signature — refuse to grant anything.
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is not configured")
    # Verifies HMAC-SHA256 of the raw body; raises SignatureVerificationError on mismatch.
    _client().utility.verify_webhook_signature(payload.decode(), sig_header, secret)
    event = json.loads(payload)
    if event.get("event") != "payment_link.paid":
        return
    entity = event["payload"]["payment_link"]["entity"]
    link_id = entity["id"]
    notes = entity.get("notes") or {}

    # Validate the grant against our own pack table — never trust the amount blindly, and
    # treat a malformed event as handled (log + return) so Razorpay stops retrying it.
    pack_id = notes.get("pack", "")
    pack = PACKS.get(pack_id)
    try:
        user_id = uuid.UUID(notes["user_id"])
        credits_n = int(notes["credits"])
    except (KeyError, ValueError, TypeError):
        logger.error("webhook %s has unparseable notes: %r", link_id, notes)
        return
    if pack is None or pack["credits"] != credits_n:
        logger.error("webhook %s credits/pack mismatch: pack=%r credits=%r", link_id, pack_id, credits_n)
        return

    async with session() as db:
        # Lock the payment row so two concurrent deliveries of the same link can't
        # both pass the idempotency check and double-grant credits.
        pay = (
            await db.execute(
                select(Payment)
                .where(Payment.razorpay_payment_link_id == link_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if pay is not None and pay.status == "paid":
            return  # already processed — idempotent
        await add_credits(db, user_id, credits_n, "purchase")
        if pay is not None:
            pay.status = "paid"
        await db.commit()
