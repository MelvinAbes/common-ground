"""Experiment rules. No HTTP, sockets or database code in this module."""

import hashlib
import random
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .config import Settings

LABELS = ["Player A", "Player B", "Player C"]
FINISHED = {"complete", "aborted"}


class RuleError(ValueError):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Participant:
    label: str
    kind: str
    token_hash: str | None = None


@dataclass
class Session:
    id: str
    config: dict
    participants: list[Participant]
    created_at: float
    seed: int
    phase: str = "waiting"
    round: int = 0
    phase_started: float = 0
    deadline: float = 0
    seq: int = 0
    messages: list[dict] = field(default_factory=list)
    votes: dict[str, dict[str, str]] = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    bot_actions: list[str] = field(default_factory=list)
    request_ids: dict[str, list[str]] = field(default_factory=dict)
    last_message_at: dict[str, float] = field(default_factory=dict)
    winner: str | None = None
    abort_reason: str | None = None

    @classmethod
    def create(cls, config: Settings, now: float):
        kinds = list(config.participants)
        secrets.SystemRandom().shuffle(kinds)
        return cls(
            id=str(uuid4()),
            config=config.model_dump(),
            participants=[Participant(label, kind) for label, kind in zip(LABELS, kinds)],
            created_at=now,
            phase_started=now,
            deadline=now + config.waiting_seconds,
            seed=secrets.randbits(32),
        )

    @classmethod
    def restore(cls, data: dict):
        return cls(**{**data, "participants": [Participant(**p) for p in data["participants"]]})

    def dump(self):
        return asdict(self)

    def participant_for(self, token: str) -> Participant | None:
        hashed = token_hash(token)
        return next((p for p in self.participants if p.token_hash == hashed), None)

    def vacant_humans(self) -> list[Participant]:
        return [p for p in self.participants if p.kind == "human" and not p.token_hash]


def record(s: Session, events: list, now: float, kind: str, actor=None, **payload):
    s.seq += 1
    events.append(
        {
            "seq": s.seq,
            "at": now,
            "type": kind,
            "actor": actor,
            "round": s.round,
            "phase": s.phase,
            "elapsed_ms": round((now - s.phase_started) * 1000),
            "payload": payload,
        }
    )


def enter(s: Session, events: list, now: float, phase: str, seconds: int):
    previous = s.phase
    s.phase, s.phase_started, s.deadline = phase, now, now + seconds
    record(s, events, now, "phase_changed", previous=previous, next=phase, deadline=s.deadline)


def start(s: Session, events: list, now: float):
    s.round = 1
    enter(s, events, now, "discussion", s.config["discussion_seconds"])


def abort(s: Session, events: list, now: float, reason: str):
    s.abort_reason = reason
    enter(s, events, now, "aborted", 0)


def cast_vote(s: Session, events: list, now: float, actor: str, target: str):
    votes = s.votes.setdefault(str(s.round), {})
    if actor in votes:
        raise RuleError("Your vote has already been recorded.")
    if target not in LABELS:
        raise RuleError("Choose one of the three participants.")
    votes[actor] = target
    record(s, events, now, "vote_submitted", actor=actor, target=target)
    if len(votes) == len(LABELS):
        finish_vote(s, events, now)


def finish_vote(s: Session, events: list, now: float):
    votes = s.votes.get(str(s.round), {})
    counts = {p: list(votes.values()).count(p) for p in LABELS}
    missing = [p for p in LABELS if p not in votes]
    result: dict[str, Any] = {"round": s.round, "counts": counts, "abstentions": len(missing)}
    if missing:
        record(s, events, now, "votes_missing", participants=missing)
    if s.round == 2:
        if not votes:
            result.update(
                winner=None, tied=[], rule="No votes received. No Decision Maker selected."
            )
        else:
            leaders = [p for p in LABELS if counts[p] == max(counts.values())]
            # Store the seed with the session so this draw can be reproduced.
            s.winner = random.Random(s.seed).choice(leaders)
            result.update(
                winner=s.winner,
                tied=leaders if len(leaders) > 1 else [],
                rule="Random draw among tied leaders."
                if len(leaders) > 1
                else "Most votes in round 2.",
            )
    s.results.append(result)
    record(s, events, now, "round_result", **result)
    enter(
        s,
        events,
        now,
        "complete" if s.round == 2 else "feedback",
        0 if s.round == 2 else s.config["feedback_seconds"],
    )


def agent_choice(s: Session, actor: str) -> str:
    others = [label for label in LABELS if label != actor]
    return random.Random(s.seed + s.round + LABELS.index(actor)).choice(others)


