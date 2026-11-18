import { defineConfig } from "playwright/test";

// Uses the already-running Docker app, including Nginx and PostgreSQL.
// This config does not start the in-memory browser harness.
export default defineConfig({
  testDir: "./tests",
  testMatch: "docker.spec.ts",
  timeout: 240000,
  expect: { timeout: 90000 },
  workers: 1,
  use: {
    baseURL: process.env.APP_URL || "http://localhost:8080",
    headless: true,
    channel: process.env.CI ? undefined : "chrome",
  },
});
