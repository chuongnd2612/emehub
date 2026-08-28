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
  /**
   * Exact match only. `NavLink` matches on **prefix** by default, so any row
   * whose `to` is a prefix of a deeper real route needs this or it stays lit
   * on every page beneath it (#236).
   *
   * `/app` needs it because every route is beneath it. `/app/projects` needs it
   * because project detail is `/app/projects/:projectId/:tab` since #219 — and
   * the project's own row in the tree is the honest answer there, so two rows
   * lit at once was the visible symptom.
   *
   * `Unassigned` deliberately does NOT set it: a ticket at
   * `/app/unassigned/tickets/:externalId` really is inside the bucket.
   */
  end?: boolean;
}

export interface NavGroup {
  /** 10px/700/.12em tracked heading. */
  label: string;
  items: NavItem[];
  /**
   * Render the project tree inside this group, immediately after the item at
   * this index (#220). Only `WORKSPACE` has one, and it sits between Overview
   * and All projects — the order ADR 0011 §1 specifies.
   *
   * The tree is not a `NavItem`: its rows come from `GET /projects` at runtime,
   * so it cannot be a static entry in this table.
   */
  treeAfterIndex?: number;
}

/**
 * Two group headings. Order is the handoff's, as amended by containment.
 *
 * ## WORKSPACE is Overview → project tree → All projects (#220, ADR 0011 §1)
 *
 * The standalone `Tickets` entry is **gone**. A ticket belongs to a project and
 * arrives through the connection configured on that project, so presenting
 * Tickets as a sibling of Projects was a claim the domain does not make, and
 * clicking it threw a user out of the project they were in. Ticket-shaped data
 * now lives only inside its container.
 *
 * The workspace-wide question that entry used to answer is asked on Overview
 * instead — `screens/Overview/ProjectComparison.tsx` (#218), which is the guard
 * on this removal rather than decoration. Do not delete one without the other.
 *
 * ## …and then `Unassigned`, which is not a contradiction (#221)
 *
 * The last WORKSPACE row is the **Unassigned bucket** —
 * `/app/unassigned/tickets`, the work items whose `project_id` is NULL (#217,
 * ADR 0011 §4). Ticket-shaped data at workspace level looks like the very thing
 * containment removed, and it is the opposite: these rows belong to no project,
 * so a project-only information architecture is exactly what would make them
 * invisible. ADR 0011 §4 requires the bucket to be "explicit, visible, never
 * hidden, never guessed at", and an address nothing links to is hidden.
 *
 * It is **not** a row in the project tree, because the tree lists projects and
 * the bucket is not one. It is **not** conditional on holding something either:
 * a `0` here is an honest, useful answer — "nothing is unattributed" — and it can
 * only be read from a row that is there to read. The badge still follows
 * `useSidebarStats()`' rule: a count that could not be read renders no badge at
 * all, never a fabricated zero.
 *
 * `All projects` is the label the containment spec gives this row
 * (`docs/PROJECT-CONTAINMENT-HANDOFF.md` §1, ADR 0011 §1, #220) now that the
 * projects themselves are listed above it in the tree; the page's own header
 * copy stays "Projects & Repositories" (`ROUTE_HEADER`).
 *
 * ## PLATFORM is untouched
 *
 * Claude Settings, Authentication, User Management, Integrations and Settings
 * are workspace-level and correctly flat. Containment applies to ticket-shaped
 * data, not to platform administration (ADR 0011, "What we do not adopt").
 *
 * Badges are NOT declared here — the prototype hardcoded "6" / "128" / "3",
 * which drifts from reality the moment a project or ticket is added. They're
 * computed live in `Sidebar.tsx` via `useSidebarStats()` and keyed by `to`.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "WORKSPACE",
    treeAfterIndex: 0,
    items: [
      { to: "/app", label: "Overview", icon: "grid", end: true },
      { to: "/app/projects", label: "All projects", icon: "folder", end: true },
      { to: "/app/unassigned/tickets", label: "Unassigned", icon: "ticket" },
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
 *
 * Every key here is a **nav-addressable page**: the command palette lists this
 * table as its PAGES group. `/app/tickets` was removed from it with the nav
 * entry (#220) — there is no workspace-wide ticket page to jump to any more.
 * `/app/unassigned/tickets` is here for the opposite reason (#221): it has a nav
 * row of its own, so it is somewhere a user can genuinely jump to. Every other
 * ticket address wears `TICKET_HEADER`, below.
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
  // The Unassigned bucket (#221). It IS in this table — unlike `/app/tickets`,
  // which #220 removed — because it is a real, nav-addressable page again, and
  // the command palette's PAGES group should be able to reach it. The exact-path
  // lookup in `routeHeader` runs before the `TICKET_ROUTE` test, so the list
  // wears this header while `…/tickets/:externalId` beneath it still wears
  // `TICKET_HEADER`, which is the right answer for a ticket detail.
  "/app/unassigned/tickets": {
    title: "Unassigned work items",
    subtitle: "Work items that belong to no project",
  },
  "/app/claude": {
    title: "Claude Settings",
    subtitle: "Credentials and model selection",
  },
  "/app/auth": {
    title: "Authentication",
    subtitle: "Sessions and sign-in methods",
  },
  "/app/users": {
    title: "User Management",
    subtitle: "Members of this workspace",
  },
  "/app/integrations": {
    title: "Integrations",
    subtitle: "Azure DevOps, Jira and GitHub connections",
  },
  "/app/settings": {
    title: "Settings",
    subtitle: "Appearance and product availability",
  },
  // Not in the handoff's nav — the account screen has no design and is reached
  // from the sidebar user chip, not the nav list. It still needs a header.
  "/app/profile": {
    title: "Your account",
    subtitle: "Personal details, password and two-factor authentication",
  },
};

/**
 * Anything ticket-shaped, in either address it can now have (#219).
 *
 *   /app/tickets/1234                          the legacy flat link (a redirect)
 *   /app/projects/<id>/tickets[/1234]          nested under its project
 *   /app/unassigned/tickets[/1234]             the Unassigned bucket (#217)
 *
 * Kept as one expression so a new ticket address cannot be added without the
 * header following it — the failure mode this guards is a ticket page silently
 * wearing the Overview header while the nav says otherwise.
 */
