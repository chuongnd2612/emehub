// The auth guard for the whole `/app/*` subtree.
//
// On first mount (`status === "idle"`) it kicks off `bootstrap()`, which
// exchanges the HttpOnly refresh cookie for an access token — this is what
// makes a hard reload keep you signed in. While that is in flight it renders
// the full-screen loader rather than flashing the login screen at someone who
// is in fact signed in. A dead session renders `<Navigate to="/login">`; the
// URL stays the source of truth and nothing navigates imperatively, so a
// refresh failure cannot put the app in a redirect loop.

import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AuthLoader } from "@/components/auth/AuthLayout";
import { useAuth } from "@/store/auth";

export function RequireAuth() {
  const status = useAuth((s) => s.status);
  const bootstrap = useAuth((s) => s.bootstrap);
  const location = useLocation();

  useEffect(() => {
    if (status === "idle") void bootstrap();
  }, [status, bootstrap]);

  if (status === "idle" || status === "loading") return <AuthLoader />;

  if (status === "anon") {
    // Carry where they were headed so a successful sign-in can return them.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }

  return <Outlet />;
}
