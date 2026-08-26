import { useCallback, useEffect, useState } from "react";

import { apply, readTheme, storeTheme, type Theme } from "@/theme/theme";

/**
 * The current theme, and a way to change it.
 *
 * Follows the system while the choice is "system", so somebody whose machine switches at
 * dusk sees the application switch with it rather than at their next reload.
 */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(readTheme);

  useEffect(() => {
    apply(theme);
    if (theme !== "system") return;

    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const follow = () => apply("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    storeTheme(next);
    setThemeState(next);
  }, []);

  return [theme, setTheme];
}
