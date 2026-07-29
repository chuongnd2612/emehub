// Overview — the activity feed, the KPI tiles, and the product cards.
//
// STUBS, except `getProducts`: Q-Agent and D-Agent are static metadata with no
// endpoint planned.

import { ACTIVITY, KPIS } from "./fixtures/overview";
import { PRODUCTS } from "./fixtures/providers";
import { after, READ_DELAY_MS } from "./timing";
import type { ActivityEvent, Kpi, Product } from "./types";

// STUB: GET /api/activity
export const getActivity = (): Promise<ActivityEvent[]> =>
  after(ACTIVITY, READ_DELAY_MS);

// STUB: GET /api/overview/kpis
export const getKpis = (): Promise<Kpi[]> => after(KPIS, READ_DELAY_MS);

// Static product metadata — Q-Agent and D-Agent. No endpoint planned.
export const getProducts = (): Promise<Product[]> =>
  after(PRODUCTS, READ_DELAY_MS);
