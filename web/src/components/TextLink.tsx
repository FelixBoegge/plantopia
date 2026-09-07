import { Link, type LinkProps } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * A link that reads as prose until you point at it.
 *
 * Tailwind's Preflight resets an `a` to inherit both its colour and its text-decoration,
 * and nothing in the stylesheet puts either back — so a bare `<Link>` rendered as body
 * text and the hand cursor was the only clue it could be clicked at all. Resting state
 * stays deliberately quiet; the colour and the underline arrive on hover.
 *
 * Not a global `a` rule. `LinkButton` and the header's lockup are anchors too and neither
 * wants an underline, so the style belongs to the links meant to look like text.
 */
export function TextLink({ className, ...props }: LinkProps) {
  return (
    <Link
      className={cn(
        "font-medium underline-offset-4 transition-colors hover:text-primary hover:underline focus-visible:underline",
        className,
      )}
      {...props}
    />
  );
}
