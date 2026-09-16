import type { ReactNode } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
  // The background art already carries the Plantopia mark and is a light watercolour
  // illustration. There is no theme toggle here any more — `.light` (in
  // `styles/index.css`) pins these screens to the light tokens regardless of a dark
  // preference chosen while signed in, so a stored choice never leaves a dark card
  // floating on the light artwork. Switching back to dark still works from `AppHeader`
  // once somebody is signed in.
  return (
    <main className="light grid h-svh grid-rows-[calc(33.5svh_-_0.5cm)_1fr] overflow-hidden bg-[url('/auth-background.png')] bg-cover bg-center p-4">
      {/* An empty spacer fixing the card's top edge at the same height on every one of
          these screens — Register (the tallest) sat here when centered in the space
          below the wordmark, and the rest are pinned to match rather than each centering
          on its own height. The `- 0.5cm` pulls every card up that same fixed amount,
          closer to the wordmark above. `h-svh` + `overflow-hidden` on `main` fix the
          page to exactly the viewport: it never scrolls. */}
      <div aria-hidden="true" />

      {/* `items-start`, not `place-items-center`: the card's top is fixed by the row
          above, not re-centered per screen. `min-h-0` overrides grid's default
          `min-height: auto` on this row, which would otherwise force the `1fr` track to
          grow to the card's full height on a short screen — exactly the scrolling this
          layout exists to rule out. With it, the row holds still and this scrolls
          internally instead. */}
      <div className="grid min-h-0 items-start justify-items-center overflow-y-auto">
        {/* `bg-card/90`: the card's own usual colour (a light sage, warmed toward green
            in `.light`'s `--card` to cut the blue cast it had at this hue) at partial
            opacity, rather than the much darker `--primary` — lighter, and closer to the
            background than a brand-green tint. */}
        <Card className="w-full max-w-md bg-card/90 shadow-2xl shadow-black/50 [--card-spacing:--spacing(3)]">
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
      </div>
    </main>
  );
}
