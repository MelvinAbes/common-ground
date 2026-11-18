import { test, expect } from "playwright/test";

test("a delayed tab timer cannot inflate a newly received countdown", async ({ page }) => {
  // Freeze interval callbacks, as Safari can do for background tabs. Network
  // responses still render the UI and must use the current wall clock.
  await page.addInitScript(() => {
    window.setInterval = (() => 0) as typeof window.setInterval;
    const originalNow = Date.now.bind(Date);
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      Date.now = () => originalNow() + 60000;
      return originalFetch(...args);
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Join the experiment" }).click();
  await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
  await expect(page.locator(".timer strong")).toHaveText("0:08");
});

test("join, chat, reload, vote twice and see results", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A small group. A shared decision." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Join the experiment" }).click();
  await expect(
    page.getByRole("heading", { name: "Discussion", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Your message")
    .fill("I would listen to everyone before deciding.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("log")).toContainText(
    "I would listen to everyone before deciding.",
  );
  const identity = await page.locator(".identity h2").textContent();
  await page.reload();
  await expect(page.locator(".identity h2")).toHaveText(identity!);
  await expect(page.getByRole("log")).toContainText(
    "I would listen to everyone before deciding.",
  );
  await page.getByLabel("Your message").fill("Unsent first-round draft");
  for (const round of [1, 2]) {
    await expect(
      page.getByRole("heading", { name: "Who has your vote?" }),
    ).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Player A" }).click();
    await page.getByRole("button", { name: "Confirm my vote" }).click();
    if (round === 1) {
      await expect(
        page.getByRole("heading", {
          name: "A first look at your group’s choices.",
        }),
      ).toBeVisible({ timeout: 10000 });
      await expect(
        page.getByRole("heading", { name: "Discussion", exact: true }),
      ).toBeVisible({ timeout: 5000 });
      await expect(page.getByLabel("Your message")).toHaveValue("");
    }
  }
  await expect(
    page.getByRole("heading", { name: "Your group has decided." }),
  ).toBeVisible({ timeout: 10000 });
  expect(errors).toEqual([]);
});

test("mobile layout fits and all controls have labels", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Join the experiment" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Join the experiment" }).click();
  await expect(page.getByLabel("Your message")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
