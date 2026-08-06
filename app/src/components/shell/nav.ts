// Handoff § 0. App shell › Sidebar › Nav, and the prototype's `META` table of
// page titles/subtitles.
//
// The URL is the source of truth for navigation (CLAUDE.md › Frontend
// conventions), so the nav is a list of routes rendered with <NavLink>. There
// is no `page` in the store and there must never be one.

import type { IconName } from "@/components/ui";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Exact match only — used by the index route. */
  end?: boolean;
}

export interface NavGroup {
  /** 10px/700/.12em tracked heading. */
  label: string;
  items: NavItem[];
}

/**
 * One flat list under two group headings. Order is the handoff's.
 *
 * Badges are NOT declared here — the prototype hardcoded "6" / "128" / "3",
 * which drifts from reality the moment a project or ticket is added. They're
 * computed live in `Sidebar.tsx` via `useSidebarStats()` and keyed by `to`.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "WORKSPACE",
    items: [
      { to: "/app", label: "Overview", icon: "grid", end: true },
      { to: "/app/projects", label: "Projects & Repositories", icon: "folder" },
      { to: "/app/tickets", label: "Tickets", icon: "ticket" },
    ],
  },
  {
    label: "PLATFORM",
    items: [
      { to: "/app/claude", label: "Claude Settings", icon: "cpu" },
      { to: "/app/auth", label: "Authentication", icon: "shield" },
      { to: "/app/users", label: "User Management", icon: "users" },
      { to: "/app/integrations", label: "Integrations", icon: "plug" },
      { to: "/app/settings", label: "Settings", icon: "gear" },
    ],
  },
];

export interface HeaderContent {
  title: string;
  subtitle: string;
}

/**
 * The prototype's `META` table, keyed by route instead of by `page`. This is
 * the FALLBACK only — a screen that calls `useHeader()` overrides it.
 * Copy is final (CLAUDE.md › Design › Rules).
 */
export const ROUTE_HEADER: Record<string, HeaderContent> = {
  "/app": {
    title: "Overview",
    subtitle: "Command center for every EMESOFT agent",
  },
  "/app/projects": {
    title: "Projects & Repositories",
    subtitle: "Repositories, connected agents and per-project defaults",
  },
  "/app/tickets": {
    title: "Tickets",
    subtitle: "Read-only mirror of Azure DevOps and Jira work items",
  },
  "/app/claude": {
    title: "Claude Settings",
    subtitle: "Credentials, models and agent behaviour",
  },
  "/app/auth": {
    title: "Authentication",
    subtitle: "Sessions and sign-in methods",
  },
  "/app/users": {
    title: "User Management",
    subtitle: "Members, roles and pending invitations",
  },
  "/app/integrations": {
    title: "Integrations",
    subtitle: "Azure DevOps, Jira and GitHub connections",
  },
  "/app/settings": {
    title: "Settings",
    subtitle: "Appearance, workspace defaults and notifications",
  },
  // Not in the handoff's nav — the account screen has no design and is reached
  // from the sidebar user chip, not the nav list. It still needs a header.
  "/app/profile": {
    title: "Your account",
    subtitle: "Personal details, password and two-factor authentication",
  },
};

/** Resolve the fallback header for a pathname (`/app/projects/:id` → Projects). */
export function routeHeader(pathname: string): HeaderContent {
  const clean = pathname.replace(/\/+$/, "") || "/app";
  if (ROUTE_HEADER[clean]) return ROUTE_HEADER[clean];
  if (clean.startsWith("/app/projects/")) return ROUTE_HEADER["/app/projects"];
  return ROUTE_HEADER["/app"];
}
