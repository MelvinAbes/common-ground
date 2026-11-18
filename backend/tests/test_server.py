import asyncio
import copy

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import RuleError, Session
from app.main import Experiment, create_app
from tests.fakes import FakeSocket, MemoryStore


@pytest.mark.parametrize("humans", [1, 2, 3])
async def test_waits_for_every_human_connection(humans):
    exp = Experiment(
        Settings(participants=["human"] * humans + ["ai"] * (3 - humans)), MemoryStore()
    )
    joins = await asyncio.gather(*(exp.join() for _ in range(humans)))
    sid = joins[0]["session_id"]
    assert len({j["session_id"] for j in joins}) == 1
    sockets = []
    for index, join in enumerate(joins):
        assert exp.sessions[sid].phase == "waiting"
        ws = FakeSocket()
        sockets.append(ws)
        await exp.connect(ws, sid, join["token"])
        assert exp.sessions[sid].phase == ("discussion" if index == humans - 1 else "waiting")
    assert all(ws.frames[-1]["phase"] == "discussion" for ws in sockets)
    assert len({ws.frames[-1]["deadline"] for ws in sockets}) == 1


async def test_parallel_joins_form_groups_of_three():
    exp = Experiment(Settings(participants=["human"] * 3), MemoryStore())
    joins = await asyncio.gather(*(exp.join() for _ in range(6)))
    groups = [j["session_id"] for j in joins]
    assert len(set(groups)) == 2
    assert all(groups.count(sid) == 3 for sid in set(groups))


async def test_join_draws_from_all_remaining_human_seats(monkeypatch):
    exp = Experiment(Settings(participants=["human"] * 3), MemoryStore())
    pools = []

    def choose_last(seats):
        pools.append([p.label for p in seats])
        return seats[-1]

    monkeypatch.setattr("app.main.secrets.choice", choose_last)
    for _ in range(3):
        join = await exp.join()
        seat = exp.sessions[join["session_id"]].participant_for(join["token"])
        assert seat.label == pools[-1][-1]
    assert pools == [["Player A", "Player B", "Player C"], ["Player A", "Player B"], ["Player A"]]


async def test_private_events_do_not_notify_peers_and_closed_ballot_is_shared(monkeypatch):
    exp = Experiment(Settings(participants=["human"] * 3), MemoryStore())
    first, second, third = FakeSocket(), FakeSocket(), FakeSocket()
    a = await exp.join()
    sid = a["session_id"]
    await exp.connect(first, sid, a["token"])
    b = await exp.join()
    await exp.connect(second, sid, b["token"])
    await exp.disconnect(second)
    await exp.connect(second, sid, b["token"])
    assert len(first.frames) == 1
    c = await exp.join()
    await exp.connect(third, sid, c["token"])
    assert all(ws.frames[-1]["phase"] == "discussion" for ws in (first, second, third))
    deadline = exp.sessions[sid].deadline
    monkeypatch.setattr("app.main.time.time", lambda: deadline)
    vote = {"type": "vote", "round": 1, "target": "Player B", "request_id": "ballot"}
    await exp.command(first, vote)
    assert first.frames[-2]["your_vote"] == "Player B"
    assert second.frames[-1]["phase"] == "voting"
    assert second.frames[-1]["your_vote"] is None
    peer_frames = len(third.frames)
    await exp.command(second, vote)
    await exp.command(second, vote)  # Retry after a lost acknowledgement.
    await exp.command(second, {**vote, "request_id": "another"})
    assert second.frames[-1]["type"] == "error"
    assert len(third.frames) == peer_frames
    assert "version" not in third.frames[-1]
    await exp.command(third, vote)
    for ws in (first, second, third):
        state = [frame for frame in ws.frames if frame["type"] == "state"][-1]
        assert state["phase"] == "feedback" and state["results"][0]["counts"]["Player B"] == 3
    assert sum(e["type"] == "vote_submitted" for e in exp.store.events) == 3


async def test_capacity_preserves_connected_results_and_uncommitted_evictions():
    store = MemoryStore()
    exp = Experiment(Settings(participants=["human"] * 3), store)
    sessions = [Session.create(exp.settings, 1) for _ in range(200)]
    for session in sessions:
        session.phase = "complete"
        exp.sessions[session.id] = session
        exp.clients[FakeSocket()] = (session.id, "Player A")
    with pytest.raises(RuleError, match="busy"):
        await exp.join()
    connection = next(iter(exp.clients))
    await exp.disconnect(connection)
    store.fail = True
    with pytest.raises(ConnectionError):
        await exp.join()
    assert set(exp.sessions) == {s.id for s in sessions}
    store.fail = False
    await exp.join()
    assert len(exp.sessions) == 200 and sessions[0].id not in exp.sessions
    assert all(sid in exp.sessions for sid, _ in exp.clients.values())


