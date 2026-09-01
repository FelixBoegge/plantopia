import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { signUp } from "./people";

/**
 * Losing the connection in the middle of a run.
 *
 * A run takes about a minute and a half and streams the whole way. Somebody's laptop sleeps,
 * a proxy times an idle connection out, a phone changes network — none of which is unusual,
 * and all of which look identical from here: the stream ends and the run does not.
 *
 * Two things have to hold. The run must finish regardless, because it is executing on a
 * worker that has never heard of the connection. And the replay that follows the reconnect
 * must not show a step twice: the server subscribes before it replays, so the tail of a
 * replay legitimately arrives on both sides of the seam.
 */

const PHOTOGRAPH = resolve(import.meta.dirname, "../../test_pics/20260810_105048.jpg");

test("finishes a run whose stream was cut, without repeating a step", async ({ page }) => {
  await signUp(page, "reconnect");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await expect(page.getByText("Checking the photographs")).toBeVisible();

  // The connection goes away mid-run, without the run being told. Chromium's own offline
  // switch rather than route interception: a route handler left open on a streaming
  // response holds the browser's request queue, and the next request — the answers — never
  // leaves. That looked exactly like a server hang, and was not one.
  await page.context().setOffline(true);
  await page.waitForTimeout(1_500);
  await page.context().setOffline(false);

  // The run carries on and reaches its pause, which is the whole point: the answer is that
  // the client reconnects and catches up, not that the run waited.
  await expect(page.getByLabel(/How often do you water/)).toBeVisible({ timeout: 60_000 });

  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });

  // Every step exactly once. A duplicate here is the replay overlapping the live stream,
  // and it would appear on precisely the reconnect that is meant to be invisible.
  const steps = await page
    .getByRole("region", { name: "What Plantopia is doing" })
    .getByRole("listitem")
    .allInnerTexts();
  expect(new Set(steps).size).toBe(steps.length);
  expect(steps.length).toBeGreaterThan(4);
});

test("recovers a run from a reload in the middle of it", async ({ page }) => {
  // The harder half of the same problem: after a reload there is no stream *and* no
  // component state. The run's identifier is in the address bar and everything else has to
  // be rebuilt from the server, which is what makes replay load-bearing rather than a nicety.
  await signUp(page, "reload-mid");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await expect(page.getByText("Checking the photographs")).toBeVisible();
  const url = page.url();
  expect(url).toContain("run=");

  await page.reload();

  // The steps that happened before the reload are still there, from the replay.
  await expect(page.getByText("Checking the photographs")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel(/How often do you water/)).toBeVisible({ timeout: 60_000 });
});
