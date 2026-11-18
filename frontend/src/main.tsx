import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { useExperiment } from "./useExperiment";
import { Avatar, Ballot, Discussion, Tally } from "./RoundViews";
import "./style.css";

function App() {
  const {
    state,
    credentials,
    connection,
    error,
    joining,
    pending,
    acceptedMessage,
    offset,
    join,
    reset,
    send,
    clearError,
  } = useExperiment();
  const [, setClockTick] = useState(0);
  const stage = state?.phase;
  const finished = stage === "complete" || stage === "aborted";
  const timed = !!stage && !finished;
  const phaseHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!timed) return;
    const refresh = () => setClockTick((tick) => tick + 1);
    const id = setInterval(refresh, 200);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [timed]);
  useEffect(() => {
    phaseHeading.current?.focus();
  }, [state?.phase, state?.round]);
  const seconds = state
    ? Math.max(
        0,
        // Background tabs can suspend interval callbacks. Every render must
        // read the current clock, including renders caused by socket updates.
        Math.ceil((state.deadline * 1000 - Date.now() - offset.current) / 1000),
      )
    : 0;
  const online = connection === "online";
  const label =
    stage === "discussion"
      ? "Discussion"
      : stage === "voting"
        ? "Private vote"
        : stage === "feedback"
          ? "Round results"
          : "Your session";
  const duration = state ? state.deadline - state.phase_started : 1;
  const enabled = online && seconds > 0 && !pending;
  const currentStep = stage === "complete" ? 3 : (state?.round ?? 0);

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Common Ground home">
          <span className="brand-symbol" aria-hidden="true">
            cg.
          </span>
          <span>
            Common Ground<small>A group decision experiment</small>
          </span>
        </a>
        <span className="header-note">
          THREE PARTICIPANTS. ONE SHARED CHOICE.
        </span>
        {credentials && (
          <span
            className={`connection ${online ? "connected" : ""}`}
            role="status"
          >
            <i />
            {online
              ? "Connected"
              : connection === "failed"
                ? "Connection unavailable"
                : "Reconnecting…"}
          </span>
        )}
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button className="text-button" onClick={clearError}>
            Dismiss
          </button>
        </div>
      )}

      {!credentials ? (
        <main className="welcome">
          <div className="welcome-copy">
            <p className="eyebrow">GROUP DECISION STUDY / 01</p>
            <h1>
              A small group.
              <br />A shared decision.
            </h1>
            <p className="intro">
              Meet your group, exchange views, and choose a Decision Maker
              together.
            </p>
            <button
              className="primary join-button"
              disabled={joining}
              onClick={join}
            >
              {joining ? "Joining…" : "Join the experiment"}
              <span aria-hidden="true">↗</span>
            </button>
            <p className="welcome-meta">
              3 participants <span>·</span> 2 discussion rounds <span>·</span>{" "}
              About 3 minutes
            </p>
          </div>
          <div className="welcome-aside">
            <div className="group-illustration" aria-hidden="true">
              <span className="circle-ring" />
              <span className="circle-ring inner" />
              <span className="orbit a">A</span>
              <span className="orbit b">B</span>
              <span className="orbit c">C</span>
              <span className="center-label">
                A shared
                <br />
                choice
              </span>
            </div>
            <div className="overview">
              <h2>What to expect</h2>
              <ol>
                <li>
                  <span>01</span>
                  <div>
                    <strong>Meet your group</strong>
                    <p>You will receive a neutral player name.</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>Discuss and vote</strong>
                    <p>
                      Share your views, then cast a private vote in each round.
                    </p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>See the decision</strong>
                    <p>The final vote selects your group’s Decision Maker.</p>
                  </div>
                </li>
              </ol>
            </div>
          </div>
          <p className="privacy-note">
            This is a demonstration. Messages and votes are recorded for the
            experiment. Please avoid sharing personal information.
          </p>
        </main>
      ) : !state ? (
        <main className="center-stage">
          <p className="eyebrow">YOUR SESSION</p>
          <h1>Connecting to your group</h1>
          <p>Your place is saved while we connect.</p>
          {connection === "failed" && (
            <button className="primary" onClick={reset}>
              Return to start
            </button>
          )}
        </main>
      ) : (
        <main className="experiment-layout">
          <aside className="session-sidebar">
            <p className="eyebrow">YOUR PARTICIPATION</p>
            <div className="identity">
              <Avatar player={state.you} />
              <div>
                <h2>{state.you}</h2>
                <span className="muted">Your name in this group</span>
              </div>
            </div>
            <div className="session-code">
              <span>SESSION</span>
              <code>{state.session_id.slice(0, 8).toUpperCase()}</code>
            </div>
            <div className="journey" aria-label="Experiment progress">
              {["Waiting room", "Round 1", "Round 2", "Results"].map(
                (name, index) => {
                  return (
                    <div
                      className={`journey-step ${index === currentStep ? "current" : ""} ${index < currentStep ? "done" : ""}`}
                      key={name}
                    >
                      <span>
                        {index < currentStep
                          ? "✓"
                          : String(index + 1).padStart(2, "0")}
                      </span>
                      {name}
                    </div>
                  );
                },
              )}
            </div>
            <div className="reminder">
              <h3>Your shared task</h3>
              <p>
                Choose someone to make decisions for the group in a later,
                imaginary experiment.
              </p>
              <p>This session ends after the election.</p>
            </div>
            <p className="sidebar-foot">
              Your vote stays private.
              <br />
              Only group totals are shared.
            </p>
          </aside>

          <section className="main-panel">
            {stage === "waiting" ? (
              <div className="center-stage waiting-stage">
                <p className="eyebrow">WAITING ROOM</p>
                <h1 ref={phaseHeading} tabIndex={-1}>
                  A moment to get ready.
                </h1>
                <p>
                  We’ll begin automatically when your group is ready.
                  <br />
                  Keep this tab open.
                </p>
                <div className="waiting-players">
                  {state.players.map((player) => (
                    <div key={player}>
                      <Avatar player={player} />
                      <strong>{player}</strong>
                      {player === state.you && <small>You</small>}
                    </div>
                  ))}
                </div>
                <div className="waiting-pulse">
                  <i />
                  <span>Getting the group together</span>
                </div>
                <p className="muted small-text">
                  Waiting room closes in {seconds}s. You can refresh and keep
                  your place.
                </p>
              </div>
            ) : stage === "aborted" ? (
              <div className="center-stage">
                <p className="eyebrow">SESSION ENDED</p>
                <h1 ref={phaseHeading} tabIndex={-1}>
                  Let’s try a new group.
                </h1>
                <p>{state.abort_reason}</p>
                <button className="primary" onClick={reset}>
                  Return to start
                </button>
              </div>
            ) : (
              <>
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">
                      {finished
                        ? "EXPERIMENT COMPLETE"
                        : `ROUND ${state.round} OF ${state.rounds}`}
                    </p>
                    <h1 ref={phaseHeading} tabIndex={-1}>
                      {finished
                        ? state.winner ? "Your group has decided." : "No Decision Maker was selected."
                        : label}
                    </h1>
                  </div>
                  {!finished && (
                    <div
                      className={`timer ${seconds <= 10 ? "urgent" : ""}`}
                      aria-label={`${seconds} seconds remaining`}
                    >
                      <strong>
                        {Math.floor(seconds / 60)}:
                        {String(seconds % 60).padStart(2, "0")}
                      </strong>
                      <span>
                        {seconds === 0 ? "Moving to next stage…" : "remaining"}
                      </span>
                    </div>
                  )}
                </div>
                {!finished && (
                  <div className="time-track" aria-hidden="true">
                    <div
                      style={{
                        width: `${Math.min(100, (seconds / duration) * 100)}%`,
                      }}
                    />
                  </div>
                )}

                {stage === "discussion" && (
                  <Discussion
                    key={state.round}
                    state={state}
                    enabled={enabled}
                    pending={pending}
                    acceptedMessage={acceptedMessage}
                    onMessage={(text) => send("message", { text })}
                  />
                )}
                {stage === "voting" && (
                  <Ballot
                    key={state.round}
                    state={state}
                    enabled={enabled}
                    pending={pending}
                    onVote={(target) => send("vote", { target })}
                  />
                )}

                {stage === "feedback" && (
                  <div className="feedback-stage">
                    <p className="eyebrow">FIRST ROUND FEEDBACK</p>
                    <h2>A first look at your group’s choices.</h2>
                    <p>
                      There is still time to discuss. Round 2 will decide the
                      final outcome.
                    </p>
                    <Tally result={state.results[0]} />
                    <p className="muted">
                      The next discussion starts automatically in {seconds}s.
                    </p>
                  </div>
                )}

                {stage === "complete" && (
                  <div className="results-stage">
                    <div className="winner-block">
                      {state.winner && <Avatar player={state.winner} />}
                      <p className="eyebrow">
                        {state.winner
                          ? "YOUR DECISION MAKER"
                          : "NO DECISION MAKER"}
                      </p>
                      <h2>{state.winner || "No votes were received."}</h2>
                      <p>{state.results.at(-1)?.rule}</p>
                    </div>
                    <div className="results-rounds">
                      {state.results.map((result) => (
                        <section key={result.round}>
                          <h3>
                            Round {result.round}{" "}
                            <span>
                              {result.round === 1
                                ? "First impressions"
                                : "Final vote"}
                            </span>
                          </h3>
                          <Tally result={result} />
                        </section>
                      ))}
                    </div>
                    <div className="completion-note">
                      <p>
                        Thank you for taking part. This experiment ends here.
                      </p>
                      <button className="secondary" onClick={reset}>
                        Return to start
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
            {connection !== "online" && !finished && (
              <div className="connection-notice" role="status">
                {connection === "failed" ? (
                  <>
                    <span>Your connection is unavailable.</span>
                    <button className="text-button" onClick={reset}>
                      Return to start
                    </button>
                  </>
                ) : (
                  "Reconnecting… Your place is saved. The experiment timer continues."
                )}
              </div>
            )}
          </section>
        </main>
      )}
      <footer className="site-footer">
        <span>Common Ground</span>
        <span>Technical assessment prototype · 2026</span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
