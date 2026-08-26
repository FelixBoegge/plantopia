import { Link, type LinkProps } from "react-router-dom";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A link that looks like a button.
 *
 * An `<a>`, not a button with an onClick. Middle-click, open in a new tab, copy the
 * address, and everything else a browser already knows how to do with a link keep working —
 * and none of it does when navigation is a click handler on a styled element.
 */
export function LinkButton({
  className,
  variant,
  size,
  ...props
}: LinkProps & Parameters<typeof buttonVariants>[0]) {
  return (
    <Link
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
