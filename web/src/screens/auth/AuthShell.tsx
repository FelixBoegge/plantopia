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
  return (
    <main className="grid min-h-svh place-items-center gap-6 p-6">
      {/* The whole lockup, wordmark and all, above the card rather than inside it. These
          screens are the first thing anybody sees, and until they sign in the header — the
          only other place the logo appears — is not on screen, so this is where the
          application gets to introduce itself.

          Decorative: the wordmark is a picture of the word and the heading below is the
          text. A screen reader should hear the application named once. */}
      <span aria-hidden="true" className="logo-lockup w-48 shrink-0 self-end" />

      <Card className="w-full max-w-md self-start">
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
        <CardContent className="grid gap-6">{children}</CardContent>
        {footer ? (
          <CardContent className="text-sm">{footer}</CardContent>
        ) : null}
      </Card>
    </main>
  );
}
