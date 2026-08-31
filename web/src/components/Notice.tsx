import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Something the person needs to read.
 *
 * `role="alert"` on a failure, so it is announced rather than merely appearing — a form
 * that silently grows a red sentence is a form somebody using a screen reader submits twice.
 * A confirmation is `status`, which announces without interrupting.
 *
 * A caution is `status` too, deliberately. It appears and disappears as somebody edits a
 * field, and a role that interrupts would talk over them while they are still typing.
 */
export function Notice({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "caution" | "failure";
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <Alert
      role={tone === "failure" ? "alert" : "status"}
      variant={tone === "failure" ? "destructive" : "default"}
      className={
        tone === "caution"
          ? "border-amber-500/60 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
          : undefined
      }
    >
      {title ? <AlertTitle>{title}</AlertTitle> : null}
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
