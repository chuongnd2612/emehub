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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  TableFootnote,
  TablePager,
  TableRowsSkeleton,
  toast,
} from "@/components/ui";
import { ImportDialog, useImportRun } from "@/components/import";
import { ApiError } from "@/lib/api";
import { useUi } from "@/store/ui";
import { TicketsTable } from "./TicketsTable";
import { TicketsToolbar } from "./TicketsToolbar";

/**
 * Rows per page. Matches the hub's own `GET /tickets` default (`page_size=25`),
 * so the first request asks for exactly what the server would have given anyway.
 */
const PAGE_SIZE = 25;

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
  /**
   * Which page of the row load is shown.
   *
   * Transient screen state, deliberately **not** a URL param. `?source=` is in
   * the URL because the active provider is a selection worth linking to and
   * restoring; a scroll depth through a paged list is not, and every other
   * intra-screen control here (the query, the field filters) is already local.
   */
  const [page, setPage] = useState(1);
  /**
   * A page change in flight, as distinct from `status === "loading"`.
   *
   * Turning a page must not swap the table for the full-screen loader: the rows
   * and the pager would vanish and come back, which reads as a navigation rather
   * than a page turn — and with the pager gone mid-flight there is nothing to
   * click twice. So a page change keeps the current rows on screen and only
   * disables the pager. A provider/filter/query change still shows the loader,
   * because there the rows on screen are about to become the wrong rows.
   */
  const [turning, setTurning] = useState(false);
  const shownPage = useRef(1);

  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);

  // An import can change the size of the set under us, so a reload starts over
  // at page 1 rather than on a page that may no longer exist.
  const reload = useCallback(() => {
    setPage(1);
    shownPage.current = 1;
    setReloadKey((n) => n + 1);
  }, []);
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

  // Rows: the same endpoint with the active filters, query and page.
  useEffect(() => {
    let live = true;
    const turned = shownPage.current !== page;
    if (turned) setTurning(true);
    else setStatus("loading");

    void getTicketPage({ provider, filters, query, page, pageSize: PAGE_SIZE })
      .then((loaded) => {
        if (!live) return;
        setTickets(loaded.items);
        setTotal(loaded.total);
        shownPage.current = page;
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(
          err instanceof ApiError ? err.message : "The hub did not respond.",
        );
        setStatus("error");
      })
      .finally(() => {
        if (live) setTurning(false);
      });
    return () => {
      live = false;
    };
  }, [provider, filters, query, page, reloadKey]);

  /**
   * Reset to page 1 whenever what is being *asked for* changes.
   *
   * This has to happen in the same state update as the change itself, not in an
   * effect afterwards. An effect would run alongside the row load, which still
   * holds the old page in its closure — so narrowing a filter while on page 3
   * fires a request for page 3 of a set that may now have one page, and only
   * then a request for page 1. The doomed request was measured, not theorised:
   * it showed up as `q=z&page=3` immediately before `q=z&page=1`.
   *
   * Resetting inside each mutator makes it one update, one effect run, one
   * request.
   */
  const resetPage = useCallback(() => {
    setPage(1);
    shownPage.current = 1;
  }, []);

  /** Switching source clears all field filters. */
  const changeProvider = useCallback(
    (next: ProviderKey) => {
      setFilters({});
      resetPage();
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.set("source", next);
          return p;
        },
        { replace: true },
      );
    },
    [resetPage, setParams],
  );

  /** Picking the same value again clears the field. */
  const pickFilter = useCallback(
    (key: string, value: string) => {
      setFilters((f) => ({ ...f, [key]: f[key] === value ? undefined : value }));
      resetPage();
    },
    [resetPage],
  );

  const changeQuery = useCallback(
    (next: string) => {
      setQuery(next);
      resetPage();
    },
    [resetPage],
  );

  const clear = useCallback(() => {
    setFilters({});
    setQuery("");
    resetPage();
  }, [resetPage]);

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
        onQueryChange={changeQuery}
        schema={fields}
        filters={filters}
        onFilterPick={pickFilter}
        onClear={clear}
        importing={importing}
        lastImport={lastImportLabel(facetRows)}
        onImport={() => setModal("import")}
      />

      {/* Skeleton rows rather than a centred spinner: the table's geometry is
          known, so the toolbar stays put and the rows fill in instead of the
          layout jumping when they land. */}
      {status === "loading" && (
        <GlassCard className="rounded-[20px] p-0">
          <TableRowsSkeleton rows={8} columns={6} />
        </GlassCard>
      )}

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

          <TablePager
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onPageChange={setPage}
            busy={turning}
            noun="work item"
          />

          {/* The old footnote ended with "narrow the filters to see the rest",
              which was the only way through a set bigger than one page. The
              pager above is that way, so the sentence goes. */}
          <TableFootnote icon="lock">
            Read-only mirror. Edit work items in {providerName} — the next import
            reflects the change.
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
