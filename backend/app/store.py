"""Atomic session snapshots and an ordered research event log."""

import json
from datetime import datetime, timezone

from .domain import Session

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    snapshot JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS events (
    session_id UUID NOT NULL REFERENCES sessions(id),
    seq INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    round INTEGER NOT NULL,
    phase TEXT NOT NULL,
    elapsed_ms BIGINT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (session_id, seq)
);
-- Older databases used 32-bit milliseconds, which overflow after about 25 days.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'events'
          AND column_name = 'elapsed_ms' AND data_type = 'integer'
    ) THEN
        ALTER TABLE events ALTER COLUMN elapsed_ms TYPE BIGINT;
    END IF;
END;
$$;
"""


class PostgresStore:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def open(cls, url):
        import asyncpg

        pool = await asyncpg.create_pool(url, min_size=1, max_size=5, command_timeout=5)
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA)
        return cls(pool)

    async def save(self, session: Session, events: list):
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO sessions(id, snapshot) VALUES($1, $2::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET snapshot=$2::jsonb, updated_at=now()",
                session.id,
                json.dumps(session.dump()),
            )
            await conn.executemany(
                "INSERT INTO events VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)",
                [
                    (
                        session.id,
                        e["seq"],
                        datetime.fromtimestamp(e["at"], timezone.utc),
                        e["type"],
                        e["actor"],
                        e["round"],
                        e["phase"],
                        e["elapsed_ms"],
                        json.dumps(e["payload"]),
                    )
                    for e in events
                ],
            )

    async def load(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT snapshot FROM sessions ORDER BY updated_at DESC LIMIT 200"
            )
        return [Session.restore(json.loads(r["snapshot"])) for r in rows]

    async def healthy(self):
        async with self.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    async def close(self):
        await self.pool.close()
