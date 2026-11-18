import asyncio
import copy
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from .config import Settings, load_settings
from .domain import (
    FINISHED,
    RuleError,
    Session,
    abort,
    act,
    public_state,
    record,
    start,
    tick,
    token_hash,
)
from .store import PostgresStore

logger = logging.getLogger("experiment")


class Experiment:
    def __init__(self, settings: Settings, store):
        self.settings = settings
        self.store = store
        self.sessions: dict[str, Session] = {}
        self.clients: dict[WebSocket, tuple[str, str]] = {}
        # One lock keeps state changes, commits and broadcasts in the same order.
        self.lock = asyncio.Lock()

    async def recover(self):
        for session in await self.store.load():
            if session.phase not in FINISHED:
                events = []
                abort(
                    session,
                    events,
                    time.time(),
                    "The server restarted during this session. Please join a new session.",
                )
                await self.store.save(session, events)
            self.sessions[session.id] = session

    async def commit(self, session: Session, events: list):
        if not events:
            return
        await self.store.save(session, events)
        self.sessions[session.id] = session
        logger.info(
            json.dumps(
                {
                    "session_id": session.id,
                    "version": session.seq,
                    "events": [e["type"] for e in events],
                }
            )
        )
        await self.publish(session, events)

    async def publish(self, session: Session, events: list):
        # Frame timing is visible too. A private event updates only its participant.
        shared = any(e["type"] in {"message_sent", "phase_changed", "round_result"} for e in events)
        private = {
            e["actor"] for e in events if e["type"] in {"participant_connected", "vote_submitted"}
        }

        async def send(ws, player):
            try:
                await asyncio.wait_for(ws.send_json(public_state(session, player, time.time())), 1)
            except Exception:
                self.clients.pop(ws, None)
                with suppress(Exception):
                    await ws.close(code=1011)

        await asyncio.gather(
            *(
                send(ws, player)
                for ws, (sid, player) in list(self.clients.items())
                if sid == session.id and (shared or player in private)
            )
        )

    async def join(self):
        async with self.lock:
            now = time.time()
            existing = next(
                (
                    s
                    for s in self.sessions.values()
                    if s.phase == "waiting" and s.deadline > now and s.vacant_humans()
                ),
                None,
            )
            events = []
            evict = None
            if existing:
                session = copy.deepcopy(existing)
            else:
                if len(self.sessions) >= 200:
                    connected = {sid for sid, _ in self.clients.values()}
                    evict = min(
                        (
                            s for s in self.sessions.values()
                            if s.phase in FINISHED and s.id not in connected
                        ),
                        key=lambda s: s.created_at,
                        default=None,
                    )
                    if evict is None:
                        raise RuleError("All sessions are busy. Please try again later.")
                session = Session.create(self.settings, now)
                record(
                    session,
                    events,
                    now,
                    "session_created",
                    config=session.config,
                    seed=session.seed,
                    participants=[{"label": p.label, "kind": p.kind} for p in session.participants],
                )
            participant = secrets.choice(session.vacant_humans())
            token = secrets.token_urlsafe(32)
            participant.token_hash = token_hash(token)
            record(session, events, now, "participant_joined", actor=participant.label)
            await self.commit(session, events)
            if evict is not None:
                del self.sessions[evict.id]
            return {"session_id": session.id, "token": token}

    async def connect(self, ws, sid, token):
        async with self.lock:
            original = self.sessions.get(sid)
            participant = original.participant_for(token) if original else None
            if not participant:
                raise RuleError("This session could not be restored. Please join a new session.")
            # One active connection per identity. A reload replaces the previous socket.
            for old, identity in list(self.clients.items()):
                if identity == (sid, participant.label):
                    self.clients.pop(old, None)
                    with suppress(Exception):
                        await old.close(
                            code=4001, reason="This participant opened another connection."
                        )
            self.clients[ws] = (sid, participant.label)
            session, events, now = copy.deepcopy(original), [], time.time()
            record(session, events, now, "participant_connected", actor=participant.label)
            online = {player for session_id, player in self.clients.values() if session_id == sid}
            if session.phase == "waiting":
                if now >= session.deadline:
                    tick(session, events, now)
                elif all(p.label in online for p in session.participants if p.kind == "human"):
                    start(session, events, now)
            try:
                await self.commit(session, events)
            except Exception:
                self.clients.pop(ws, None)
                raise

    async def disconnect(self, ws):
        async with self.lock:
            identity = self.clients.pop(ws, None)
            if identity:
                sid, player = identity
                session, events = copy.deepcopy(self.sessions[sid]), []
                record(session, events, time.time(), "participant_disconnected", actor=player)
                await self.commit(session, events)

    async def command(self, ws, command):
        async with self.lock:
            if ws not in self.clients:
                raise RuleError("This connection is no longer active.")
            sid, player = self.clients[ws]
            session, events, now = copy.deepcopy(self.sessions[sid]), [], time.time()
            # Advance expired stages before validating an action.
            tick(session, events, now)
            error = None
            try:
                act(session, events, now, player, command)
            except RuleError as exc:
                error = str(exc)
                record(session, events, now, "action_rejected", actor=player, reason=error)
            await self.commit(session, events)
            await ws.send_json(
                {
                    "type": "error" if error else "ack",
                    "request_id": command.get("request_id"),
                    "message": error,
                }
            )

    async def run_clock(self):
        while True:
            await asyncio.sleep(0.25)
            try:
                async with self.lock:
                    for original in list(self.sessions.values()):
                        if original.phase in FINISHED:
                            continue
                        session, events = copy.deepcopy(original), []
                        tick(session, events, time.time())
                        await self.commit(session, events)
            except Exception:
                logger.exception("Clock update failed; no uncommitted state was published")


