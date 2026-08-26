import { BrowserRouter } from "react-router-dom";

import { QueryProvider } from "@/app/QueryProvider";
import { AuthProvider } from "@/auth/AuthProvider";
import { AppRoutes } from "@/routes/routes";

export function App() {
  return (
    <QueryProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryProvider>
  );
}
