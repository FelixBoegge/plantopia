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
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-md">
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
