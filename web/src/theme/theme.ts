/**
 * Light, dark, or whatever the operating system says.
 *
 * The choice is the one thing here worth persisting: it is a preference rather than data,
 * it belongs to the browser rather than the account, and losing it on every reload is the
 * kind of small wrongness that reads as carelessness.
 */

export type Theme = "light" | "dark" | "system";

const KEY = "plantopia-theme";

export function readTheme(): Theme {
  const stored = window.localStorage.getItem(KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

export function storeTheme(theme: Theme): void {
  if (theme === "system") {
    window.localStorage.removeItem(KEY);
    return;
  }
  window.localStorage.setItem(KEY, theme);
}

/** Whether dark should be applied, resolving "system" against the browser. */
export function resolve(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function apply(theme: Theme): void {
  document.documentElement.classList.toggle("dark", resolve(theme) === "dark");
}
