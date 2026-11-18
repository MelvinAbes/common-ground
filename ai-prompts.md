# AI Usage - prompts

## Models used in the project

Codex was the AI assistant used for Common Ground. The project records identify these models.

| Model | Work it supported |
| --- | --- |
| `gpt-6.1-sol` | Local setup guidance, the first demo review, and later documentation work |
| `gpt-6-astra` | The round-two agent openings and the first verification on my Mac |
| `gpt-6.2-astra` | Code review, cleanup, further testing, and explanations of the codebase |
| `gpt-6.2-sol` | Documentation and prompt drafting |

## 1. Start with the flow

```text
I'm putting together the discussion and voting flow. Everyone joins a waiting room, then there are two discussions with a vote after each one. The first vote gives the group some feedback, and the second chooses the Decision Maker. Check that this matches the brief before we go further.
```

## 2. Organise the backend

```text
I've started the React and FastAPI parts. I want to keep the experiment rules separate from the WebSocket handling so I can follow them easily. Help me work out what belongs in the session logic and what belongs in the API. Keep the database code separate too.
```

## 3. Put the settings in one place

```text
The researcher needs to switch between three humans, two humans and one agent, and one human and two agents. Put those settings and the timers in config.yml. I should be able to change the condition without editing Python or React. Check the values when the backend starts so a bad configuration gives a useful error.
```

## 4. Get the waiting room right

```text
I'm not sure that counting assigned human seats is enough to start the session. What if someone joins and their connection drops before the last person arrives? Check that every required human is actually connected before the first discussion starts.
```

## 5. Connect the discussion

```text
Let's get one shared discussion working first. If Player A sends a message, everyone should see it under the same label. Have React display the state from FastAPI. I don't want each tab working out its own version of the session.
```

## 6. Work out the two ballots

```text
For the first vote, show everyone the totals and give them a short pause before the next discussion. The second vote should decide the winner on its own. Keep each person's choice private while voting is open. Can you check that the two rounds follow those rules?
```

## 7. Decide what to save

```text
I want PostgreSQL to hold the current session and a record of what happened. That should include messages, votes and changes of stage. Would a session snapshot and an ordered event list be enough for this? Explain how they would be saved together before adding more tables.
```

## 8. Make the local setup straightforward

```text
Help me finish the Docker setup so I can start the whole app with Docker Compose. Nginx should serve React and forward the API and WebSocket requests to FastAPI. Keep PostgreSQL data in a volume so stopping the app doesn't wipe the sessions.
```

## 9. Check what we've built so far

```text
The main pieces are connected now. Go through the flow against the brief and point out anything that could stop a group from finishing the experiment. Start with the waiting room, private voting and the final result. Show me the problem before making a change.
```

## 10. Keep the scope manageable

```text
I think the proposed additions would make this harder to finish and explain. Let's get the two-round experiment working properly first. Which changes fix a problem, and which are just extra features? Talk me through that before adding anything else.
```

## 11. Question the browser timer

```text
I don't think the browser should decide when discussion ends. A background tab can pause its timer, and two laptops might have different clocks. Keep the deadline on the backend. Also check a vote that arrives exactly at the deadline so we're clear about whether it gets accepted.
```

## 12. Check what the browser receives

```text
Hiding the agent label in React isn't enough if the participant type is still in the response. Look at the join response and WebSocket messages. Choose the fields each player is allowed to receive, then test that. They need their own vote confirmation, but they shouldn't get anyone else's individual vote or credentials.
```

## 13. Save before sending the update

```text
I'm not happy with sending the result before the database has saved it. If the write fails, the players could see a result that isn't recorded. Save the session and events in one transaction, then send the update. Test a failed event insert and check that the session change rolls back as well. Use a separate test database.
```

## 14. Think about extra workers

```text
Would adding workers actually work here? Each process would have its own session manager, so two votes could end up in different copies of the session. Keep one worker for this version. Show me how the current lock keeps changes in order, and explain what we'd need before using more workers.
```

## 15. Handle a dropped connection

```text
If I refresh a tab, I want to come back as the same player with the same chat history. Check how the session ID and token are kept in that tab. Also try resending an action after reconnecting. A repeated request shouldn't create a second message or count a vote twice.
```

## 16. Check what the agent says and does

```text
Can you show me how an agent chooses whom to vote for? Its last discussion message should agree with that choice. If the message and ballot use separate rules, they could disagree. Have them use the same choice function and add a test for that.
```

## 17. Discuss an LLM first

```text
An LLM might make the discussion more varied, but I want to think about the votes separately. What would it improve in each part? Compare a hosted model with one I could run locally. Think about repeatability, response time and the risk of revealing that a player is an agent. Let's discuss it before adding a dependency.
```

## 18. Check ties and missing votes

```text
We need a clear result when the final vote is tied or someone doesn't vote. Use a saved seed for the draw between tied leaders so we can reproduce the choice. If nobody votes in round two, show that no Decision Maker was selected. Check that all players see the same outcome.
```

## 19. Test the full app

```text
The tests using the in-memory store are useful, but they don't check PostgreSQL or Nginx. Run the app through Docker and try all three participant configurations in independent browser contexts. Check the waiting room, shared chat, both votes, a refresh and the final results. Keep my existing records and restore the settings after testing.
```

## 20. Explain what actually passed

```text
Show me which check supports each result you're reporting. Was it a unit test, a database test or a browser run? Include failures and skipped checks too. For anything you fixed, explain how the problem happened and how you checked the fix. I need to be able to repeat the checks myself.
```

## 21. Make the code easier to follow

```text
Now go through the code for repeated logic or extra layers we don't need. Check what uses a function before combining or removing it. Show me the diff and rerun the affected checks. After that, walk me through one vote, from the React button to the saved record and the update each browser gets.
```
