// The route map: the marketing landing view at `/`, and the app shell at
// `/app` wrapping the eight pages the handoff describes. Each route points at
// one folder under `src/screens/`.
//
// The URL is the source of truth for navigation (CLAUDE.md › Frontend
// conventions). Nothing about "which page am I on" belongs in Zustand;
// intra-screen selection (active tab, ticket source, expanded row) goes in
// query params — `?tab=`, `?source=` — not here and not in the store.

import { createBrowserRouter, Navigate } from "react-router-dom";

import AppLayout from "./screens/AppLayout";
import AuthScreen from "./screens/Auth";
import ClaudeScreen from "./screens/Claude";
import IntegrationsScreen from "./screens/Integrations";
import LandingScreen from "./screens/Landing";
import OverviewScreen from "./screens/Overview";
import ProjectDetailScreen from "./screens/ProjectDetail";
import ProjectsScreen from "./screens/Projects";
import SettingsScreen from "./screens/Settings";
import TicketsScreen from "./screens/Tickets";
import UsersScreen from "./screens/Users";

export const router = createBrowserRouter([
  // Marketing landing view — no app shell.
  { path: "/", element: <LandingScreen /> },

  // The app shell wraps every /app page.
  {
    path: "/app",
    element: <AppLayout />,
    children: [
      { index: true, element: <OverviewScreen /> },
      { path: "projects", element: <ProjectsScreen /> },
      { path: "projects/:projectId", element: <ProjectDetailScreen /> },
      { path: "tickets", element: <TicketsScreen /> },
      { path: "claude", element: <ClaudeScreen /> },
      { path: "auth", element: <AuthScreen /> },
      { path: "users", element: <UsersScreen /> },
      { path: "integrations", element: <IntegrationsScreen /> },
      { path: "settings", element: <SettingsScreen /> },
    ],
  },

  // Anything else falls back to the landing view.
  { path: "*", element: <Navigate to="/" replace /> },
]);
