"""Run persistence + per-run runtime.

Persisted truth lives in Postgres (``runs`` + ``stage_results``). Per-run runtime
state that doesn't belong in the DB — an advance lock and the live SSE subscribers
— is held in memory keyed by run id (single API process in Phase 2a). The snapshot
returned to the frontend is always rebuilt from the database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from engine import pressure_test
from engine.coach import review_stage
from engine.conductor import (
    INTERACTIVE_STAGES,
    STAGE_ORDER,
    STAGE_TITLES,
    first_stage,
    next_stage,
    rebuild_output,
    run_stage,
)
from engine.config import EngineConfig, Usage
from engine.pricing import cost_usd

from . import credits
from .auth import AuthUser
from .credits import FREE_SIGNUP_CREDITS, stage_cost
from .db import session
from .models_db import PressureTestMessage, RunRow, StageResultRow, User

logger = logging.getLogger("idea_stage.usage")

# Token fields summed for a per-idea rollup (everything in Usage.to_dict except cost).
_USAGE_FIELDS = (
    "input_tokens", "output_tokens", "cache_creation_input_tokens",
    "cache_read_input_tokens", "web_searches", "calls",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_stage_usage(run_id: str, user_id: uuid.UUID, stage_key: str, usage: dict) -> None:
    logger.info(
        "stage_usage run=%s user=%s stage=%s in=%d out=%d cache_read=%d web=%d calls=%d cost_usd=%.4f",
        run_id, user_id, stage_key,
        usage.get("input_tokens", 0), usage.get("output_tokens", 0),
        usage.get("cache_read_input_tokens", 0), usage.get("web_searches", 0),
        usage.get("calls", 0), usage.get("cost_usd", 0.0),
    )


def _mint_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# In-memory runtime (locks + SSE subscribers), keyed by run id
# --------------------------------------------------------------------------- #
@dataclass
class _Runtime:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subscribers: list[asyncio.Queue] = field(default_factory=list)


_RUNTIME: dict[str, _Runtime] = {}


def _runtime(run_id: str) -> _Runtime:
    rt = _RUNTIME.get(run_id)
    if rt is None:
        rt = _Runtime()
        _RUNTIME[run_id] = rt
    return rt


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _runtime(run_id).subscribers.append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    subs = _runtime(run_id).subscribers
    if q in subs:
        subs.remove(q)


async def _emit(run_id: str, event: dict) -> None:
    for q in list(_runtime(run_id).subscribers):
        await q.put(event)


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def _totals(stages: list[StageResultRow]) -> dict:
    """Per-idea rollup of token spend + dollar cost across every completed stage.
    Includes ``cost_usd`` — used for internal logging; stripped from user-facing payloads."""
    out: dict[str, float] = {f: 0 for f in _USAGE_FIELDS}
    out["cost_usd"] = 0.0
    for s in stages:
        u = s.usage or {}
        for f in _USAGE_FIELDS:
            out[f] += u.get(f, 0)
        out["cost_usd"] += u.get("cost_usd", 0.0)
    out["cost_usd"] = round(out["cost_usd"], 6)
    return out


def _public_usage(u: dict | None) -> dict:
    """A usage dict with the dollar cost removed. Token counts are fine to show the
    founder; raw model cost is internal pricing intel and stays in the DB + logs only."""
    return {k: v for k, v in (u or {}).items() if k != "cost_usd"}


def _snapshot(run: RunRow) -> dict:
    completed = [s.stage_key for s in run.stages]
    nxt = first_stage() if not completed else next_stage(completed[-1])
    running_stage = nxt if run.status == "running" else None
    return {
        "id": run.id,
        "idea": run.idea,
        "mock": run.mock,
        "status": run.status,
        "running_stage": running_stage,
        "error": run.error,
        "published": run.published,
        "stage_order": list(STAGE_ORDER),
        "completed_stages": completed,
        "next_stage": nxt,
        "totals": _public_usage(_totals(run.stages)),
        "results": [
            {
                "stage_key": s.stage_key,
                "title": STAGE_TITLES[s.stage_key],
                "output": s.output,
                "review": s.review,
                "usage": _public_usage(s.usage),
            }
            for s in run.stages
        ],
    }


async def _load(sess, run_id: str) -> RunRow | None:
    return (
        await sess.execute(
            select(RunRow).where(RunRow.id == run_id).options(selectinload(RunRow.stages))
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Public operations
# --------------------------------------------------------------------------- #
async def ensure_user(user: AuthUser) -> None:
    """Create the user row with the one-time free credit grant if it doesn't exist yet.

    Idempotent: ``on_conflict_do_nothing`` means the grant lands exactly once per
    account, no matter how many times this is called. Invoked at first login (``/me``)
    and as a safety net before a run's first write, so the free credits don't depend on
    which endpoint the user happens to hit first.
    """
    async with session() as sess:
        await sess.execute(
            pg_insert(User)
            .values(id=user.id, email=user.email, credits=FREE_SIGNUP_CREDITS, created_at=_now())
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        await sess.commit()


async def create_run(user: AuthUser, idea: str, mock: bool, scheduling_link: str) -> dict:
    await ensure_user(user)
    async with session() as sess:
        run = RunRow(
            id=_mint_id(),
            user_id=user.id,
            idea=idea,
            mock=mock,
            scheduling_link=scheduling_link,
            status="idle",
            created_at=_now(),
            updated_at=_now(),
        )
        sess.add(run)
        await sess.commit()
        await sess.refresh(run, attribute_names=["stages"])
        return _snapshot(run)


async def list_runs(user_id: uuid.UUID, limit: int = 100) -> list[dict]:
    """The user's own runs, newest activity first — for the 'My ideas' dashboard."""
    async with session() as sess:
        runs = (
            await sess.execute(
                select(RunRow)
                .where(RunRow.user_id == user_id)
                .order_by(RunRow.updated_at.desc())
                .limit(limit)
                .options(selectinload(RunRow.stages))
            )
        ).scalars()
        out: list[dict] = []
        for r in runs:
            completed = [s.stage_key for s in r.stages]
            nxt = first_stage() if not completed else next_stage(completed[-1])
            out.append(
                {
                    "id": r.id,
                    "idea": r.idea,
                    "status": r.status,
                    "completed_stages": completed,
                    "next_stage": nxt,
                    "total_stages": len(STAGE_ORDER),
                    "published": r.published,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            )
        return out


async def get_run(run_id: str, user_id: uuid.UUID) -> dict | None:
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or run.user_id != user_id:
            return None
        return _snapshot(run)


def _stale_running(run_id: str) -> bool:
    """A run whose DB status is 'running' but with no in-flight ``advance`` task in this
    process — e.g. the API restarted mid-stage and lost the in-memory lock, leaving the
    DB stuck. Such a run is safe to re-kick; a genuinely in-flight one holds the lock."""
    return not _runtime(run_id).lock.locked()


# (status, stage) — status is "ok" | "insufficient" | "conflict".
StartResult = tuple[str, str | None]


async def begin_stage(
    run_id: str, user_id: uuid.UUID, *, mode: str = "continue"
) -> StartResult:
    """Atomically: validate the next stage is runnable, RESERVE its credits under a user
    row lock, mark the run running — all in one transaction — then return the stage that
    ``advance`` will run. Reserving here (not charging after the stage) is what closes the
    credit-bypass race: a user firing many runs at once can't pass more reservations than
    their balance, because ``credits.reserve`` serialises on ``SELECT ... FOR UPDATE``.

    ``mode``: 'continue' runs the next stage; 'regenerate' drops + re-runs the last
    stage; 'regenerate_hypothesis' drops + re-runs the hypothesis (with founder edits
    applied by ``advance``). The reserved amount always equals what ``advance`` will run,
    so a failure refund is unambiguous.
    """
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or run.user_id != user_id:
            return ("conflict", None)
        if run.status == "running" and not _stale_running(run_id):
            return ("conflict", None)  # a real advance task is in flight
        completed = [s.stage_key for s in run.stages]

        if mode == "continue":
            stage_key = first_stage() if not completed else next_stage(completed[-1])
            drop = False
        elif mode == "regenerate":
            stage_key = completed[-1] if completed else None
            drop = True
        elif mode == "regenerate_hypothesis":
            stage_key = "hypothesis" if completed[-1:] == ["hypothesis"] else None
            drop = True
        else:
            return ("conflict", None)

        if stage_key is None or stage_key in INTERACTIVE_STAGES:
            return ("conflict", None)  # nothing to run / interactive stages own their flow

        if not await credits.reserve(
            sess, user_id, stage_cost(stage_key), f"stage:{stage_key}", run_id
        ):
            return ("insufficient", None)

        if drop:
            await sess.delete(run.stages[-1])
        run.status = "running"
        run.error = None
        run.updated_at = _now()
        await sess.commit()
        return ("ok", stage_key)


async def save_hypothesis(run_id: str, user_id: uuid.UUID, output: dict) -> dict | None:
    """Persist founder edits to the hypothesis output (no model call). Validates the
    payload is a well-formed Hypothesis. Only allowed while hypothesis is the last
    completed stage (editing after downstream stages ran would desync the chain)."""
    from engine.models import Hypothesis

    clean = Hypothesis.model_validate(output).model_dump(mode="json")
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or run.user_id != user_id or not run.stages:
            return None
        if run.stages[-1].stage_key != "hypothesis":
            return None
        run.stages[-1].output = clean
        run.updated_at = _now()
        await sess.commit()
        await sess.refresh(run, attribute_names=["stages"])
        return _snapshot(run)


async def advance(run_id: str, *, edits: str = "") -> None:
    """Background task: run the next stage + Coach, persist it, emit SSE events.

    Assumes the run was already marked 'running' AND its credits reserved by the
    caller (``begin_stage``). Serialised per run by the runtime lock. ``edits`` is
    founder guidance applied when the next stage is the hypothesis (regenerate-with-
    edits). On failure the reserved credits are refunded — a failed stage is free.
    """
    rt = _runtime(run_id)
    async with rt.lock:
        async with session() as sess:
            run = await _load(sess, run_id)
            if run is None:
                return
            completed = [s.stage_key for s in run.stages]
            stage_key = first_stage() if not completed else next_stage(completed[-1])
            if stage_key is None:
                run.status = "done"
                await sess.commit()
                await _emit(run_id, {"type": "done"})
                return

            prior: object = run.idea if not completed else rebuild_output(
                run.stages[-1].stage_key, run.stages[-1].output
            )
            mock, link, seq = run.mock, run.scheduling_link, len(completed)

        await _emit(run_id, {"type": "stage_start", "stage": stage_key})
        try:
            result = await run_stage(
                stage_key, prior, EngineConfig(mock=mock), scheduling_link=link, edits=edits
            )
        except Exception as exc:  # surface the failure, don't hide it
            message = f"{type(exc).__name__}: {exc}"
            async with session() as sess:
                run = await _load(sess, run_id)
                if run is not None:
                    # Refund the credits reserved for this stage — a failed stage is free.
                    await credits.refund(sess, run.user_id, stage_cost(stage_key),
                                         f"refund:{stage_key}", run_id)
                    run.status = "error"
                    run.error = message
                    run.updated_at = _now()
                    await sess.commit()
            await _emit(run_id, {"type": "error", "stage": stage_key, "message": message})
            return

        usage_dict = result.usage_dict()  # tokens + computed cost_usd
        async with session() as sess:
            run = await _load(sess, run_id)
            if run is None:
                return
            # Credits were already reserved in begin_stage; nothing to charge here.
            sess.add(
                StageResultRow(
                    run_id=run_id,
                    stage_key=stage_key,
                    seq=seq,
                    output=result.output.model_dump(mode="json"),
                    review=result.review.model_dump(mode="json"),
                    usage=usage_dict,
                    created_at=_now(),
                )
            )
            done = next_stage(stage_key) is None
            run.status = "done" if done else "idle"
            run.updated_at = _now()
            await sess.commit()
            await sess.refresh(run, attribute_names=["stages"])
            user_id, totals = run.user_id, _totals(run.stages)
            payload = {
                "stage_key": stage_key,
                "title": STAGE_TITLES[stage_key],
                "output": result.output.model_dump(mode="json"),
                "review": result.review.model_dump(mode="json"),
                "usage": _public_usage(usage_dict),
            }

    _log_stage_usage(run_id, user_id, stage_key, usage_dict)
    if done:
        logger.info("idea_total run=%s user=%s total_tokens=%d total_cost_usd=%.4f",
                    run_id, user_id,
                    totals["input_tokens"] + totals["output_tokens"], totals["cost_usd"])
    await _emit(run_id, {"type": "stage_complete", "stage": stage_key, "result": payload})
    if done:
        await _emit(run_id, {"type": "done"})


# --------------------------------------------------------------------------- #
# Pressure test — interactive interview (own endpoints, not the generic advance)
# --------------------------------------------------------------------------- #
async def _pt_rows(sess, run_id: str) -> list[PressureTestMessage]:
    return list(
        (
            await sess.execute(
                select(PressureTestMessage)
                .where(PressureTestMessage.run_id == run_id)
                .order_by(PressureTestMessage.seq)
            )
        ).scalars()
    )


def _visible(rows: list[PressureTestMessage]) -> list[dict]:
    return [{"role": r.role, "text": r.content.get("text", "")} for r in rows]


def _messages_dto(rows: list[PressureTestMessage]) -> list[dict]:
    return [{"role": r.role, "text": r.content.get("text", ""),
             "sources": r.content.get("sources", [])} for r in rows]


def _interview_usage(rows: list[PressureTestMessage]) -> Usage:
    """Sum the token usage of every interviewer turn so the pressure-test stage cost
    reflects the whole conversation, not just the final synthesis."""
    u = Usage.zero()
    for r in rows:
        data = r.content.get("usage") if r.role == "assistant" else None
        if data:
            u.add(Usage(**{k: data.get(k, 0) for k in _USAGE_FIELDS}))
    return u


async def _load_hypothesis(run: RunRow):
    for s in run.stages:
        if s.stage_key == "hypothesis":
            return rebuild_output("hypothesis", s.output)
    return None


async def pt_state(run_id: str, user_id: uuid.UUID) -> dict | None:
    """Transcript + whether the pressure test has concluded (its stage result exists)."""
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or run.user_id != user_id:
            return None
        concluded = any(s.stage_key == "pressure_test" for s in run.stages)
        rows = await _pt_rows(sess, run_id)
        return {"messages": _messages_dto(rows), "concluded": concluded}


async def pt_start(run_id: str, user_id: uuid.UUID) -> dict | None:
    """Open the interview: generate the first VC turn from the hypothesis."""
    rt = _runtime(run_id)
    async with rt.lock:
        async with session() as sess:
            run = await _load(sess, run_id)
            if run is None or run.user_id != user_id:
                return None
            completed = [s.stage_key for s in run.stages]
            nxt = first_stage() if not completed else next_stage(completed[-1])
            if nxt != "pressure_test":
                return None
            if await _pt_rows(sess, run_id):
                return {"messages": _messages_dto(await _pt_rows(sess, run_id)), "concluded": False}
            hyp = await _load_hypothesis(run)
            mock = run.mock

        text, sources, usage = await pressure_test.open_interview(hyp, EngineConfig(mock=mock))
        async with session() as sess:
            sess.add(PressureTestMessage(
                run_id=run_id, seq=0, role="assistant",
                content={"text": text, "sources": [c.model_dump() for c in sources],
                         "usage": usage.to_dict()},
                created_at=_now(),
            ))
            await sess.commit()
            rows = await _pt_rows(sess, run_id)
        return {"messages": _messages_dto(rows), "concluded": False}


async def pt_message(run_id: str, user_id: uuid.UUID, text: str) -> dict | None:
    """Append the founder's reply and generate the interviewer's next turn."""
    rt = _runtime(run_id)
    async with rt.lock:
        async with session() as sess:
            run = await _load(sess, run_id)
            if run is None or run.user_id != user_id:
                return None
            if any(s.stage_key == "pressure_test" for s in run.stages):
                return None  # already concluded
            rows = await _pt_rows(sess, run_id)
            if not rows:
                return None  # not started
            hyp = await _load_hypothesis(run)
            mock = run.mock
            visible = _visible(rows)
            next_seq = rows[-1].seq + 1
            sess.add(PressureTestMessage(
                run_id=run_id, seq=next_seq, role="user",
                content={"text": text}, created_at=_now(),
            ))
            await sess.commit()

        reply, sources, usage = await pressure_test.next_reply(
            hyp, visible, text, EngineConfig(mock=mock)
        )
        async with session() as sess:
            sess.add(PressureTestMessage(
                run_id=run_id, seq=next_seq + 1, role="assistant",
                content={"text": reply, "sources": [c.model_dump() for c in sources],
                         "usage": usage.to_dict()},
                created_at=_now(),
            ))
            await sess.commit()
            rows = await _pt_rows(sess, run_id)
        return {"messages": _messages_dto(rows), "concluded": False}


# Sentinel pt_conclude returns when the founder can't afford the pressure-test stage.
INSUFFICIENT = "insufficient"


async def pt_conclude(run_id: str, user_id: uuid.UUID) -> dict | str | None:
    """Synthesize the interview into a cited verdict, write it as the stage result, and
    run the Coach over it. Reserves the stage credit atomically before any paid work and
    refunds it if synthesis fails. Returns ``INSUFFICIENT`` if the founder can't afford it."""
    rt = _runtime(run_id)
    async with rt.lock:
        async with session() as sess:
            run = await _load(sess, run_id)
            if run is None or run.user_id != user_id:
                return None
            if any(s.stage_key == "pressure_test" for s in run.stages):
                return await get_run(run_id, user_id)  # already concluded
            rows = await _pt_rows(sess, run_id)
            if not rows:
                return None
            # Reserve before doing paid work (atomic, FOR UPDATE) — same anti-bypass
            # guarantee as begin_stage, since a user can conclude several runs at once.
            if not await credits.reserve(sess, user_id, stage_cost("pressure_test"),
                                         "stage:pressure_test", run_id):
                return INSUFFICIENT
            hyp = await _load_hypothesis(run)
            mock, seq = run.mock, len(run.stages)
            visible = _visible(rows)
            interview_usage = _interview_usage(rows)
            await sess.commit()

        config = EngineConfig(mock=mock)
        try:
            result, _, synth_usage = await pressure_test.conclude(hyp, visible, config)
            review, review_usage = await review_stage("pressure_test", result, config)
        except Exception:
            async with session() as sess:  # failed stage is free — give the credit back
                await credits.refund(sess, user_id, stage_cost("pressure_test"),
                                     "refund:pressure_test", run_id)
                await sess.commit()
            raise

        # The interview + synthesis ran on the stage model; the Coach on the coach model.
        opus = Usage.zero()
        opus.add(interview_usage)
        opus.add(synth_usage)
        cost = cost_usd(config.stage_model, opus) + cost_usd(config.coach_model, review_usage)
        total = Usage.zero()
        total.add(opus)
        total.add(review_usage)
        usage_dict = total.to_dict()
        usage_dict["cost_usd"] = cost

        async with session() as sess:
            sess.add(StageResultRow(
                run_id=run_id, stage_key="pressure_test", seq=seq,
                output=result.model_dump(mode="json"),
                review=review.model_dump(mode="json"),
                usage=usage_dict, created_at=_now(),
            ))
            run = await _load(sess, run_id)
            run.status = "idle"
            run.updated_at = _now()
            await sess.commit()

    _log_stage_usage(run_id, user_id, "pressure_test", usage_dict)
    await _emit(run_id, {"type": "stage_complete", "stage": "pressure_test"})
    return await get_run(run_id, user_id)


# --------------------------------------------------------------------------- #
# Credits — balance (reservation happens atomically inside begin_stage/pt_conclude)
# --------------------------------------------------------------------------- #
async def balance(user_id: uuid.UUID) -> int:
    async with session() as sess:
        return await credits.get_balance(sess, user_id)


# --------------------------------------------------------------------------- #
# Publish + public gallery (no PII exposed)
# --------------------------------------------------------------------------- #
def _verdict_line(run: RunRow) -> str:
    by = {s.stage_key: s.output for s in run.stages}
    bits: list[str] = []
    if "pressure_test" in by:
        bits.append("Survived pressure test ✓" if by["pressure_test"].get("survived")
                    else "Didn't survive the pressure test")
    if "market" in by:
        bits.append("Real market signal ✓" if by["market"].get("real_signal")
                    else "Weak market signal")
    return " · ".join(bits) or "Validation in progress"


async def set_published(run_id: str, user_id: uuid.UUID, published: bool) -> dict | None:
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or run.user_id != user_id:
            return None
        run.published = published
        run.published_at = _now() if published else None
        run.updated_at = _now()
        await sess.commit()
        await sess.refresh(run, attribute_names=["stages"])
        return _snapshot(run)


async def gallery_list(limit: int = 60) -> list[dict]:
    async with session() as sess:
        runs = (
            await sess.execute(
                select(RunRow)
                .where(RunRow.published.is_(True))
                .order_by(RunRow.published_at.desc())
                .limit(limit)
                .options(selectinload(RunRow.stages))
            )
        ).scalars()
        return [
            {
                "id": r.id,
                "idea": r.idea,
                "verdict": _verdict_line(r),
                "stages_done": [s.stage_key for s in r.stages],
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in runs
        ]


async def gallery_detail(run_id: str) -> dict | None:
    """Public, PII-free view of a published run."""
    async with session() as sess:
        run = await _load(sess, run_id)
        if run is None or not run.published:
            return None
        return {
            "id": run.id,
            "idea": run.idea,
            "verdict": _verdict_line(run),
            "published_at": run.published_at.isoformat() if run.published_at else None,
            "results": [
                {
                    "stage_key": s.stage_key,
                    "title": STAGE_TITLES[s.stage_key],
                    "output": s.output,
                    "review": s.review,
                }
                for s in run.stages
            ],
        }
