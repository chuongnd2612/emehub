// Handoff § 4. Tickets — "Mirrors the Q-Agent ticket browser: exactly one
// provider is active at a time, and the filter set changes with it."
//
// Filtering is `provider match && every set field equals the ticket's field &&
// query matches id|title|project`, and it lives in the data layer
// (`getTickets`) so the real endpoint can take it over unchanged.
//
// The active provider is a URL selection (`?source=`) — the URL is the source
// of truth (CLAUDE.md). Query + field filters are transient screen state.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getTicketFilterSchema,
  getTickets,
  PROVIDERS,
  type ProviderKey,
  type Ticket,
  type TicketFilterField,
  type TicketFilters,
  type TicketFilterSchema,
} from "@/data";
import { TableFootnote, toast } from "@/components/ui";
import { ImportDialog, useImportRun } from "@/components/import";
import { useUi } from "@/store/ui";
import { TicketsTable } from "./TicketsTable";
import { TicketsToolbar } from "./TicketsToolbar";

const isProvider = (value: string | null): value is ProviderKey =>
  value === "ado" || value === "jira" || value === "gh";

export default function TicketsScreen() {
  const [params, setParams] = useSearchParams();
  const source = params.get("source");
  const provider: ProviderKey = isProvider(source) ? source : "ado";

  const [schema, setSchema] = useState<TicketFilterSchema | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filters, setFilters] = useState<TicketFilters>({});
  const [query, setQuery] = useState("");

  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);
  const { importing, run } = useImportRun();

  const fields: TicketFilterField[] = useMemo(
    () => schema?.[provider] ?? [],
    [schema, provider],
  );

  // STUB: GET /api/tickets/schema — see data/index.ts.
  useEffect(() => {
    let live = true;
    getTicketFilterSchema().then((s) => {
      if (live) setSchema(s);
    });
    return () => {
      live = false;
    };
  }, []);

  // STUB: GET /api/tickets?provider=…&{filters}. Re-runs on every input.
  useEffect(() => {
    let live = true;
    getTickets(provider, filters, query).then((rows) => {
      if (live) setTickets(rows);
    });
    return () => {
      live = false;
    };
  }, [provider, filters, query]);

  /** Switching source clears all field filters. */
  const changeProvider = useCallback(
    (next: ProviderKey) => {
      setFilters({});
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.set("source", next);
          return p;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /** Picking the same value again clears the field. */
  const pickFilter = useCallback((key: string, value: string) => {
    setFilters((f) => ({ ...f, [key]: f[key] === value ? undefined : value }));
  }, []);

  const clear = useCallback(() => {
    setFilters({});
    setQuery("");
  }, []);

  const openRow = useCallback(
    (ticket: Ticket) => {
      toast(
        ticket.id,
        `Read-only mirror · open in ${PROVIDERS[provider].name} to edit`,
        "info",
      );
    },
    [provider],
  );

  const providerName = PROVIDERS[provider].name;

  return (
    <div className="flex animate-fade-in-up flex-col gap-3.5">
      <TicketsToolbar
        provider={provider}
        onProviderChange={changeProvider}
        query={query}
        onQueryChange={setQuery}
        schema={fields}
        filters={filters}
        onFilterPick={pickFilter}
        onClear={clear}
        importing={importing}
        onImport={() => setModal("import")}
      />

      <TicketsTable
        tickets={tickets}
        providerName={providerName}
        onRowClick={openRow}
      />

      <TableFootnote icon="lock">
        Read-only mirror. Edit work items in {providerName} — the next import
        reflects the change.
      </TableFootnote>

      <ImportDialog
        open={modal === "import"}
        provider={provider}
        onClose={() => setModal(null)}
        onImport={run}
      />
    </div>
  );
}
