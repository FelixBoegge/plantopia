import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useTheme } from "@/theme/useTheme";

/** The frame every screen you can reach without a session shares. */
export function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  // Mounting this here is what applies the stored theme at all on these screens. The only
  // other caller is `AppHeader`, which does not render until there is a session — so
  // somebody who chose dark, signed out, and came back met a bright white front door. The
  // two callers never coexist (the signed-out screens and the header are mutually
  // exclusive) and both read the choice from `localStorage` on mount, so they cannot
  // disagree about it.
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";

  // The page carries a soft glow behind the card rather than a flat field of sage. Both
  // stops are existing theme tokens, so light and dark each get their own vignette and no
  // new colour value enters the palette — which also means the contrast measurements
  // recorded in `styles/index.css` still hold: every piece of text here sits on `--card`,
  // exactly as it did before.
  return (
    <main className="relative grid min-h-svh place-items-center gap-4 bg-[radial-gradient(circle_at_50%_0%,var(--card),var(--background)_60%)] p-4">
      {/* The whole lockup, wordmark and all, above the card rather than inside it. These
          screens are the first thing anybody sees, and until they sign in the header — the
          only other place the logo appears — is not on screen, so this is where the
          application gets to introduce itself.

          Full size wherever the tallest of these screens still fits without scrolling, and
          stepped down only where the alternative is a scrollbar. A height query rather
          than a width one: vertical space is what runs out here, and a 1366×768 laptop is
          wide and short. The thresholds are the measured page heights — registering is the
          tall one at 760 with the full lockup, 700 with the middle step.

          Decorative: the wordmark is a picture of the word and the heading below is the
          text. A screen reader should hear the application named once. */}
      <span
        aria-hidden="true"
        className="logo-lockup w-28 shrink-0 self-end [@media(min-height:700px)]:w-40 [@media(min-height:780px)]:w-56"
      />

      {/* Tighter than a card in the body of the application, for the same reason the
          lockup is smaller: this one has to fit above the fold on a short screen. */}
      <Card className="w-full max-w-md self-start shadow-xl shadow-foreground/5 [--card-spacing:--spacing(3)]">
        <CardHeader>
          {/* A real heading, not a styled div. It is the only h1 on the page and it is
              what a screen reader's heading navigation lands on. */}
          <CardTitle>
            <h1>{title}</h1>
          </CardTitle>
          {description ? (
            <CardDescription>{description}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-4">{children}</CardContent>
        {footer ? (
          <CardContent className="text-center text-sm">{footer}</CardContent>
        ) : null}
      </Card>

      {/* Drawn top right, where the header keeps it, so the control does not jump when
          somebody signs in — but last in the document, not first. Positioned absolutely,
          so where it appears owes nothing to where it sits here, and putting it first
          meant the opening Tab on the sign-in screen landed on a preference toggle instead
          of the email field. Signing in is what somebody came here to do; the theme can
          wait until the end of the tab order. The keyboard test in `accessibility.test.tsx`
          is what caught it. */}
      <Button
        variant="ghost"
        size="sm"
        className="absolute top-4 right-4"
        onClick={() => setTheme(dark ? "light" : "dark")}
        aria-pressed={dark}
      >
        {dark ? "Light mode" : "Dark mode"}
      </Button>
    </main>
  );
}