async def test_filled_waiting_room_still_requires_disconnected_human_to_return():
    exp = Experiment(Settings(participants=["human"] * 3), MemoryStore())
    joins = await asyncio.gather(*(exp.join() for _ in range(3)))
    sid = joins[0]["session_id"]
    first = FakeSocket()
    await exp.connect(first, sid, joins[0]["token"])
    await exp.disconnect(first)
    for join in joins[1:]:
        await exp.connect(FakeSocket(), sid, join["token"])
    assert exp.sessions[sid].phase == "waiting"
    await exp.connect(FakeSocket(), sid, joins[0]["token"])
    assert exp.sessions[sid].phase == "discussion"


async def test_reconnect_keeps_identity_and_replaces_old_connection():
    exp = Experiment(Settings(participants=["human", "ai", "ai"]), MemoryStore())
    join = await exp.join()
    first, second = FakeSocket(), FakeSocket()
    await exp.connect(first, join["session_id"], join["token"])
    await exp.connect(second, join["session_id"], join["token"])
    assert first.closed and len(exp.clients) == 1
    assert first.frames[0]["you"] == second.frames[0]["you"]
    assert first.frames[0]["deadline"] == second.frames[0]["deadline"]


async def test_database_failure_does_not_publish_uncommitted_message():
    store = MemoryStore()
    exp = Experiment(Settings(participants=["human", "ai", "ai"]), store)
    join, ws = await exp.join(), FakeSocket()
    await exp.connect(ws, join["session_id"], join["token"])
    before = copy.deepcopy(exp.sessions[join["session_id"]].dump())
    frames = len(ws.frames)
    store.fail = True
    with pytest.raises(ConnectionError):
        await exp.command(
            ws, {"type": "message", "round": 1, "text": "unsaved", "request_id": "one"}
        )
    assert exp.sessions[join["session_id"]].dump() == before
    assert len(ws.frames) == frames


async def test_restart_aborts_active_session_and_preserves_history():
    store = MemoryStore()
    settings = Settings(participants=["human", "ai", "ai"])
    exp = Experiment(settings, store)
    join = await exp.join()
    await exp.connect(FakeSocket(), join["session_id"], join["token"])
    recovered = Experiment(settings, store)
    await recovered.recover()
    session = recovered.sessions[join["session_id"]]
    assert session.phase == "aborted"
    assert session.participant_for(join["token"])
    assert "restarted" in session.abort_reason
    assert len(store.events) > 3


def test_real_websocket_authentication_and_message_acknowledgement():
    app = create_app(Settings(participants=["human", "ai", "ai"]), MemoryStore(), clock=False)
    with TestClient(app) as client:
        join = client.post("/api/join").json()
        with client.websocket_connect(f"/api/ws/{join['session_id']}") as ws:
            ws.send_json({"token": join["token"]})
            state = ws.receive_json()
            assert state["phase"] == "discussion"
            ws.send_json({"type": "message", "round": 1, "request_id": "test", "text": "Hello"})
            state = ws.receive_json()
            assert state["messages"][-1]["text"] == "Hello"
            assert ws.receive_json()["type"] == "ack"
            ws.send_text("not json")
            assert ws.receive_json()["type"] == "error"


def test_invalid_token_and_cross_origin_join_rejected():
    app = create_app(Settings(participants=["human"] * 3), MemoryStore(), clock=False)
    with TestClient(app) as client:
        assert (
            client.post("/api/join", headers={"Origin": "https://other.example"}).status_code == 403
        )
        join = client.post("/api/join").json()
        with client.websocket_connect(f"/api/ws/{join['session_id']}") as ws:
            ws.send_json({"token": "wrong"})
            assert ws.receive_json()["type"] == "fatal"


def test_health_reports_database_failure():
    store = MemoryStore()
    with TestClient(create_app(Settings(participants=["human"] * 3), store)) as client:
        assert client.get("/api/health").status_code == 200
        store.fail = True
        assert client.get("/api/health").status_code == 503
