// Provider connections and the per-provider integration summary.
//
// STUBS. Each function names the endpoint that will replace it. Note the hub
// never returns a PAT (CLAUDE.md › Security rules) — the real `/connections`
// response carries `hasPat`, never the token itself, so nothing in this module
// should ever grow a field holding one.

import { CONNECTION_GROUPS } from "./fixtures/connections";
import { INTEGRATIONS, PROVIDERS } from "./fixtures/providers";
import { after, READ_DELAY_MS } from "./timing";
import type {
  ConnectionTestResult,
  Integration,
  ProviderConnection,
  ProviderConnectionGroup,
} from "./types";

/** Test connection — "Testing…" spinner. */
export const TEST_CONNECTION_DELAY_MS = 1300;

export { PROVIDERS };

// STUB: GET /api/connections
export const getConnections = (): Promise<ProviderConnectionGroup[]> =>
  after(CONNECTION_GROUPS, READ_DELAY_MS);

// STUB: GET /api/integrations — the per-provider summary cards.
export const getIntegrations = (): Promise<Integration[]> =>
  after(INTEGRATIONS, READ_DELAY_MS);

/** Resolves after 1300 ms; the caller then marks the connection Connected. */
// STUB: POST /api/connections/{connectionId}/test
export const testConnection = (
  _connectionId: string,
): Promise<ConnectionTestResult> =>
  after({ ok: true, latencyMs: 118 }, TEST_CONNECTION_DELAY_MS);

// STUB: PUT /api/connections/{connectionId}
export const saveConnection = (
  connection: ProviderConnection,
): Promise<ProviderConnection> => after(connection, READ_DELAY_MS);

// STUB: DELETE /api/connections/{connectionId}
export const removeConnection = (_connectionId: string): Promise<void> =>
  after(undefined, READ_DELAY_MS);
