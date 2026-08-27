// Overview — the KPI tiles, the activity feed, and the product cards.
//
// **No fixtures.** Everything numeric here is derived from a real endpoint. The
// tiles used to be four invented figures with invented deltas and invented
// sparklines (`OPEN TICKETS 128 +12`, `SYNC HEALTH 96%`, `AGENT RUNS 1,204`), so
// a workspace with nothing in it still looked busy. The feed was six invented
// events naming people who may not exist.
//
// Endpoint map:
//   GET /projects      ┐
//   GET /tickets       ├ the tile counts
//   GET /connections   │
//   GET /auth/users    ┘ (admin only)
//   GET /audit/events    the activity feed
//   GET /agents          the product cards' launch state
//   GET /agents/{id}/open  the product cards' availability (public)
//
// ## Why two tiles are gone rather than zeroed
//
// `SYNC HEALTH` and `AGENT RUNS` have no source: the hub stores no sync-health
// signal and does not run agents. `delta` / `direction` / `bars` have no source
// either — each needs history the hub does not keep. A zero, or a flat
// sparkline, is still a claim. So the fields and those tiles are removed rather
// than faked; if the hub ever records a time series they come back with it.

import { api } from "@/lib/api";
import { AGENT_ID, getAgents, isAgentOpen } from "./agents";
import { getConnections } from "./connections";
import { PRODUCTS } from "./fixtures/providers";
import { relativeTime } from "./humanize";
import { getProjects, getTicketCounts } from "./projects";
import type {
  ActivityEvent,
  ActivityKind,
  AgentTarget,
  Kpi,
  Product,
} from "./types";

/* ── KPI tiles ───────────────────────────────────────────────────────────── */

/**
 * A count, or `null` when this caller may not read the source.
 *
 * `null` drops the tile. It must never fall back to `0`: a failed read
 * rendering as zero is the "failed load reads as no data" bug, and on a KPI it
 * is worse than an absent tile because a zero looks authoritative.
 */
const countOr = async (load: () => Promise<number>): Promise<number | null> => {
  try {
    return await load();
  } catch {
    return null;
  }
};

/** The tiles, from real counts. Every count is one request; they run together. */
export async function getKpis(): Promise<Kpi[]> {
  const [projects, tickets, connections, members] = await Promise.all([
    countOr(async () => (await getProjects()).length),
    // `getTicketCounts()` — the ONE counting path in the app (#217/#218/#221).
    // This tile used to call `countTickets()`, an unscoped `GET /tickets` with
    // `pageSize=1`, which was both a second way to count and the last ticket
    // LIST read in the app that carried no scope at all. `total` is the same
    // figure from the endpoint the sidebar, the project tabs and the comparison
    // table already read, so Overview can no longer disagree with them.
    countOr(async () => (await getTicketCounts()).total),
    countOr(async () => {
      const groups = await getConnections();
      return groups.reduce((n, g) => n + g.connections.length, 0);
    }),
    // Admin-only: `GET /auth/users` is 403 for a member, so this tile is simply
    // absent for them rather than showing an error or a zero.
    countOr(async () => (await api.get<unknown[]>("/auth/users")).length),
  ]);

  const tiles: (Kpi | null)[] = [
    projects === null
      ? null
      : { label: "PROJECTS", value: String(projects), unit: "registered" },
    tickets === null
      ? null
      : {
          label: "WORK ITEMS",
          value: tickets.toLocaleString(),
          unit: "mirrored",
        },
    connections === null
      ? null
      : {
          label: "CONNECTIONS",
          value: String(connections),
          unit: connections === 1 ? "provider account" : "provider accounts",
        },
    members === null
      ? null
      : {
          label: "MEMBERS",
          value: String(members),
          unit: members === 1 ? "account" : "accounts",
        },
  ];

  return tiles.filter((tile): tile is Kpi => tile !== null);
}

/* ── Activity feed ───────────────────────────────────────────────────────── */

