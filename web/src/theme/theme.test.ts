/**
 * The theme choice, and where it is remembered.
 *
 * A preference rather than data: it belongs to the browser, not the account, and losing it
 * on every reload is the kind of small wrongness that reads as carelessness.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apply, readTheme, resolve, storeTheme } from "@/theme/theme";

function systemPrefers(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: dark,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => vi.unstubAllGlobals());

describe("the theme choice", () => {
  it("follows the system when nothing has been chosen", () => {
    expect(readTheme()).toBe("system");
  });

  it("survives a reload", () => {
    storeTheme("dark");

    expect(readTheme()).toBe("dark");
  });

  it("returns to following the system when the choice is cleared", () => {
    storeTheme("dark");
    storeTheme("system");

    expect(readTheme()).toBe("system");
    expect(window.localStorage.getItem("plantopia-theme")).toBeNull();
  });

  it("ignores a stored value it does not recognise", () => {
    // Somebody's browser extension, or an older version of this application.
    window.localStorage.setItem("plantopia-theme", "chartreuse");

    expect(readTheme()).toBe("system");
  });
});

describe("resolving the choice", () => {
  it("reads the system preference when following it", () => {
    systemPrefers(true);

    expect(resolve("system")).toBe("dark");
  });

  it("ignores the system preference when a choice was made", () => {
    systemPrefers(true);

    expect(resolve("light")).toBe("light");
  });
});

describe("applying it", () => {
  it("marks the document for dark", () => {
    apply("dark");

    expect(document.documentElement).toHaveClass("dark");
  });

  it("unmarks it for light", () => {
    apply("dark");
    apply("light");

    expect(document.documentElement).not.toHaveClass("dark");
  });
});
