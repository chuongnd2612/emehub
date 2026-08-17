// The route map: the marketing landing view at `/`, the public auth routes,
// and the app shell at `/app` wrapping the pages the handoff describes. Each
// route points at one folder under `src/screens/`.
//
// The URL is the source of truth for navigation (CLAUDE.md › Frontend
// conventions). Nothing about "which page am I on" belongs in Zustand;
// intra-screen selection (active tab, ticket source, expanded row) goes in
// query params — `?tab=`, `?source=` — not here and not in the store. That
// holds for auth too: `RequireAuth` and `RedirectIfAuthed` express their
// decisions as `<Navigate>`, never as an imperative redirect.
//
// Three tiers:
//   • `/` and `/signed-out` — public and ungated. `/signed-out` is ungated on
//     purpose: logout lands there while the store may still say "authed".
//   • `/login`, `/forgot`, `/reset` — public, but `RedirectIfAuthed` bounces an
//     already-authenticated visitor into the app.
//   • `/app/*` — `RequireAuth` restores the session from the refresh cookie
//     before any child renders, and sends a dead session to `/login`.
//
// The unauthenticated screens live under `screens/Public/`, not
// `screens/auth/`: `screens/Auth/` is the in-app Authentication page, and on a
// case-insensitive filesystem those are the same directory (TS1261).

import { createBrowserRouter, Navigate } from "react-router-dom";

import AppLayout from "./screens/AppLayout";
import AuthScreen from "./screens/Auth";
import ClaudeScreen from "./screens/Claude";
import ForgotPasswordScreen from "./screens/Public/ForgotPassword";
import IntegrationsScreen from "./screens/Integrations";
import LandingScreen from "./screens/Landing";
import LoginScreen from "./screens/Public/Login";
import OverviewScreen from "./screens/Overview";
import ProfileScreen from "./screens/Profile";
import ProjectDetailScreen from "./screens/ProjectDetail";
import ProjectsScreen from "./screens/Projects";
import ResetPasswordScreen from "./screens/Public/ResetPassword";
import SettingsScreen from "./screens/Settings";
import SignedOutScreen from "./screens/Public/SignedOut";
import TicketDetailScreen from "./screens/TicketDetail";
import TicketsScreen from "./screens/Tickets";
import UsersScreen from "./screens/Users";
import { RedirectIfAuthed } from "./screens/RedirectIfAuthed";
import { RequireAuth } from "./screens/RequireAuth";

export const router = createBrowserRouter([
  // Marketing landing view — no app shell, no guard.
  { path: "/", element: <LandingScreen /> },

  // Public sign-in routes. An authenticated visitor is bounced to /app.
  {
    element: <RedirectIfAuthed />,
    children: [
      { path: "/login", element: <LoginScreen /> },
      { path: "/forgot", element: <ForgotPasswordScreen /> },
      { path: "/reset", element: <ResetPasswordScreen /> },
    ],
  },

  // Ungated: logout lands here and finalises the sign-out on mount.
  { path: "/signed-out", element: <SignedOutScreen /> },

  // The authenticated subtree. RequireAuth gates every route below it.
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/app",
        element: <AppLayout />,
        children: [
          { index: true, element: <OverviewScreen /> },
          { path: "projects", element: <ProjectsScreen /> },
          { path: "projects/:projectId", element: <ProjectDetailScreen /> },
          { path: "tickets", element: <TicketsScreen /> },
          // The provider is NOT a path segment: ticket identity is
          // `(providerKind, externalId)`, and putting the kind in the path would
          // make `/app/tickets/ado/1234` the canonical URL for a row whose
          // provider the caller may not know. It rides in `?source=` instead —
          // the same param the list uses — so the id stays the only path part
          // and an unqualified link still resolves.
          { path: "tickets/:externalId", element: <TicketDetailScreen /> },
          { path: "claude", element: <ClaudeScreen /> },
          { path: "auth", element: <AuthScreen /> },
          { path: "users", element: <UsersScreen /> },
          { path: "integrations", element: <IntegrationsScreen /> },
          { path: "profile", element: <ProfileScreen /> },
          { path: "settings", element: <SettingsScreen /> },
        ],
      },
    ],
  },

  // Anything else falls back to the landing view.
  { path: "*", element: <Navigate to="/" replace /> },
]);
