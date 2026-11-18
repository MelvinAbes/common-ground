import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import LABELS, RuleError, Session, act, finish_vote, public_state, start, tick


def make_session(kinds=None):
    s = Session.create(Settings(participants=kinds or ["human"] * 3), 1000)
    events = []
    start(s, events, 1000)
    return s, events


def command(kind, request_id="one", round=1, **kwargs):
    return {"type": kind, "request_id": request_id, "round": round, **kwargs}


@pytest.mark.parametrize("humans", [1, 2, 3])
def test_complete_flow_for_every_condition(humans):
    s, events = make_session(["human"] * humans + ["ai"] * (3 - humans))
    for round_no in (1, 2):
        assert s.phase == "discussion" and s.round == round_no
        tick(s, events, s.phase_started + 52)
        assert len(s.messages) == (3 - humans) * 3 * round_no
        tick(s, events, s.deadline)
        assert s.phase == "voting"
        for p in s.participants:
            if p.kind == "human":
                act(
                    s,
                    events,
                    s.phase_started + 1,
                    p.label,
                    command("vote", f"{p.label}-{round_no}", round_no, target=LABELS[0]),
                )
        if s.phase == "voting":
            tick(s, events, s.phase_started + 15)
        assert s.phase == ("feedback" if round_no == 1 else "complete")
        if round_no == 1:
            tick(s, events, s.deadline)
    assert s.winner in LABELS
    assert len(s.results) == 2
    assert [e["seq"] for e in events] == list(range(1, s.seq + 1))


def test_private_state_has_no_types_tokens_or_other_votes():
    s, events = make_session(["human", "ai", "ai"])
    s.votes["1"] = {"Player B": "Player C"}
    for p in s.participants:
        p.token_hash = "secret"
    state = public_state(s, "Player A", 1010)
    serialized = json.dumps(state)
    assert state["your_vote"] is None
    assert not {"config", "participants", "seed", "votes", "token_hash", "version", "seq"} & state.keys()
    assert "secret" not in serialized and '"ai"' not in serialized


def test_duplicate_message_is_idempotent():
    s, events = make_session()
    action = command("message", text="I would listen to everyone.")
    act(s, events, 1001, "Player A", action)
    act(s, events, 1001.1, "Player A", action)
    assert len(s.messages) == 1


def test_quiet_round_agent_sends_distinct_messages_and_votes_as_announced():
    s, events = make_session(["human", "human", "ai"])
    tick(s, events, s.deadline - 1)
    assert len({m["text"] for m in s.messages}) == 3
    last_message = s.messages[-1]
    tick(s, events, s.deadline)
    tick(s, events, s.phase_started + 20)
    target = s.votes["1"][last_message["player"]]
    assert f"leaning towards {target}." in last_message["text"]


def test_second_vote_cannot_replace_first():
    s, events = make_session()
    tick(s, events, s.deadline)
    act(s, events, 1061, "Player A", command("vote", target="Player B"))
    with pytest.raises(RuleError, match="already"):
        act(s, events, 1062, "Player A", command("vote", "two", target="Player C"))
    assert s.votes["1"]["Player A"] == "Player B"


@pytest.mark.parametrize(
    "payload",
    [
        command("message", text=" "),
        command("message", text="x" * 501),
        command("message", text=42),
        command("message", round=2, text="stale"),
        command("vote", target="Player A"),
        {"type": "invented"},
        {"type": []},
        {"type": "message", "text": "no ID", "round": 1},
    ],
)
def test_invalid_actions_rejected(payload):
    s, events = make_session()
    with pytest.raises(RuleError):
        act(s, events, 1001, "Player A", payload)


def test_deadline_is_enforced_without_waiting_for_scheduler():
    s, events = make_session()
    with pytest.raises(RuleError, match="no longer"):
        act(s, events, s.deadline, "Player A", command("message", text="late"))


def test_message_rate_limit():
    s, events = make_session()
    act(s, events, 1001, "Player A", command("message", text="first"))
    with pytest.raises(RuleError, match="wait"):
        act(s, events, 1001.1, "Player A", command("message", "two", text="second"))


def test_self_vote_and_invalid_target():
    s, events = make_session()
    tick(s, events, s.deadline)
    act(s, events, 1061, "Player A", command("vote", target="Player A"))
    with pytest.raises(RuleError, match="three"):
        act(s, events, 1061, "Player B", command("vote", target="Player D"))


def test_round_two_only_selects_winner():
    s, events = make_session()
    s.votes["1"] = {p: "Player A" for p in LABELS}
    finish_vote(s, events, 1060)
    assert s.winner is None
    tick(s, events, s.deadline)
    s.votes["2"] = {p: "Player B" for p in LABELS}
    finish_vote(s, events, 1200)
    assert s.winner == "Player B"


def test_tie_can_be_reproduced_from_recorded_seed():
    s, events = make_session()
    s.round = 2
    s.votes["2"] = dict(zip(LABELS, LABELS))
    restored = Session.restore(s.dump())
    finish_vote(s, events, 1100)
    finish_vote(restored, [], 1100)
    assert s.winner == restored.winner
    assert s.results[-1]["tied"] == LABELS


def test_no_votes_means_no_winner_and_three_abstentions():
    s, events = make_session()
    s.round = 2
    finish_vote(s, events, 1100)
    assert s.winner is None and s.phase == "complete"
    assert s.results[-1]["abstentions"] == 3


def test_waiting_room_expires():
    s = Session.create(Settings(participants=["human"] * 3), 1000)
    tick(s, [], s.deadline)
    assert s.phase == "aborted"


@pytest.mark.parametrize(
    "overrides",
    [
        {"participants": ["ai"] * 3},
        {"participants": ["human"] * 2},
        {"participants": ["human", "bot", "ai"]},
        {"discussion_seconds": 0},
        {"rounds": 3},
        {"unknown_option": True},
    ],
)
def test_config_rejects_unsupported_experiments(overrides):
    with pytest.raises(ValidationError):
        Settings.model_validate({"participants": ["human", "ai", "ai"], **overrides})
