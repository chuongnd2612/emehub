// Handoff § 4. Tickets — "Mirrors the Q-Agent ticket browser: exactly one
// provider is active at a time, and the filter set changes with it."
//
// Filtering and paging are now the SERVER's: `getTicketPage` sends the active
// provider, every set field and the query as parameters on `GET /tickets`.
// Nothing is filtered in the browser.
//
// Two loads run per provider:
//   • the FACET load — one unfiltered page, which is where the filter pills get
//     their options (real values present in the store, not invented ones) and
//     where the toolbar's "last import" timestamp comes from;
//   • the ROW load — the same endpoint with the filters applied.
//
// The active provider is a URL selection (`?source=`) — the URL is the source
// of truth (CLAUDE.md). Query + field filters are transient screen state.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  buildTicketFilterSchema,
  getTicketPage,
  PROVIDERS,
  type ProviderKey,
  type Ticket,
  type TicketFilters,
} from "@/data";
import {
  Button,
  EmptyState,
  ErrorState,
  GlassCard,
  Icon,
  LoadingState,
  TableFootnote,
  toast,
} from "@/components/ui";
import { ImportDialog, useImportRun } from "@/components/import";
import { ApiError } from "@/lib/api";
import { useUi } from "@/store/ui";
import { TicketsTable } from "./TicketsTable";
import { TicketsToolbar } from "./TicketsToolbar";

const isProvider = (value: string | null): value is ProviderKey =>
  value === "ado" || value === "jira" || value === "gh";

/**
 * The toolbar's "last import" line: the humanised `synced` label of the row the
 * mirror saw most recently, or null when nothing has been imported.
 */
const lastImportLabel = (rows: Ticket[]): string | null => {
  let newest: Ticket | null = null;
  for (const row of rows) {
    if (!row.syncedAt) continue;
    if (!newest?.syncedAt || row.syncedAt > newest.syncedAt) newest = row;
  }
  return newest?.synced ?? null;
};

export default function TicketsScreen() {
  const [params, setParams] = useSearchParams();
  const source = params.get("source");
  const provider: ProviderKey = isProvider(source) ? source : "ado";

  /** The unfiltered page — drives the pills' options and "last import". */
  const [facetRows, setFacetRows] = useState<Ticket[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<TicketFilters>({});
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);

  const reload = useCallback(() => setReloadKey((n) => n + 1), []);
  const { importing, run } = useImportRun(reload);

  const fields = useMemo(
    () => buildTicketFilterSchema(provider, facetRows),
    [provider, facetRows],
  );

  // Facets: one unfiltered page per provider.
  useEffect(() => {
    let live = true;
    void getTicketPage({ provider })
      .then((page) => {
        if (live) setFacetRows(page.items);
      })
      .catch(() => {
        if (live) setFacetRows([]);
      });
    return () => {
      live = false;
    };
  }, [provider, reloadKey]);

  // Rows: the same endpoint with the active filters and query.
  useEffect(() => {
    let live = true;
    setStatus("loading");
    void getTicketPage({ provider, filters, query })
      .then((page) => {
        if (!live) return;
        setTickets(page.items);
        setTotal(page.total);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(
          err instanceof ApiError ? err.message : "The hub did not respond.",
        );
        setStatus("error");
      });
    return () => {
      live = false;
    };
  }, [provider, filters, query, reloadKey]);

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
      toast(ticket.id, "info");
    },
    [provider],
  );

  const providerName = PROVIDERS[provider].name;
  const filtered = Object.values(filters).some(Boolean) || Boolean(query);
  const importButton = (
    <Button
      variant="primary"
      className="h-auto rounded-button px-[18px] py-[11px] text-[13px]"
      icon={<Icon name="download" size={15} strokeWidth={2.3} />}
      onClick={() => setModal("import")}
    >
      Import work items
    </Button>
  );

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
        lastImport={lastImportLabel(facetRows)}
        onImport={() => setModal("import")}
      />

      {status === "loading" && <LoadingState label="Loading work items…" />}

      {status === "error" && (
        <GlassCard className="rounded-[20px]">
          <ErrorState
            title="Could not load work items"
            detail={error}
            onRetry={reload}
          />
        </GlassCard>
      )}

      {status === "ready" && tickets.length === 0 && !filtered && (
        <GlassCard className="rounded-[20px]">
          <EmptyState
            icon="ticket"
            title={`Nothing mirrored from ${providerName} yet`}
            body="EmeHub keeps a read-only copy of your work items so every agent reads the same backlog. Run an import to pull the first batch."
            action={importButton}
          />
        </GlassCard>
      )}

      {status === "ready" && (tickets.length > 0 || filtered) && (
        <>
          <TicketsTable
            tickets={tickets}
            providerName={providerName}
            onRowClick={openRow}
          />

          <TableFootnote icon="lock">
            Read-only mirror. Edit work items in {providerName} — the next
            import reflects the change.
            {total > tickets.length &&
              ` Showing ${tickets.length} of ${total}; narrow the filters to see the rest.`}
          </TableFootnote>
        </>
      )}

      <ImportDialog
        open={modal === "import"}
        provider={provider}
        schema={fields}
        onClose={() => setModal(null)}
        onImport={run}
      />
    </div>
  );
}