/** `AuditEventOut`, as the hub serialises an audit row. */
interface AuditWire {
  id: number;
  ts: string;
  category: string;
  /** The audience that caused it: `emehub` here, `qagent` / `dagent` for an agent. */
  source: string;
  actor: string;
  actorType: string;
  action: string;
  target: string;
  status: string;
  meta: string;
}

/** Chip tint + glyph per audit category. */
const CATEGORY: Record<string, { kind: ActivityKind; icon: string }> = {
  ticket: { kind: "sync", icon: "upload" },
  credential: { kind: "key", icon: "key" },
  auth: { kind: "key", icon: "lock" },
  connection: { kind: "sync", icon: "plug" },
  project: { kind: "kb", icon: "folder" },
  knowledge: { kind: "kb", icon: "book" },
};

const AGENT_KIND: Record<string, ActivityKind> = { qagent: "q", dagent: "d" };

/**
 * `GET /audit/events` → the feed.
 *
 * The audit log already carries everything a row renders — who acted, what they
 * did, to what, when, and whether it worked — and it is already attributed to
 * the agent that caused it, which is exactly the "Q-Agent did X" line the
 * fixture was faking.
 *
 * Chip precedence: a failure is amber whatever caused it; otherwise an agent's
 * own colour beats the category's, because "Q-Agent synced tickets" is more
 * useful seen as Q-Agent than as a sync.
 */
export async function getActivity(): Promise<ActivityEvent[]> {
  const rows = await api.get<AuditWire[]>("/audit/events", {
    query: { limit: 12 },
  });
  return rows.map((row) => {
    const category = CATEGORY[row.category] ?? { kind: "sync", icon: "bolt" };
    const failed = row.status === "error" || row.status === "warning";
    const agent = AGENT_KIND[row.source];
    return {
      id: String(row.id),
      text: row.action,
      // `target` is the thing acted on (`SUR-1428`, `claude:own`). Fall back to
      // the category rather than rendering an empty mono chip.
      ref: row.target || row.category.toUpperCase(),
      kind: failed ? "warn" : (agent ?? category.kind),
      by: row.actor,
      when: relativeTime(row.ts),
      icon: failed ? "alert" : category.icon,
    };
  });
}

/* ── Product cards ───────────────────────────────────────────────────────── */

/**
 * Product cards — static copy joined to live launch state and live availability.
 *
 * The copy (name, role, description, tags, and `live`) stays in
 * `fixtures/providers.ts` because it is binding design content, not runtime
 * state: D-Agent's "Placeholder" pill is a product decision and must not start
 * reading "Live" the moment somebody sets a URL for it.
 *
 * Two different runtime questions are asked, from two different endpoints, and
 * they degrade in opposite directions on purpose:
 *
 *   **Can a session be handed over?** `launchUrl` / `handoffReady` /
 *   `handoffReason`, from `GET /agents`. A failed read disables launching but
 *   keeps the cards — a dead Launch button beats a blank Overview.
 *
 *   **Is the product open at all?** `enabled`, from the public
 *   `GET /agents/{id}/open`. A failed read means CLOSED. Never `?? true`: this
 *   used to come from the registry with an available-by-default fallback, and
 *   because `GET /agents` is hub-audience only, the signed-out landing page
 *   failed that read on every visit and showed a switched-off product as a
 *   green "Live" card anybody could click (#191).
 *
 * Reading availability from the public route rather than the registry also
 * means the landing page and the Overview agree, instead of one of them being
 * a special case.
 */
export async function getProducts(): Promise<Product[]> {
  const [registry, open] = await Promise.all([
    getAgents().catch(() => [] as AgentTarget[]),
    Promise.all(PRODUCTS.map((product) => isAgentOpen(AGENT_ID[product.key]))),
  ]);

  return PRODUCTS.map((product, at) => {
    const target = registry.find((agent) => agent.key === product.key);
    return {
      ...product,
      launchUrl: target?.url ?? null,
      handoffReady: target?.handoffReady ?? false,
      handoffReason: target?.reason ?? null,
      enabled: open[at],
    };
  });
}
