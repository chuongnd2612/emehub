// Overview — the activity feed, the KPI tiles, and the product cards.
//
// STUBS, except `getProducts`, which is now a join: static card copy from the
// handoff merged with the live launch registry (`GET /agents`).

import { getAgents } from "./agents";
import { ACTIVITY, KPIS } from "./fixtures/overview";
import { PRODUCTS } from "./fixtures/providers";
import { after, READ_DELAY_MS } from "./timing";
import type { ActivityEvent, AgentTarget, Kpi, Product } from "./types";

// STUB: GET /api/activity
export const getActivity = (): Promise<ActivityEvent[]> =>
  after(ACTIVITY, READ_DELAY_MS);

// STUB: GET /api/overview/kpis
export const getKpis = (): Promise<Kpi[]> => after(KPIS, READ_DELAY_MS);

/**
 * Product cards — static copy joined to the live launch registry.
 *
 * The copy (name, role, description, tags, metrics, and `live`) stays in
 * `fixtures/providers.ts` because it is binding design content, not runtime
 * state: D-Agent's "Placeholder" pill is a product decision and must not start
 * reading "Live" the moment somebody sets a URL for it.
 *
 * What *is* runtime state is whether a session can be handed over, so only
 * `launchUrl` / `handoffReady` / `handoffReason` come from `GET /agents`.
 *
 * If the registry read fails the cards still render with launching disabled — a
 * dead Launch button beats a blank Overview.
 */
export async function getProducts(): Promise<Product[]> {
  let registry: AgentTarget[] = [];
  try {
    registry = await getAgents();
  } catch {
    // Deliberately swallowed: see above. The cards degrade, they don't vanish.
  }

  return PRODUCTS.map((product) => {
    const target = registry.find((agent) => agent.key === product.key);
    return {
      ...product,
      launchUrl: target?.url ?? null,
      handoffReady: target?.handoffReady ?? false,
      handoffReason: target?.reason ?? null,
    };
  });
}