def bot_message(s: Session, actor: str, index: int) -> str:
    if index == 0:
        return (
            {
                "Player A": "I would listen to everyone before deciding. What matters most to you in this role?",
                "Player B": "I can take the role if the group agrees. I think explaining each choice is important.",
                "Player C": "I would prefer someone who weighs up different views. How should we handle disagreement?",
            }[actor]
            if s.round == 1
            else {
                "Player A": "Before we vote again, has anyone changed their mind about who should take the role?",
                "Player B": "I would like to hear what each person would do if the group disagreed on a decision.",
                "Player C": "For the final vote, I am looking for someone who listens carefully and explains their choices.",
            }[actor]
        )
    if index == 1:
        recent = next(
            (m for m in reversed(s.messages) if m["player"] != actor and m["round"] == s.round),
            None,
        )
        if recent is None:
            return "What would you want the Decision Maker to do if the group is split?"
        body = recent["text"].lower()
        if any(word in body for word in ["fair", "listen", "everyone"]):
            return f"{recent['player']}, I agree that everyone should get a say before a decision."
        if "?" in body:
            return "I would hear both sides, explain my reasoning, and then make a clear choice."
        return f"Thanks, {recent['player']}. Could you explain how you would handle a difficult choice?"
    target = agent_choice(s, actor)
    return (
        f"I am leaning towards {target}. I would want them to explain their decisions to the group."
    )


def tick(s: Session, events: list, now: float):
    if s.phase in FINISHED:
        return
    if now >= s.deadline:
        if s.phase == "waiting":
            abort(s, events, now, "The group did not fill in time. Please join a new session.")
        elif s.phase == "discussion":
            enter(s, events, now, "voting", s.config["voting_seconds"])
        elif s.phase == "voting":
            finish_vote(s, events, now)
        elif s.phase == "feedback":
            s.round = 2
            enter(s, events, now, "discussion", s.config["discussion_seconds"])
        return
    for p in s.participants:
        if p.kind != "ai":
            continue
        if s.phase == "discussion":
            for i, fraction in enumerate([0.15, 0.47, 0.76]):
                key = f"{s.round}:{p.label}:message:{i}"
                offset = (LABELS.index(p.label) * 0.04) * s.config["discussion_seconds"]
                due = s.phase_started + fraction * s.config["discussion_seconds"] + offset
                if key not in s.bot_actions and now >= due:
                    s.bot_actions.append(key)
                    add_message(s, events, now, p.label, bot_message(s, p.label, i))
        elif s.phase == "voting":
            due = s.phase_started + s.config["voting_seconds"] * (
                0.18 + LABELS.index(p.label) * 0.09
            )
            if now >= due and p.label not in s.votes.get(str(s.round), {}):
                cast_vote(s, events, now, p.label, agent_choice(s, p.label))


def add_message(s: Session, events: list, now: float, actor: str, text: str):
    message = {"id": str(uuid4()), "player": actor, "text": text, "at": now, "round": s.round}
    s.messages.append(message)
    s.last_message_at[actor] = now
    record(s, events, now, "message_sent", actor=actor, message=message)


def act(s: Session, events: list, now: float, actor: str, command: dict):
    kind = command.get("type")
    if kind not in ("message", "vote"):
        raise RuleError("Unknown action.")
    request_id = command.get("request_id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
        raise RuleError("A request ID is required.")
    if request_id in s.request_ids.get(actor, []):
        return  # A reconnect or double-click must not create another action.
    if command.get("round") != s.round:
        raise RuleError("The round has changed. Please try again.")
    expected = "discussion" if kind == "message" else "voting"
    if s.phase != expected or now >= s.deadline:
        raise RuleError("This action is no longer available in the current stage.")
    if kind == "message":
        text = command.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            raise RuleError("Messages must contain 1 to 500 characters.")
        if now - s.last_message_at.get(actor, 0) < 0.75:
            raise RuleError("Please wait a moment before sending another message.")
        add_message(s, events, now, actor, text.strip())
    else:
        cast_vote(s, events, now, actor, command.get("target"))
    s.request_ids.setdefault(actor, []).append(request_id)


def public_state(s: Session, player: str, now: float):
    # Explicit allowlist: never serialize internal participant records to clients.
    return {
        "type": "state",
        "session_id": s.id,
        "you": player,
        "players": LABELS,
        "phase": s.phase,
        "round": s.round,
        "rounds": 2,
        "deadline": s.deadline,
        "server_time": now,
        "phase_started": s.phase_started,
        "discussion_seconds": s.config["discussion_seconds"],
        "messages": s.messages,
        "your_vote": s.votes.get(str(s.round), {}).get(player),
        "results": s.results,
        "winner": s.winner,
        "abort_reason": s.abort_reason,
    }