def same_origin(origin: str | None, host: str) -> bool:
    return origin is None or urlparse(origin).netloc == host


def create_app(settings=None, store=None, clock=True):
    @asynccontextmanager
    async def lifespan(app):
        configured = settings or load_settings(os.getenv("CONFIG_PATH", "../config.yml"))
        database = store or await PostgresStore.open(os.environ["DATABASE_URL"])
        app.state.experiment = Experiment(configured, database)
        await app.state.experiment.recover()
        timer = asyncio.create_task(app.state.experiment.run_clock()) if clock else None
        try:
            yield
        finally:
            if timer:
                timer.cancel()
                with suppress(asyncio.CancelledError):
                    await timer
            for ws in list(app.state.experiment.clients):
                with suppress(Exception):
                    await ws.close(code=1001)
            if store is None:
                await database.close()

    app = FastAPI(
        title="Group decision experiment", lifespan=lifespan, docs_url=None, redoc_url=None
    )

    @app.get("/api/health")
    async def health(request: Request):
        try:
            await request.app.state.experiment.store.healthy()
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ok"}

    @app.post("/api/join", status_code=201)
    async def join(request: Request):
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            raise HTTPException(403, "Origin not allowed")
        try:
            return await request.app.state.experiment.join()
        except RuleError as exc:
            raise HTTPException(409, str(exc)) from None
        except Exception:
            logger.exception("Join failed")
            raise HTTPException(
                503, "The experiment is temporarily unavailable. Please try again."
            ) from None

    @app.websocket("/api/ws/{session_id}")
    async def websocket(ws: WebSocket, session_id: str):
        if not same_origin(ws.headers.get("origin"), ws.headers.get("host", "")):
            await ws.close(code=1008)
            return
        await ws.accept()
        experiment = ws.app.state.experiment
        try:
            # Credentials travel in a frame rather than a URL/access log.
            auth = await asyncio.wait_for(ws.receive_json(), timeout=5)
            if (
                not isinstance(auth, dict)
                or not isinstance(auth.get("token"), str)
                or len(auth["token"]) > 200
            ):
                raise RuleError("A valid session token is required.")
            await experiment.connect(ws, session_id, auth["token"])
            while True:
                raw = await ws.receive_text()
                if len(raw) > 4096:
                    await ws.send_json({"type": "error", "message": "Message too large."})
                    continue
                try:
                    command = json.loads(raw)
                    if not isinstance(command, dict):
                        raise ValueError
                except (ValueError, TypeError):
                    await ws.send_json({"type": "error", "message": "Invalid message format."})
                    continue
                await experiment.command(ws, command)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        except RuleError as exc:
            with suppress(Exception):
                await ws.send_json({"type": "fatal", "message": str(exc)})
                await ws.close(code=1008)
        except Exception:
            logger.exception("Connection failed")
            with suppress(Exception):
                await ws.close(code=1011)
        finally:
            try:
                await experiment.disconnect(ws)
            except Exception:
                logger.exception("Could not persist disconnect")

    return app


app = create_app()
