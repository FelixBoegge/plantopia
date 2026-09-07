import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/index.css";
import { App } from "@/App";
import { apply, readTheme } from "@/theme/theme";

// Before the first paint, not in an effect. `useTheme` applies the choice from a
// `useEffect`, which React runs *after* the browser has painted — so a dark-mode reader
// saw a white flash on every load. Reading `localStorage` synchronously here costs nothing
// and the correct theme is on the element before anything is drawn.
apply(readTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
