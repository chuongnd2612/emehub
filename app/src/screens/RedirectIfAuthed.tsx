// The inverse of `RequireAuth`: guards the public sign-in routes (`/login`,
// `/forgot`, `/reset`) so an already-authenticated visitor cannot sit on them.
//
// It bootstraps on first mount for the same reason `RequireAuth` does — a typed
// URL or a hard reload while a live refresh cookie exists should land in the
// app, not on a sign-in form.
//
// NOT applied to `/signed-out`: logout intentionally lands there while the
// store may still say "authed", and clears the session on mount. Guarding it
// would bounce the user straight back into the app.
//
// The `arrivedAnon` latch stops this guard hijacking an in-progress sign-in.
// Once we have seen the visitor arrive unauthenticated we let them stay on the
// auth screen even after they authenticate here, so `Login` keeps ownership of
// its own post-login navigation and its redirect animation. Without it, the
// anon → authed transition from signing in on this very page would fire our
// redirect mid-animation.

import { useEffect, useRef } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { AuthLoader } from "@/components/auth/AuthLayout";
import { useAuth } from "@/store/auth";

export function RedirectIfAuthed() {
  const status = useAuth((s) => s.status);
  const bootstrap = useAuth((s) => s.bootstrap);

  useEffect(() => {
    if (status === "idle") void bootstrap();
  }, [status, bootstrap]);

  const arrivedAnon = useRef(false);
  if (status === "anon") arrivedAnon.current = true;

  if (status === "idle" || status === "loading") return <AuthLoader />;
  if (status === "authed" && !arrivedAnon.current) {
    return <Navigate to="/app" replace />;
  }

  return <Outlet />;
}
