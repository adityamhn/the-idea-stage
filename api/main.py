"""FastAPI service — Phase 2a: Supabase auth + Postgres-persisted, per-user runs.

    POST /runs                 {idea, mock?, scheduling_link?}  -> run snapshot
    POST /runs/{id}/continue                                    -> kicks next stage
    POST /runs/{id}/regenerate                                  -> re-run last stage
    GET  /runs/{id}                                             -> run snapshot
    GET  /runs/{id}/events?token=...                            -> SSE progress stream
    GET  /health

All run routes require a Supabase bearer token and are scoped to that user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env by absolute path before submodules read env.
# Shell/deployment env wins, so local verification can override ports/origins.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from . import billing, store  # noqa: E402
from .auth import AuthUser, CurrentUser, verify_token  # noqa: E402

# Emit our usage/billing logs even if the host didn't configure the root logger.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("idea_stage")

app = FastAPI(title="The Idea Stage API", version="0.2.0")

_origins = os.environ.get("IDEA_STAGE_ALLOW_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _validate_config() -> None:
    """Fail fast on a misconfigured deploy rather than 500-ing the first real request."""
    missing = [v for v in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "DATABASE_URL")
               if not (os.environ.get(v) or os.environ.get(f"NEXT_PUBLIC_{v}"))]
    if missing:
        raise RuntimeError(f"missing required env vars: {', '.join(missing)}")
    if billing.configured() and not os.environ.get("RAZORPAY_WEBHOOK_SECRET"):
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is required when Razorpay billing is configured")


class CreateRunBody(BaseModel):
    idea: str
    mock: bool = False
    scheduling_link: str = ""


class HypothesisEditBody(BaseModel):
    output: dict


class RegenerateBody(BaseModel):
    edits: str = ""


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Public gallery (no auth) + publish controls (owner only)
# --------------------------------------------------------------------------- #
@app.get("/gallery")
async def gallery() -> dict:
    return {"ideas": await store.gallery_list()}


@app.get("/gallery/{run_id}")
async def gallery_detail(run_id: str) -> dict:
    detail = await store.gallery_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="not found")
    return detail


@app.post("/runs/{run_id}/publish")
async def publish(run_id: str, user: AuthUser = CurrentUser) -> dict:
    snap = await store.set_published(run_id, user.id, True)
    if snap is None:
        raise HTTPException(status_code=404, detail="run not found")
    return snap


@app.post("/runs/{run_id}/unpublish")
async def unpublish(run_id: str, user: AuthUser = CurrentUser) -> dict:
    snap = await store.set_published(run_id, user.id, False)
    if snap is None:
        raise HTTPException(status_code=404, detail="run not found")
    return snap


@app.get("/runs")
async def list_runs(user: AuthUser = CurrentUser) -> dict:
    return {"runs": await store.list_runs(user.id)}


@app.post("/runs")
async def create_run(body: CreateRunBody, user: AuthUser = CurrentUser) -> dict:
    if not body.idea.strip():
        raise HTTPException(status_code=422, detail="idea is required")
    return await store.create_run(user, body.idea.strip(), body.mock, body.scheduling_link)


def _raise_for_start(status: str) -> None:
    """Translate begin_stage's outcome into an HTTP error (or nothing on success)."""
    if status == "insufficient":
        raise HTTPException(status_code=402, detail="insufficient_credits")
    if status == "conflict":
        raise HTTPException(status_code=409, detail="cannot continue here")


@app.post("/runs/{run_id}/continue")
async def continue_run(run_id: str, user: AuthUser = CurrentUser) -> dict:
    # begin_stage atomically validates, reserves credits (FOR UPDATE), and marks running.
    status, _ = await store.begin_stage(run_id, user.id, mode="continue")
    _raise_for_start(status)
    asyncio.create_task(store.advance(run_id))
    out = await store.get_run(run_id, user.id)
    assert out is not None
    return out


@app.post("/runs/{run_id}/regenerate")
async def regenerate(run_id: str, user: AuthUser = CurrentUser) -> dict:
    status, _ = await store.begin_stage(run_id, user.id, mode="regenerate")
    _raise_for_start(status)
    asyncio.create_task(store.advance(run_id))
    out = await store.get_run(run_id, user.id)
    assert out is not None
    return out


@app.patch("/runs/{run_id}/hypothesis")
async def edit_hypothesis(
    run_id: str, body: HypothesisEditBody, user: AuthUser = CurrentUser
) -> dict:
    snapshot = await store.save_hypothesis(run_id, user.id, body.output)
    if snapshot is None:
        raise HTTPException(status_code=409, detail="hypothesis not editable right now")
    return snapshot


