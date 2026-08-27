// The route map: the marketing landing view at `/`, the public auth routes,
// and the app shell at `/app` wrapping the pages the handoff describes. Each
// route points at one folder under `src/screens/`.
//
// The URL is the source of truth for navigation (CLAUDE.md › Frontend
// conventions). Nothing about "which page am I on" belongs in Zustand;
// intra-screen selection (a filter, an expanded row) goes in query params — not
// here and not in the store. That holds for auth too: `RequireAuth` and
// `RedirectIfAuthed` express their decisions as `<Navigate>`, never as an
// imperative redirect.
//
// ## Project containment (#219, ADR 0011 §1)
//
// The project is the container, so the ticket routes nest inside it and the
// project's tab is a PATH SEGMENT rather than `?tab=`:
//
//   /app/projects/:projectId/(overview|knowledge|repos|agents|settings)
//   /app/projects/:projectId/tickets/:externalId
//   /app/unassigned/tickets/:externalId      — the Unassigned bucket (#217)
//
// `?tab=` was right while a tab was intra-screen selection; once a tab is a
// distinct view of a distinct resource, it is a path. The tab route is `:tab`
// and not a list of literals on purpose: `PROJECT_TABS` in
// `screens/ProjectDetail/shared.ts` stays the single source for the vocabulary,
// so a new tab there needs no change here. `tickets` is reserved in that same
// table for #221's project-scoped list.
//
// The flat `/app/tickets` and `/app/tickets/:externalId` are kept as REDIRECTS
// so saved links and bookmarks survive, and both still accept `?source=` —
// which is load-bearing on a ticket link, since identity is
// `(providerKind, externalId)`. The list redirect lands on `/app/projects`: with
// containment there is no workspace-wide ticket list to send it to any more, and
// choosing the container is the step that replaced it.
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
import ProjectTabRedirect from "./screens/ProjectDetail/TabRedirect";
import ProjectsScreen from "./screens/Projects";
import ResetPasswordScreen from "./screens/Public/ResetPassword";
import SettingsScreen from "./screens/Settings";
import ComingSoonScreen from "./screens/Public/ComingSoon";
import SignedOutScreen from "./screens/Public/SignedOut";
import TicketDetailScreen from "./screens/TicketDetail";
import LegacyTicketRedirect from "./screens/TicketDetail/LegacyTicketRedirect";
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

  // Ungated: the edge sends anyone here who asks for an agent that is turned
  // off (#186), and that visitor may have no hub session at all.
  { path: "/coming-soon/:key", element: <ComingSoonScreen /> },

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
          {
            path: "projects/:projectId",
            children: [
              // A bare project URL is not a view — it resolves once to the
              // default tab, and absorbs a legacy `?tab=` on the way.
              { index: true, element: <ProjectTabRedirect /> },
              { path: ":tab", element: <ProjectDetailScreen /> },
              // The provider is NOT a path segment: ticket identity is
              // `(providerKind, externalId)`, and putting the kind in the path
              // would make `…/tickets/ado/1234` the canonical URL for a row
              // whose provider the caller may not know. It rides in `?source=`
              // instead, so the id stays the only path part and an unqualified
              // link still resolves.
              {
                path: "tickets/:externalId",
                element: <TicketDetailScreen />,
              },
            ],
          },

          // The Unassigned bucket (#217) — tickets that belong to no project.
          // Not inside any project, so it has its own workspace-level address
          // rather than a fake project id. #221 renders the list here, backed by
          // `GET /tickets?unassigned=true`.
          {
            path: "unassigned/tickets/:externalId",
            element: <TicketDetailScreen />,
          },

          // Legacy, redirect-only. See the header comment.
          { path: "tickets", element: <Navigate to="/app/projects" replace /> },
          { path: "tickets/:externalId", element: <LegacyTicketRedirect /> },
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
