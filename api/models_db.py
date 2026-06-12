"""ORM models mirroring the Phase 2a schema (see the Supabase migration)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

_TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(_TS)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(_TS)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    razorpay_payment_link_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(_TS)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    idea: Mapped[str] = mapped_column(Text)
    mock: Mapped[bool] = mapped_column(Boolean, default=True)
    scheduling_link: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="idle")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS)
    updated_at: Mapped[datetime] = mapped_column(_TS)

    stages: Mapped[list["StageResultRow"]] = relationship(
        back_populates="run", order_by="StageResultRow.seq", cascade="all, delete-orphan"
    )


class StageResultRow(Base):
    __tablename__ = "stage_results"
    __table_args__ = (UniqueConstraint("run_id", "stage_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str] = mapped_column(String)
    seq: Mapped[int] = mapped_column(Integer)
    output: Mapped[dict] = mapped_column(JSONB)
    review: Mapped[dict] = mapped_column(JSONB)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(_TS)

    run: Mapped[RunRow] = relationship(back_populates="stages")


class PressureTestMessage(Base):
    __tablename__ = "pressure_test_messages"
    __table_args__ = (UniqueConstraint("run_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String)  # assistant | user
    content: Mapped[dict] = mapped_column(JSONB)  # { text, sources? }
    created_at: Mapped[datetime] = mapped_column(_TS)
