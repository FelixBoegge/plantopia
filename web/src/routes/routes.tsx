import { Navigate, Route, Routes } from "react-router-dom";

import { RequireSession } from "@/auth/RequireSession";
import { Register } from "@/screens/auth/Register";
import { ResetPassword } from "@/screens/auth/ResetPassword";
import { SignIn } from "@/screens/auth/SignIn";
import { VerifyEmail } from "@/screens/auth/VerifyEmail";
import { SignedIn } from "@/screens/SignedIn";
import { PlantDetail } from "@/screens/plants/PlantDetail";
import { Plants } from "@/screens/plants/Plants";
import { Wizard } from "@/screens/wizard/Wizard";

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
      <Route path="/login" element={<SignIn />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      <Route element={<RequireSession />}>
        <Route element={<SignedIn />}>
          <Route path="/" element={<Plants />} />
          <Route path="/plants/:plantId" element={<PlantDetail />} />
          <Route path="/plants/:plantId/diagnose" element={<Wizard />} />
          <Route path="/diagnose" element={<Wizard />} />
          <Route
            path="/account"
            element={<Placeholder name="Your account" />}
          />
          <Route
            path="/admin/evaluation"
            element={<Placeholder name="Evaluation" />}
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