const TICKET_ROUTE =
  /^\/app\/(tickets(\/|$)|(projects\/[^/]+|unassigned)\/tickets(\/|$))/;

/**
 * The header a ticket page wears, wherever it is addressed from.
 *
 * Deliberately NOT a `ROUTE_HEADER` entry: since #220 there is no
 * `/app/tickets` page to navigate to, and anything in that table shows up in
 * the command palette's PAGES group. The copy is unchanged — it is the
 * handoff's, and copy is final.
 */
export const TICKET_HEADER: HeaderContent = {
  title: "Tickets",
  subtitle: "Read-only mirror of Azure DevOps and Jira work items",
};

/**
 * Resolve the fallback header for a pathname.
 *
 * `/app/projects/:id/:tab` → Projects; anything ticket-shaped → Tickets. A
 * ticket page keeps the Tickets header wherever it is addressed from: without
 * this it fell all the way through to Overview, which reads as having navigated
 * away from the section.
 */
export function routeHeader(pathname: string): HeaderContent {
  const clean = pathname.replace(/\/+$/, "") || "/app";
  if (ROUTE_HEADER[clean]) return ROUTE_HEADER[clean];
  // Before the projects fallback: a project's ticket routes are Tickets pages,
  // not project pages, and `startsWith("/app/projects/")` would swallow them.
  if (TICKET_ROUTE.test(clean)) return TICKET_HEADER;
  if (clean.startsWith("/app/projects/")) return ROUTE_HEADER["/app/projects"];
  return ROUTE_HEADER["/app"];
}
