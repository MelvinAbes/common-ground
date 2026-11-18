import { test, expect, type Page } from "playwright/test";
import type { State } from "../src/types";

const humans = Number(process.env.TEST_HUMANS || "2");
if (![1, 2, 3].includes(humans)) throw new Error("TEST_HUMANS must be 1, 2 or 3");

for (const missed of [false, true]) {
  test(`${humans} humans: ${missed ? "missed votes and no final votes" : "shared flow and refresh"}`, async ({ browser }) => {
    test.skip(missed && humans !== 3, "No-votes case requires three humans");
    const contexts = await Promise.all(Array.from({ length: humans }, () => browser.newContext()));
    const pages = await Promise.all(contexts.map((context) => context.newPage()));
    const states: State[][] = pages.map(() => []);
    const errors: string[] = [];
    pages.forEach((page, index) => {
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("websocket", (ws) => ws.on("framereceived", ({ payload }) => {
        const frame = JSON.parse(String(payload));
        if (frame.type === "state") states[index].push(frame);
      }));
    });
    const latest = (index: number) => states[index].at(-1)!;
    const vote = async (page: Page, target: string) => {
      await page.getByRole("button", { name: new RegExp(`^${target}`) }).click();
      await page.getByRole("button", { name: "Confirm my vote" }).click();
    };
    try {
      for (let index = 0; index < humans; index++) {
        await pages[index].goto("/");
        await pages[index].getByRole("button", { name: "Join the experiment" }).click();
        if (index < humans - 1) {
          await expect(pages[index].getByRole("heading", { name: "A moment to get ready." })).toBeVisible();
        }
      }
      for (const page of pages) {
        await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
      }
      expect(new Set(pages.map((_, i) => latest(i).session_id)).size).toBe(1);
      expect(new Set(pages.map((_, i) => latest(i).you)).size).toBe(humans);
      expect(new Set(pages.map((_, i) => latest(i).deadline)).size).toBe(1);
      const identity = latest(0).you;
      const message = `Docker verification ${humans}: listen to everyone <script>text only</script>`;
      await pages[0].getByLabel("Your message").fill(message);
      await pages[0].getByRole("button", { name: "Send message" }).click();
      for (const page of pages) await expect(page.getByRole("log")).toContainText(message);
      await pages[0].reload();
      await expect(pages[0].locator(".identity h2")).toHaveText(identity);
      await expect(pages[0].getByRole("log")).toContainText(message);
      for (const round of [1, 2]) {
        for (const page of pages) await expect(page.getByRole("heading", { name: "Who has your vote?" })).toBeVisible();
        if (!missed || round === 1) {
          const peerFrames = states[1]?.length;
          await vote(pages[0], round === 1 ? "Player A" : identity);
          if (humans > 1) {
            await expect.poll(() => latest(0).your_vote).not.toBeNull();
            expect(latest(1).your_vote).toBeNull();
            expect(latest(1).results.length).toBe(round - 1);
            expect(states[1].length).toBe(peerFrames);
          }
          if (!missed) {
            for (let index = 1; index < humans; index++) {
              await vote(pages[index], round === 1 ? "Player A" : latest(index).you);
            }
          }
        }
        if (round === 1) {
          for (const page of pages) await expect(page.getByRole("heading", { name: "A first look at your group’s choices." })).toBeVisible();
          for (const page of pages) await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
        }
      }
      const finalHeading = missed ? "No Decision Maker was selected." : "Your group has decided.";
      for (const page of pages) await expect(page.getByRole("heading", { name: finalHeading })).toBeVisible();
      const final = latest(0);
      for (let index = 0; index < humans; index++) {
        expect(latest(index).results).toEqual(final.results);
        expect(latest(index).winner).toBe(final.winner);
      }
      if (humans === 3) {
        if (missed) {
          expect(final.results.map((r) => r.abstentions)).toEqual([2, 3]);
          expect(final.winner).toBeNull();
        } else {
          expect(final.results[1].tied).toEqual(["Player A", "Player B", "Player C"]);
          expect(final.results[1].counts).toEqual({ "Player A": 1, "Player B": 1, "Player C": 1 });
        }
      }
      const allowed = ["type", "session_id", "you", "players", "phase", "round", "rounds", "deadline", "server_time", "phase_started", "discussion_seconds", "messages", "your_vote", "results", "winner", "abort_reason"].sort();
      for (const stream of states) for (const state of stream) {
        expect(Object.keys(state).sort()).toEqual(allowed);
        for (const message of state.messages) expect(Object.keys(message).sort()).toEqual(["at", "id", "player", "round", "text"]);
        for (const result of state.results) expect(Object.keys(result).every((key) => ["round", "counts", "abstentions", "winner", "tied", "rule"].includes(key))).toBe(true);
      }
      expect(errors).toEqual([]);
      console.log(JSON.stringify({ session_id: final.session_id, humans, missed, winner: final.winner, results: final.results, received_states: states.map((s) => s.length) }));
    } finally {
      await Promise.all(contexts.map((context) => context.close()));
    }
  });
}
