// The sidebar's nav badges and footer status line were hardcoded ("6", "128",
// "3", "3 integrations connected · 2 agents online") straight from the
// prototype's fixtures. This hook replaces them with real counts from the
// same endpoints the owning screens already call, so the sidebar can never
// disagree with the page it links to.

import { useEffect, useState } from "react";

import { getConnections } from "@/data/connections";
import { getProjects } from "@/data/projects";
import { getTicketPage } from "@/data/tickets";

export interface SidebarStats {
  projectCount: number | null;
  ticketCount: number | null;
  connectionCount: number | null;
  loading: boolean;
}

const EMPTY: SidebarStats = {
  projectCount: null,
  ticketCount: null,
  connectionCount: null,
  loading: true,
};

/**
 * `null` means "not loaded yet or failed" — the caller renders no badge
 * rather than a stale or invented number. A failed count must never fall
 * back to a fixture.
 */
export function useSidebarStats(): SidebarStats {
  const [stats, setStats] = useState<SidebarStats>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const [projects, tickets, connections] = await Promise.all([
        getProjects().catch(() => null),
        getTicketPage({ pageSize: 1 }).catch(() => null),
        getConnections().catch(() => null),
      ]);
      if (cancelled) return;
      setStats({
        projectCount: projects ? projects.length : null,
        ticketCount: tickets ? tickets.total : null,
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
