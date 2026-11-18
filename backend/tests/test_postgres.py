"""Runs against a real PostgreSQL service when TEST_DATABASE_URL is set."""

import os

import asyncpg
import pytest

from app.config import Settings
from app.domain import Session, enter, record
from app.store import PostgresStore


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Requires a running PostgreSQL test database"
)
async def test_postgres_snapshot_and_events_commit_or_rollback_together():
    url = os.environ["TEST_DATABASE_URL"]
    store = await PostgresStore.open(url)
    session = Session.create(Settings(participants=["human", "ai", "ai"]), 1000)
    events = []
    enter(session, events, 1000, "complete", 0)
    try:
        await store.save(session, events)
        # A participant reopens the results 30 days after the session ended.
        events = []
        record(session, events, 1000 + 30 * 86400, "participant_connected", actor="Player A")
        await store.save(session, events)
        loaded = next(s for s in await store.load() if s.id == session.id)
        assert loaded.dump() == session.dump()
        async with store.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT seq, event_type, elapsed_ms FROM events WHERE session_id=$1 ORDER BY seq",
                session.id,
            )
            assert [tuple(row) for row in rows] == [
                (1, "phase_changed", 0),
                (2, "participant_connected", 2_592_000_000),
            ]
        session.phase = "discussion"
        # Duplicate sequence forces the event insert to fail after the snapshot UPDATE.
        with pytest.raises(asyncpg.UniqueViolationError):
            await store.save(session, events)
        loaded = next(s for s in await store.load() if s.id == session.id)
        assert loaded.phase == "complete"
        async with store.pool.acquire() as conn:
            assert (
                await conn.fetchval("SELECT count(*) FROM events WHERE session_id=$1", session.id)
                == 2
            )
    finally:
        async with store.pool.acquire() as conn:
            await conn.execute("DELETE FROM events WHERE session_id=$1", session.id)
            await conn.execute("DELETE FROM sessions WHERE id=$1", session.id)
        await store.close()
