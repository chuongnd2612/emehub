// The sidebar's nav badges, project tree and footer status line were hardcoded
// ("6", "128", "3", "3 integrations connected · 2 agents online") straight from
// the prototype's fixtures. This hook replaces them with real counts from the
// same endpoints the owning screens already call, so the sidebar can never
// disagree with the page it links to.
//
// ## Per-project counts (#220)
//
// The tree needs one count per project row, not one workspace-wide total, so
// this hook reads `getTicketCounts()` — `GET /projects/ticket-counts` (#217),
// the ONE counting path in the app. The Overview comparison table (#218) and
// the Project › Tickets tab (#221) read the same function, which is the point:
// no screen counts its own way (`docs/PROJECT-CONTAINMENT-HANDOFF.md` §3).
//
// The workspace-wide `ticketCount` this hook used to expose went with the
// standalone Tickets nav entry it fed. Nothing at workspace level is
// ticket-shaped any more (ADR 0011 §1); `TicketCounts.total` still carries the
// figure for anything that genuinely needs it.

import { useEffect, useState } from "react";

import { getConnections } from "@/data/connections";
import { getProjects, getTicketCounts } from "@/data/projects";
import type { Project, TicketCounts } from "@/data";

export interface SidebarStats {
  /**
   * The rows of the project tree, or `null` when the read failed. An empty
   * array is a different fact — this workspace has no projects — and the tree
   * renders its empty state for that, never for a failure.
   */
  projects: Project[] | null;
  projectCount: number | null;
  /**
   * Per-project ticket counts, `null` when the read failed or has not landed.
   * Read one project's count out of it with `ticketCountFor(counts, rowId)`,
   * which keeps the tri-state: a number, `undefined` for "this project holds no
   * tickets", `null` for "unavailable". Never collapse those with `?? 0`.
   */
  ticketCounts: TicketCounts | null;
  connectionCount: number | null;
  loading: boolean;
}

const EMPTY: SidebarStats = {
  projects: null,
  projectCount: null,
  ticketCounts: null,
  connectionCount: null,
  loading: true,
};

/**
 * `null` means "not loaded yet or failed" — the caller renders no badge
 * rather than a stale or invented number. A failed count must never fall
 * back to a fixture, and must never fall back to `0` either: `0` is a claim
 * that the project holds no tickets, which a failed read cannot make.
 */
export function useSidebarStats(): SidebarStats {
  const [stats, setStats] = useState<SidebarStats>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const [projects, ticketCounts, connections] = await Promise.all([
        getProjects().catch(() => null),
        getTicketCounts().catch(() => null),
        getConnections().catch(() => null),
      ]);
      if (cancelled) return;
      setStats({
        projects,
        projectCount: projects ? projects.length : null,
        ticketCounts,
        connectionCount: connections
          ? connections.reduce((n, g) => n + g.connections.length, 0)
          : null,
        loading: false,
      });
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return stats;
}
