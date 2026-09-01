import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { signUp } from "./people";

/**
 * What a photograph says about itself, and what the run does with it.
 *
 * The photographs under `test_pics/` carry a real capture date and — since their GPS was
 * stripped on 2026-08-26 — no position. That is the ordinary shape of an upload: most
 * photographs have been through something that removed the location and kept the date.
 */

const PHOTOGRAPH = resolve(import.meta.dirname, "../../test_pics/20260810_105048.jpg");

async function startedFrom(page: import("@playwright/test").Page, name: string, outdoors = false) {
  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  if (outdoors) await page.getByRole("radio", { name: "Outdoors" }).check();
  await page.getByRole("button", { name: "Start the diagnosis" }).click();
}

test("nobody is asked where the plant is before the run starts", async ({ page }) => {
  // The photograph usually knows, and asking somebody to type what the file already says is
  // asking them to do the machine's work.
  await signUp(page, "no-location-upfront");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();

  await expect(page.getByRole("button", { name: "Start the diagnosis" })).toBeVisible();
  await expect(page.getByLabel(/Roughly where/)).toHaveCount(0);
  await expect(page.getByLabel(/Which town or city/)).toHaveCount(0);
});

test("the date the camera recorded is in the field, and can be corrected", async ({ page }) => {
  await signUp(page, "dated");
  await startedFrom(page, "Dated basil");

  const taken = page.getByLabel(/When was the photograph taken/);
  await expect(taken).toBeVisible({ timeout: 60_000 });

  // The real capture date of the committed photograph.
  await expect(taken).toHaveValue("2026-08-10");
  await expect(page.getByText("Recorded by your camera")).toBeVisible();

  await taken.fill("2026-08-05");
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
});

test("an outdoor plant cannot go on without a place", async ({ page }) => {
  // The photograph carries no position — its GPS was stripped — so the field is empty, and
  // outdoors that is the half of the answer weather explains.
  await signUp(page, "outdoors");
  await startedFrom(page, "Outdoor basil", true);

  const where = page.getByLabel(/Which town or city/);
  await expect(where).toBeVisible({ timeout: 60_000 });
  await expect(where).toHaveValue("");

  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  // Refused, and said so where the field is rather than as a sentence somewhere else.
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "A couple of questions" })).toBeVisible();

  await where.fill("Berlin");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
});

test("an indoor plant can go on without one", async ({ page }) => {
  // Indoors the connection to weather is weak enough that demanding a place would be
  // demanding it for nothing.
  await signUp(page, "indoors");
  await startedFrom(page, "Indoor basil");

  await expect(page.getByLabel(/Which town or city/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel(/Which town or city/)).toHaveValue("");

  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
});

test("a photograph old enough to mislead says so, and the run carries on anyway", async ({
  page,
}) => {
  // The committed photograph was taken on 2026-08-10 and only gets older, so this is stale
  // by any threshold the deployment might set and will stay stale.
  await signUp(page, "stale");
  await startedFrom(page, "Old basil");

  const taken = page.getByLabel(/When was the photograph taken/);
  await expect(taken).toBeVisible({ timeout: 60_000 });

  const warning = page.getByText(/days old/);
  await expect(warning).toBeVisible();
  await expect(warning).toContainText(/less reliable/);
  await expect(warning).toContainText(/upload one taken today/);

  // Correcting the date corrects the verdict: the warning follows the field rather than the
  // metadata, because somebody who knows the camera's clock is wrong has just said so.
  const today = new Date().toISOString().slice(0, 10);
  await taken.fill(today);
  await expect(page.getByText(/days old/)).toHaveCount(0);

  // And back again — it is not a one-way door somebody can dismiss by touching the field.
  await taken.fill("2026-08-10");
  await expect(page.getByText(/days old/)).toBeVisible();

  // A caution, not a gate. Somebody whose plant died last week and who has only last week's
  // photograph is exactly who needs an answer.
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
});
