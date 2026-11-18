# Common Ground

Three participants discuss whom to elect as Decision Maker for an imaginary follow-up experiment. Each person sees the same neutral labels (Player A, B and C), whether a seat belongs to a human or a scripted agent. The session ends with the election result.

## Run locally

Start Docker Desktop, then run this command from the repository root.

```sh
docker compose up --build
```

Open [localhost:8080](http://localhost:8080) in **one fresh tab per human** and click **Join the experiment** in each. The default uses one human and two scripted agents, so you can run the demo in one tab. For a group with more humans, enter the address in each new tab. Duplicating an existing tab can copy its player identity. Refreshing the same tab reconnects that player.

Stop the app with `docker compose down`. PostgreSQL keeps the session records in a named volume.

## Switch participant configurations

Edit `participants` in [config.yml](config.yml). Once the current session has finished, run `docker compose restart backend`, then join from one fresh tab per human. Restarting the backend marks unfinished sessions as aborted.

| Value for `participants` | Human players needed |
| --- | --- |
| `[human, human, human]` | 3 |
| `[human, human, ai]` | 2 |
| `[human, ai, ai]` (default) | 1 |

The same file controls the timers. The default allows three minutes for the group to fill, 60 seconds for each discussion, 30 seconds for each ballot and six seconds to read the first result.

## Election rules and design choices

- **Two rounds.** Each discussion ends with a private vote. Players may vote for themselves. The ballot closes when all three votes arrive or time expires. Missing votes count as abstentions.
- **Feedback and outcome.** After round one, everyone sees the totals and can reconsider during the second discussion. Only round two elects the Decision Maker. A tie triggers a draw among the tied leaders using the saved session seed. If nobody votes, everyone sees that no Decision Maker was selected.
- **Scripted agents.** Agents use short scripted messages and can respond to words in the discussion. Each chooses another player using the session seed, its label and the round. This keeps voting reproducible and lets the demo run without an external model or API key.
- **Timing and persistence.** Nginx serves the React frontend and forwards API and WebSocket traffic to FastAPI. One backend worker controls the clock and orders concurrent actions. It saves the session and its events in one PostgreSQL transaction before sending an update to browsers.
- **Privacy.** The server sends each player their own ballot confirmation. Other players see aggregate results after the ballot closes. Participant screens and messages from the server omit the human/agent assignments and other players’ individual votes.

See the [prompt examples and model notes](ai-prompts.md).
