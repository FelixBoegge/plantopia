import { Navigate, Route, Routes } from "react-router-dom";

import { RequireSession } from "@/auth/RequireSession";

/**
 * Every screen, and which of them need a session.
 *
 * One file, so that "what is behind a session" is a question with one answer rather than a
 * property distributed across a dozen components.
 */

function Placeholder({ name }: { name: string }) {
  return <h1>{name}</h1>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Placeholder name="Sign in" />} />
      <Route path="/register" element={<Placeholder name="Register" />} />
      <Route path="/verify-email" element={<Placeholder name="Verify your address" />} />
      <Route path="/reset-password" element={<Placeholder name="Reset your password" />} />

      <Route element={<RequireSession />}>
        <Route path="/" element={<Placeholder name="Your plants" />} />
        <Route path="/plants/:plantId" element={<Placeholder name="Plant" />} />
        <Route path="/plants/:plantId/diagnose" element={<Placeholder name="Diagnose" />} />
        <Route path="/diagnose" element={<Placeholder name="Diagnose" />} />
        <Route path="/account" element={<Placeholder name="Your account" />} />
        <Route path="/admin/evaluation" element={<Placeholder name="Evaluation" />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
