import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { signUp } from "./people";

/**
 * Asking about a plant, and being told what the answer was built from.
 *
 * A reply that consulted the disorder reference and one the model produced from its own
 * memory look identical on the screen. Only one of them is worth trusting about a plant
 * somebody is worried about, so the lookup is announced while it happens and recorded on the
 * reply afterwards — and those two are drawn from different sources on different sides of
 * the wire, which is why they are checked here rather than only in a component test.
 */

const PHOTOGRAPH = resolve(import.meta.dirname, "../../test_pics/20260810_105048.jpg");

/** A plant to talk about. Chat is per-plant, so one has to exist first. */
async function aPlantWithADiagnosis(page: import("@playwright/test").Page, name: string) {
  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Photographs").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("What is it called?").fill(name);
  await page.getByRole("button", { name: "Start the check" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();
  await page
    .getByRole("heading", { name: "What this looks like" })
    .waitFor({ timeout: 60_000 });

  await page.getByRole("link", { name: "Plantopia" }).click();
  await page.getByText(name).click();
  await page.getByRole("heading", { name }).waitFor();
}

test("announces the lookup before the reply arrives", async ({ page }) => {
  await signUp(page, "chat");
  await aPlantWithADiagnosis(page, "Talkative basil");

  const announcement = page
    .getByRole("region", { name: "Ask about this plant" })
    .locator("[aria-live='polite']");

  await page.getByLabel("Your question").fill("Why are the lower leaves yellow?");
  await page.getByRole("button", { name: "Ask" }).click();

  // While it is working, and in words — not a spinner. This is the half a person can act
  // on: it says the answer is being built from the reference rather than from memory.
  await expect(announcement).toContainText("the disorder reference", { timeout: 60_000 });

  // And the reply itself, once it lands.
  await expect(page.getByText(/Let the top third dry out/)).toBeVisible({ timeout: 60_000 });
});

test("keeps what a reply consulted, on the reply", async ({ page }) => {
  // The announcement is transient; the record is not. A transcript reloaded tomorrow must
  // still say what the answer was built from, and that comes from the stored messages rather
  // than from the stream that produced them.
  await signUp(page, "chat-record");
  await aPlantWithADiagnosis(page, "Remembered basil");

  await page.getByLabel("Your question").fill("Why are the lower leaves yellow?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText(/Let the top third dry out/)).toBeVisible({ timeout: 60_000 });

  await page.reload();

  await expect(page.getByText(/Let the top third dry out/)).toBeVisible();
  await expect(page.getByText("the disorder reference")).toBeVisible();
});
