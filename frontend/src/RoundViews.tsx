import { useEffect, useRef, useState } from "react";
import type { Result, State } from "./types";

export function Avatar({
  player,
  small = false,
}: {
  player: string;
  small?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={`avatar ${small ? "small" : ""} player-${player.slice(-1)}`}
    >
      {player.slice(-1)}
    </span>
  );
}

export function Tally({ result }: { result: Result }) {
  return (
    <div className="tally">
      {Object.entries(result.counts).map(([player, count]) => (
        <div className="tally-row" key={player}>
          <Avatar player={player} small />
          <span>{player}</span>
          <div className="bar-track">
            <div
              className={`bar player-${player.slice(-1)}`}
              style={{ width: `${(count / 3) * 100}%` }}
            />
          </div>
          <strong>
            {count}
            <span className="sr-only"> {count === 1 ? "vote" : "votes"}</span>
          </strong>
        </div>
      ))}
      {result.abstentions > 0 && (
        <p className="muted">
          {result.abstentions} {result.abstentions === 1 ? "participant" : "participants"} did not vote before the deadline.
        </p>
      )}
    </div>
  );
}

type RoundProps = { state: State; enabled: boolean; pending: boolean };

export function Discussion({
  state, enabled, pending, acceptedMessage, onMessage,
}: RoundProps & { acceptedMessage: number; onMessage: (text: string) => void }) {
  const [draft, setDraft] = useState("");
  const chat = useRef<HTMLDivElement>(null);

  useEffect(() => setDraft(""), [acceptedMessage]);
  useEffect(() => {
    chat.current?.scrollTo({ top: chat.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length]);

  function submitMessage() {
    const text = draft.trim();
    if (text && enabled) onMessage(text);
  }

  return (
    <>
      <div className="discussion-prompt">
        <span className="prompt-mark" aria-hidden="true">
          “
        </span>
        <div>
          <strong>
            Who should be your group’s Decision Maker?
          </strong>
          <p>
            Make your case, ask a question, or explain what
            matters to you.
          </p>
        </div>
      </div>
      <div
        className="chat"
        ref={chat}
        role="log"
        aria-label="Group discussion"
        aria-live="polite"
        aria-relevant="additions"
      >
        {state.messages.length === 0 && (
          <div className="empty-chat">
            <span aria-hidden="true">↗</span>
            <p>You’re all here. Start the conversation.</p>
          </div>
        )}
        {state.messages.map((message, index) => (
          <div key={message.id}>
            {(index === 0 ||
              state.messages[index - 1].round !==
                message.round) && (
              <div className="round-divider">
                Round {message.round}
              </div>
            )}
            <article
              className={`message ${message.player === state.you ? "own" : ""}`}
            >
              <Avatar player={message.player} small />
              <div className="message-body">
                <div className="message-meta">
                  <strong>
                    {message.player}
                    {message.player === state.you && (
                      <span> (you)</span>
                    )}
                  </strong>
                  <time
                    dateTime={new Date(
                      message.at * 1000,
                    ).toISOString()}
                  >
                    {new Date(
                      message.at * 1000,
                    ).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                </div>
                <p>{message.text}</p>
              </div>
            </article>
          </div>
        ))}
      </div>
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submitMessage();
        }}
      >
        <label className="sr-only" htmlFor="message">
          Your message
        </label>
        <textarea
          id="message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={500}
          disabled={!enabled}
          placeholder="Share your thoughts with the group…"
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              submitMessage();
            }
          }}
        />
        <div className="composer-bottom">
          <span>
            {draft.length}/500{" "}
            <span className="keyboard-hint">· Enter to send</span>
          </span>
          <button
            className="primary"
            disabled={!enabled || !draft.trim()}
          >
            {pending ? "Sending…" : "Send message"}{" "}
            <span aria-hidden="true">↑</span>
          </button>
        </div>
      </form>
    </>
  );
}

export function Ballot({
  state, enabled, pending, onVote,
}: RoundProps & { onVote: (target: string) => void }) {
  const [choice, setChoice] = useState("");
  const selected = state.your_vote ?? choice;

  return (
    <div className="voting-stage">
      <h2>Who has your vote?</h2>
      <p>
        Choose one participant. You can vote for yourself.
        <br />
        Your choice is final once submitted.
      </p>
      <div
        className="vote-options"
        role="group"
        aria-label="Choose your Decision Maker"
      >
        {state.players.map((player) => (
          <button
            className={`vote-option ${selected === player ? "selected" : ""}`}
            aria-pressed={selected === player}
            key={player}
            onClick={() => setChoice(player)}
            disabled={!!state.your_vote || !enabled}
          >
            <Avatar player={player} />
            <strong>{player}</strong>
            <span>
              {player === state.you ? "You" : "Group participant"}
            </span>
            <span className="selection-dot" aria-hidden="true" />
          </button>
        ))}
      </div>
      {state.your_vote ? (
        <div className="vote-confirmation" role="status">
          <span>✓</span>
          <strong>Your vote is recorded.</strong>
          <p>
            Waiting for the other votes or the timer to finish.
          </p>
        </div>
      ) : (
        <>
          <button
            className="primary"
            disabled={!choice || !enabled}
            onClick={() => onVote(choice)}
          >
            {pending ? "Recording…" : "Confirm my vote"}
          </button>
          <p className="muted small-text">
            If you do not vote in time, your vote counts as an
            abstention.
          </p>
        </>
      )}
    </div>
  );
}
