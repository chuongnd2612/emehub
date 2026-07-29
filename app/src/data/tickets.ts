// Tickets — the synced work-item list, its filter schema, and importing.
//
// STUBS. Each function names the endpoint that will replace it.

import { PROVIDERS } from "./fixtures/providers";
import { TICKETS, TICKET_FILTER_SCHEMA } from "./fixtures/tickets";
import { after, READ_DELAY_MS } from "./timing";
import type {
  ImportRequest,
  ImportResult,
  ProviderKey,
  Ticket,
  TicketFilters,
  TicketFilterSchema,
} from "./types";

/** Import now — button spins for this long, then the success toast fires. */
export const IMPORT_DELAY_MS = 1500;

/**
 * Filtering rule, verbatim from the handoff: `provider match && every set
 * field equals the ticket's field && query matches id|title|project`.
 */
// STUB: GET /api/tickets?provider={provider}&{...filters}
export const getTickets = (
  provider: ProviderKey,
  filters: TicketFilters = {},
  query = "",
): Promise<Ticket[]> => {
  const q = query.trim().toLowerCase();
  const rows = TICKETS.filter((t) => {
    if (t.provider !== provider) return false;
    for (const [key, value] of Object.entries(filters)) {
      if (value == null || value === "") continue;
      if ((t as unknown as Record<string, unknown>)[key] !== value) return false;
    }
    if (!q) return true;
    return `${t.id} ${t.title} ${t.project}`.toLowerCase().includes(q);
  });
  return after(rows, READ_DELAY_MS);
};

// STUB: GET /api/tickets/schema — the provider-variant filter fields.
export const getTicketFilterSchema = (): Promise<TicketFilterSchema> =>
  after(TICKET_FILTER_SCHEMA, READ_DELAY_MS);

/**
 * Runs an import. Resolves after 1500 ms; the caller shows `Importing…` with a
 * spinning icon meanwhile, then toasts
 * `Import complete — 31 work items pulled from <provider> · <scope|field filters applied>`.
 */
// STUB: POST /api/tickets/import
export const runImport = (request: ImportRequest): Promise<ImportResult> => {
  const scopeLabel =
    request.mode === "advanced"
      ? "field filters applied"
      : { sprint: "active sprint", assigned: "items assigned to you", all: "all open items" }[
          request.scope
        ];
  return after(
    { count: 31, provider: PROVIDERS[request.provider].name, scopeLabel },
    IMPORT_DELAY_MS,
  );
};
