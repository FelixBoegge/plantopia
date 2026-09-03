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

const PHOTOGRAPH = resolve(
  import.meta.dirname,
  "../../test_pics/20260810_105048.jpg",
);

/** A plant to talk about. Chat is per-plant, so one has to exist first. */
async function aPlantWithADiagnosis(
  page: import("@playwright/test").Page,
  name: string,
) {
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Diagnose a plant" })
    .click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();
  await page
    .getByRole("heading", { name: "What this looks like" })
    .waitFor({ timeout: 60_000 });

  await page.getByRole("link", { name: "Plantopia" }).click();
  // Named by the identification rather than by anybody: the scripted vision model says
  // "Basil", and `name` is now only what this test calls the run.
  await page.getByText("Basil").first().click();
  await page.getByRole("heading", { name: "Basil" }).waitFor();

  // The conversation is its own page now, reached from the plant rather than sitting
  // beside it.
  await page.getByRole("link", { name: "Chat about this plant" }).click();
  await page.getByLabel("Your question").waitFor();
}

test("announces the lookup before the reply arrives", async ({ page }) => {
  await signUp(page, "chat");
  await aPlantWithADiagnosis(page, "Talkative basil");

  const announcement = page
    .getByRole("region", { name: "Ask about this plant" })
    .locator("[aria-live='polite']");

  await page
    .getByLabel("Your question")
    .fill("Why are the lower leaves yellow?");
  await page.getByRole("button", { name: "Ask" }).click();

  // While it is working, and in words — not a spinner. This is the half a person can act
  // on: it says the answer is being built from the reference rather than from memory.
  await expect(announcement).toContainText("disorder reference", {
    timeout: 60_000,
  });

  // And the reply itself, once it lands.
  await expect(page.getByText(/Let the top third dry out/)).toBeVisible({
    timeout: 60_000,
  });
});

test("keeps what a reply consulted, on the reply", async ({ page }) => {
  // The announcement is transient; the record is not. A transcript reloaded tomorrow must
  // still say what the answer was built from, and that comes from the stored messages rather
  // than from the stream that produced them.
  await signUp(page, "chat-record");
  await aPlantWithADiagnosis(page, "Remembered basil");

  await page
    .getByLabel("Your question")
    .fill("Why are the lower leaves yellow?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText(/Let the top third dry out/)).toBeVisible({
    timeout: 60_000,
  });

  await page.reload();

  await expect(page.getByText(/Let the top third dry out/)).toBeVisible();
  await expect(page.getByText("disorder reference")).toBeVisible();
});

test("announces the weather lookup, and answers from what the diagnosis saw", async ({
  page,
}) => {
  // A different tool from the one above, and the one worth watching separately: it reads
  // the series stored against the observation rather than fetching, which is what keeps the
  // answer consistent with the diagnosis that was made against those days.
  await signUp(page, "chat-weather");

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Diagnose a plant" })
    .click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("radio", { name: "Outdoors" }).check();
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  // Outdoors the place is required, and it is what makes weather part of this run at all.
  await page.getByLabel(/Which town or city/).fill("Berlin");
  await page.getByRole("button", { name: "Carry on" }).click();
  await page
    .getByRole("heading", { name: "What this looks like" })
    .waitFor({ timeout: 60_000 });

  await page.getByRole("link", { name: "Plantopia" }).click();
  await page.getByText("Basil").first().click();
  await page.getByRole("heading", { name: "Basil" }).waitFor();

  // The conversation is its own page now, reached from the plant rather than sitting
  // beside it — the same step `aPlantWithADiagnosis` takes above.
  await page.getByRole("link", { name: "Chat about this plant" }).click();
  await page.getByLabel("Your question").waitFor();

  const announcement = page
    .getByRole("region", { name: "Ask about this plant" })
    .locator("[aria-live='polite']");

  await page
    .getByLabel("Your question")
    .fill("What has the weather been doing?");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(announcement).toContainText("the weather where this plant is", {
    timeout: 60_000,
  });

  await expect(page.getByText(/There was a frost/)).toBeVisible({
    timeout: 60_000,
  });
});
