import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";

/**
 * Registering, verifying and signing in — as a person does it, through the screens.
 *
 * The verification link is read from the mail sink the API writes (`tests/e2e/mail.py`)
 * rather than minted from the database, because the link itself is a thing this project has
 * had wrong twice: once pointing at a retired UI's port, and once spent by the screen
 * before the person clicked it.
 */

const SINK = resolve(import.meta.dirname, "../../tests/e2e/mail.jsonl");

/** A fresh address per test, so one test's account cannot decide another's outcome. */
export function someone(label: string): string {
  return `${label}-${process.pid}-${counter++}@example.com`;
}

let counter = 0;

export const PASSWORD = "a-long-enough-password";

/** The newest link sent to an address, waited for rather than assumed to have arrived. */
export async function linkSentTo(address: string, page: Page): Promise<string> {
  let found: string | null = null;

  await page.waitForFunction(() => true); // keeps the polling below on Playwright's clock
  for (let attempt = 0; attempt < 60 && !found; attempt += 1) {
    found = newestLink(address);
    if (!found) await page.waitForTimeout(250);
  }

  if (!found) throw new Error(`no message was sent to ${address}`);
  return found;
}

function newestLink(address: string): string | null {
  let lines: string[];
  try {
    lines = readFileSync(SINK, "utf8").trim().split("\n").filter(Boolean);
  } catch {
    return null; // Nothing has been sent yet at all.
  }

  for (const line of lines.reverse()) {
    const message = JSON.parse(line) as { to: string; body: string };
    if (message.to !== address) continue;
    const link = /https?:\/\/\S+/.exec(message.body);
    if (link) return link[0];
  }
  return null;
}

/** Register, verify and sign in. Returns the address, which is also the account's name. */
export async function signUp(page: Page, label = "someone"): Promise<string> {
  const address = someone(label);

  await page.goto("/register");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();

  const link = await linkSentTo(address, page);
  await page.goto(pathOf(link));
  await page.getByRole("link", { name: /sign in/i }).click();

  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Your plants" }).waitFor();

  return address;
}

/**
 * The path part of a link, so a test opens it on the server under test.
 *
 * The link is addressed to wherever `PLANTOPIA_APP_URL` points, which is a real port and
 * not the one Playwright started. Following it verbatim would either 404 or — worse — reach
 * a dev server somebody had open and pass against the wrong build.
 */
export function pathOf(link: string): string {
  const url = new URL(link);
  return `${url.pathname}${url.search}`;
}