@app.post("/runs/{run_id}/hypothesis/regenerate")
async def regenerate_hypothesis(
    run_id: str, body: RegenerateBody, user: AuthUser = CurrentUser
) -> dict:
    status, _ = await store.begin_stage(run_id, user.id, mode="regenerate_hypothesis")
    _raise_for_start(status)
    asyncio.create_task(store.advance(run_id, edits=body.edits))
    out = await store.get_run(run_id, user.id)
    assert out is not None
    return out


class PtMessageBody(BaseModel):
    text: str


@app.get("/runs/{run_id}/pressure-test")
async def pt_get(run_id: str, user: AuthUser = CurrentUser) -> dict:
    state = await store.pt_state(run_id, user.id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state


@app.post("/runs/{run_id}/pressure-test/start")
async def pt_start(run_id: str, user: AuthUser = CurrentUser) -> dict:
    state = await store.pt_start(run_id, user.id)
    if state is None:
        raise HTTPException(status_code=409, detail="pressure test is not available yet")
    return state


@app.post("/runs/{run_id}/pressure-test/message")
async def pt_message(run_id: str, body: PtMessageBody, user: AuthUser = CurrentUser) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="message is required")
    state = await store.pt_message(run_id, user.id, body.text.strip())
    if state is None:
        raise HTTPException(status_code=409, detail="no interview in progress")
    return state


MIN_FOUNDER_ANSWERS = 2  # a verdict shouldn't rest on a single (possibly dodged) answer


@app.post("/runs/{run_id}/pressure-test/conclude")
async def pt_conclude(run_id: str, user: AuthUser = CurrentUser) -> dict:
    state = await store.pt_state(run_id, user.id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    answers = sum(1 for m in state["messages"] if m["role"] == "user")
    if answers < MIN_FOUNDER_ANSWERS:
        raise HTTPException(
            status_code=409,
            detail=f"answer at least {MIN_FOUNDER_ANSWERS} questions before concluding",
        )
    snapshot = await store.pt_conclude(run_id, user.id)  # reserves credits atomically
    if snapshot == store.INSUFFICIENT:
        raise HTTPException(status_code=402, detail="insufficient_credits")
    if snapshot is None:
        raise HTTPException(status_code=409, detail="nothing to conclude")
    return snapshot


@app.get("/me")
async def me(user: AuthUser = CurrentUser) -> dict:
    # First authenticated call after login — provision the user row + one-time free grant.
    await store.ensure_user(user)
    return {"email": user.email, "credits": await store.balance(user.id)}


# --------------------------------------------------------------------------- #
# Billing — Razorpay credit packs
# --------------------------------------------------------------------------- #
class CheckoutBody(BaseModel):
    pack: str


def _web_origin() -> str:
    return _origins[0].strip() if _origins and _origins[0].strip() else "http://localhost:3000"


@app.get("/billing/packs")
async def billing_packs() -> dict:
    return {"configured": billing.configured(), "packs": billing.PACKS}


@app.post("/billing/checkout")
async def billing_checkout(body: CheckoutBody, user: AuthUser = CurrentUser) -> dict:
    if not billing.configured():
        raise HTTPException(status_code=503, detail="billing not configured")
    if body.pack not in billing.PACKS:
        raise HTTPException(status_code=422, detail="unknown pack")
    origin = _web_origin()
    url = await billing.create_checkout(
        user, body.pack,
        success_url=f"{origin}/?purchase=success",
    )
    return {"url": url}


@app.post("/billing/webhook")
async def billing_webhook(request: Request) -> dict:
    import razorpay

    payload = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    try:
        await billing.handle_webhook(payload, sig)
    except razorpay.errors.SignatureVerificationError:
        # A forged or misconfigured signature: reject loudly, reveal nothing.
        raise HTTPException(status_code=400, detail="invalid signature")
    except Exception:
        # A poison event (bad notes, transient DB error) must not echo internals nor
        # trigger infinite Razorpay retries — log it for manual review and ack.
        logger.exception("billing webhook processing failed")
    return {"received": True}


@app.get("/runs/{run_id}")
async def get_run(run_id: str, user: AuthUser = CurrentUser) -> dict:
    snapshot = await store.get_run(run_id, user.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run not found")
    return snapshot


@app.get("/runs/{run_id}/events")
async def events(run_id: str, token: str = ""):
    # EventSource can't set headers, so the token comes as a query param.
    user = await verify_token(token)
    snapshot = await store.get_run(run_id, user.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def gen():
        q = store.subscribe(run_id)
        try:
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            while True:
                event = await q.get()
                yield {"event": event["type"], "data": json.dumps(event)}
                if event["type"] == "done":
                    break
        finally:
            store.unsubscribe(run_id, q)

    return EventSourceResponse(gen())
