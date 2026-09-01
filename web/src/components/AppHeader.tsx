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
        className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-3"
      >
        <Link to="/" className="font-semibold underline-offset-4 hover:underline">
          Plantopia
        </Link>
        <div className="flex-1" />
        <Link to="/diagnose" className="underline-offset-4 hover:underline">
          Diagnose a plant
        </Link>
        {account?.role === "admin" ? (
          <Link to="/admin/evaluation" className="underline-offset-4 hover:underline">
            Evaluation
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
