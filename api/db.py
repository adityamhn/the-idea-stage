"""Async SQLAlchemy engine + session for the Supabase Postgres database.

The app connects directly to Postgres (the `postgres` role bypasses RLS); ownership
is enforced in code by filtering on ``user_id``. DATABASE_URL is the Supabase
connection string (use the pooler URI for serverless-friendly pooling), with the
driver normalised to asyncpg.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _normalise(url: str) -> str:
    # Accept plain postgres:// or postgresql:// and route to the asyncpg driver.
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ensure() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set.")
        # asyncpg doesn't accept libpq's sslmode in the URL; SSL is negotiated
        # automatically against Supabase, so we just drop any sslmode query arg.
        url = _normalise(database_url).split("?")[0]
        _engine = create_async_engine(url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


def session() -> AsyncSession:
    """A new async session. Use as an async context manager."""
    return _ensure()()
