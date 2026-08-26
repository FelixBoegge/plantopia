import { defineConfig, devices } from "@playwright/test";

/**
 * The browser tests, against the real stack.
 *
 * Everything below the browser is real: a real API, a real database, real migrations, the
 * real graph with its real interrupt. Only the models are scripted — see
 * `tests/e2e/models.py` for what they answer and `tests/e2e/server.py` for why the patch
 * lives in test code rather than behind a setting.
 *
 * These exist because a green component suite has repeatedly described screens that did not
 * work: an SSE parser that yielded nothing because the server sends CRLF, a verification
 * screen that spent its own link, a registration that flushed and never committed. Each was
 * invisible to jsdom and obvious in a browser within seconds.
 *
 * Both servers are started here and on ports of their own, so a run cannot collide with a
 * dev server somebody has open, and cannot touch development data.
 */

const API = "http://127.0.0.1:8100";
const WEB = "http://127.0.0.1:5273";

export default defineConfig({
  testDir: "./e2e",
  // A run drives the whole graph and waits on real streams. One at a time: they share one
  // database and one account, and a parallel run would be testing the isolation of the
  // fixtures rather than the application.
  workers: 1,
  fullyParallel: false,
  // Nothing here is flaky by design. A retry would hide the one thing these tests exist to
  // catch, which is a screen that only sometimes works.
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: WEB,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Recreates and migrates its own database on every start, which is what makes
      // "against a clean database" true rather than aspirational.
      command: "uv run python -m tests.e2e.server",
      cwd: "..",
      url: `${API}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev -- --port 5273 --strictPort --host 127.0.0.1",
      url: WEB,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { PLANTOPIA_API_ORIGIN: API },
    },
  ],
});
