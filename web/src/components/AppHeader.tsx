import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/theme/useTheme";

/**
 * The bar every signed-in screen carries.
 *
 * A `nav` with real links, not click handlers on styled divs: middle-click, open in a new
 * tab, and everything a browser already knows how to do with a link keep working.
 */
export function AppHeader() {
  const { account, signOut } = useAuth();
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";

  return (
    <header className="border-b">
      <nav
        aria-label="Main"
        // Matches the main column, or the wordmark and the content below it do not line up.
        className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-3"
      >
        <Link
          to="/"
          className="flex items-center gap-2.5 text-lg font-semibold underline-offset-4 hover:underline"
        >
          {/* Decorative: the word beside it already says what this is, and a screen reader
              announcing "Plantopia Plantopia" is worse than one that says it once. */}
          {/* 40px. The mark carries a speech bubble, two leaves, a stem and a magnifier,
              and below about this size it stops being a drawing and becomes a smudge. The
              wordmark is sized up with it so the two read as one lockup rather than as a
              picture that happens to sit near some text. */}
          <span aria-hidden="true" className="logo-mark size-10 shrink-0" />
          Plantopia
        </Link>
        <div className="flex-1" />
        {/* Diagnosing comes first: it is what somebody opens this to do, and the list of
            plants is where they end up afterwards. The wordmark also leads to that list,
            but a wordmark is not a signpost — nobody should have to guess that the logo is
            the way back. */}
        <Link to="/diagnose" className="underline-offset-4 hover:underline">
          Diagnose a plant
        </Link>
        <Link to="/" className="underline-offset-4 hover:underline">
          My plants
        </Link>
        {/* Shown on the server's answer, never on the role beside it. `account.role` is
            right here and the rule derived from it was not: comparing it to "admin" was a
            second copy of an authorization rule, and it went on hiding this link after a
            deployment opened the page to members — the page reachable, the way to it
            invisible. `may_read_evaluations` is computed with the same function the
            endpoint refuses by, so a link shown is a link that works. */}
        {account?.may_read_evaluations ? (
          <Link
            to="/admin/evaluation"
            className="underline-offset-4 hover:underline"
          >
            RAG Evaluation Report
          </Link>
        ) : null}
        <Link to="/account" className="underline-offset-4 hover:underline">
          Account
        </Link>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setTheme(dark ? "light" : "dark")}
          aria-pressed={dark}
        >
          {dark ? "Light mode" : "Dark mode"}
        </Button>
        <Button variant="outline" size="sm" onClick={() => void signOut()}>
          Sign out
        </Button>
      </nav>
    </header>
  );
}
