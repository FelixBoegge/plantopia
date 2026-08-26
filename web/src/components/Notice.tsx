import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Something the person needs to read.
 *
 * `role="alert"` on a failure, so it is announced rather than merely appearing — a form
 * that silently grows a red sentence is a form somebody using a screen reader submits twice.
 * A confirmation is `status`, which announces without interrupting.
 */
export function Notice({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "failure";
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <Alert
      role={tone === "failure" ? "alert" : "status"}
      variant={tone === "failure" ? "destructive" : "default"}
    >
      {title ? <AlertTitle>{title}</AlertTitle> : null}
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
