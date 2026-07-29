// Prototype `KEYS`, typed.
//
// The prototype's `SESSIONS` array is GONE: `getSessions()` now reads
// `GET /auth/sessions`, and a fixture session list would be showing someone
// else's devices as if they were yours.

import type { ApiKey } from "../types";

export const API_KEYS: ApiKey[] = [
  { id: "k1", name: "CI pipeline (Azure)", prefix: "ehk_live_9f2c", scope: "Read tickets, write evidence", used: "12m ago", created: "Mar 2026" },
  { id: "k2", name: "D-Agent runner", prefix: "ehk_live_4a71", scope: "Full agent access", used: "2h ago", created: "Jun 2026" },
  { id: "k3", name: "Reporting export", prefix: "ehk_live_be08", scope: "Read only", used: "6d ago", created: "Jan 2026" },
];
