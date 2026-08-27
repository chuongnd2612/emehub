// The ticket list, in the only two places one can exist under containment
// (#221, ADR 0011 §1/§3):
//
//   • inside a project — `/app/projects/:projectId/tickets`, the Tickets tab
//   • the Unassigned bucket — `/app/unassigned/tickets`, rows with no project
//
// There is no third one. The workspace-wide screen this file was extracted from
// is gone: `/app/tickets` redirects to `/app/projects` (#219) and the standalone
// nav entry went with it (#220). **A ticket list is never unscoped** — every
// `GET /tickets` from here carries either `projectId` or `unassigned=true`, and
// the scope is a prop rather than a URL parameter precisely so a screen cannot
// forget to pass it.
//
// ## What the provider switcher used to do, and what replaced it
//
// The old screen read `?source=` and let the user switch provider. Deleted, not
// hidden (see `TicketsToolbar`): the source is a property of the project, so the
// provider arrives in `scope` already resolved from the project's configured
// connection, and the filter facets are built from it. Nothing on this screen
// reads `?source=`, which is why a nested tickets URL carrying one shows exactly
// the same rows.
//
// ## Filtering and paging are the SERVER's
//
// `getTicketPage` sends the scope, every set field and the query as parameters on
// `GET /tickets`; nothing is filtered in the browser. Two loads run:
//
//   • the FACET load — one unfiltered page **within the scope**, which is where
//     the filter pills get their options (real values present in this project,
//     not invented ones) and where "last import" comes from;
//   • the ROW load — the same endpoint with the filters applied.
//
// The facet load is scoped too. An unscoped facet read would offer a sprint that
// exists in another project, which is the containment leak wearing a smaller hat.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";

import {
  buildTicketFilterSchema,
  getConnectionsWithCapability,
  getTicketPage,
  getWorkItemMetadata,
  listSavedQueries,
  searchTickets,
  PROVIDERS,
  type ProviderKey,
  type Ticket,
  type TicketFilters,
  type TicketQuery as TicketScopeQuery,
  type SavedQuery,
  type WorkItemMetadata,
} from "@/data";
import { emptyQuery, type TicketQuery as ClauseQuery } from "@/data/ticketQuery";
import { QueryBuilder } from "@/components/query";
import {
  Button,
  EmptyState,
  ErrorState,
  GlassCard,
  Icon,
  Pill,
  TableFootnote,
  TablePager,
  TableRowsSkeleton,
} from "@/components/ui";
import { ImportDialog, useImportRun } from "@/components/import";
import { ApiError } from "@/lib/api";
import { useUi } from "@/store/ui";
import { TicketsTable } from "./TicketsTable";
import { TicketsToolbar } from "./TicketsToolbar";

/**
 * Which rows this list is showing, and therefore which parameter every request
 * it makes must carry.
 *
 * A discriminated union rather than an optional `projectId`: the two scopes are
 * mutually exclusive on the wire (the hub answers 400 for both, deliberately —
 * `api/app/routers/tickets.py`), and a union is what makes that unrepresentable
 * here instead of discoverable as an error.
 */
export type TicketScope =
  | {
      kind: "project";
      /** `Project.rowId` — the `projectId` filter on `GET /tickets`. */
      projectId: number;
      /** Derived from the project's work-item connection. Never switchable. */
      provider: ProviderKey;
      /** `"<Provider name> · <connection label>"`, for the source chip's title. */
      sourceLabel: string;
    }
  | { kind: "unassigned" };

/** Rows per page — 10 rather than the hub's `GET /tickets` default of 25. */
const PAGE_SIZE = 10;

/** No metadata yet — the pickers fall back to free text, which still works. */
const EMPTY_META: WorkItemMetadata = {
  areaPaths: [],
  iterationPaths: [],
  workItemTypes: [],
  states: [],
  members: [],
  tags: [],
  epics: [],
  fetchedAt: null,
  stale: false,
  message: "",
};

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

/**
 * The one provider every row in `rows` came from, or `null`.
 *
 * Only the Unassigned bucket needs this. Those rows belong to no project, so
 * there is no configured connection to derive a source from — but they still
 * carry the provider they were stamped with at sync, and when they all agree
 * that IS the source. When they do not, the honest answer is no provider
 * vocabulary at all rather than one provider's pills over another's rows.
 */
const soleProvider = (rows: Ticket[]): ProviderKey | null => {
  const kinds = new Set(rows.map((r) => r.provider).filter(Boolean));
  const [only] = [...kinds];
  return kinds.size === 1 && only ? only : null;
};

export interface TicketsViewProps {
  scope: TicketScope;
  /**
   * Where a row's detail page lives. The caller owns this because the address
   * differs by scope — `/app/projects/:id/tickets/:externalId` inside a project,
   * `/app/unassigned/tickets/:externalId` in the bucket — and a list that built
   * the URL itself would have to know which container it is in twice.
   */
  ticketHref: (ticket: Ticket) => string;
  /** Rendered when the scope holds no rows at all (as opposed to none matching). */
  empty: { title: string; body: string; action?: ReactNode };
  /** The read-only-mirror sentence under the table. Copy differs by scope. */
  footnote: string;
}

export function TicketsView({
  scope,
  ticketHref,
  empty,
  footnote,
}: TicketsViewProps) {
  const navigate = useNavigate();

  /**
   * The scope, as request parameters. Every read on this screen spreads it, so
   * there is exactly one place a scope can be dropped — and it is one line.
   */
  const scopeQuery: TicketScopeQuery = useMemo(
    () =>
      scope.kind === "project"
        ? { projectId: scope.projectId }
        : { unassigned: true },
    [scope],
  );

  /** The unfiltered page **within the scope** — pills' options and "last import". */
  const [facetRows, setFacetRows] = useState<Ticket[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<TicketFilters>({});
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  /**
   * Which page of the row load is shown. Transient screen state, deliberately
   * not a URL param: a scroll depth through a paged list is not worth linking
   * to, and every other intra-screen control here is already local.
   */
  const [page, setPage] = useState(1);
  /**
   * A page change in flight, as distinct from `status === "loading"`.
   *
   * Turning a page must not swap the table for the full-screen loader: the rows
   * and the pager would vanish and come back, which reads as a navigation rather
   * than a page turn. A filter/query change still shows the loader, because
   * there the rows on screen are about to become the wrong rows.
   */
  const [turning, setTurning] = useState(false);
  const shownPage = useRef(1);
  /**
   * The clause query, and whether the panel is open. `applied` is what the table
   * is showing; `draft` is what the user is editing, so a half-built clause can
   * never fetch.
   *
   * The bucket has no builder: `POST /tickets/search` takes `projectId` but has
   * no `unassigned`, and inventing one is a contract change this slice does not
   * make (`data/tickets.ts` › `searchTickets`).
   */
  const canBuildQuery = scope.kind === "project";
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draftQuery, setDraftQuery] = useState<ClauseQuery>(() => emptyQuery("mirror"));
  const [appliedQuery, setAppliedQuery] = useState<ClauseQuery | null>(null);
  const [metadata, setMetadata] = useState<WorkItemMetadata>(EMPTY_META);
  const [saved, setSaved] = useState<SavedQuery[]>([]);
  const [savedKey, setSavedKey] = useState(0);

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

  /**
   * The provider whose filter vocabulary this list speaks.
   *
   * Inside a project it is the project's own source, resolved before this screen
   * rendered — the facets follow the source, exactly as ADR 0011 §3 requires. In
   * the bucket it is whatever the rows agree on, or nothing.
   */
  const provider: ProviderKey | null =
    scope.kind === "project" ? scope.provider : soleProvider(facetRows);

  const fields = useMemo(
    () => (provider ? buildTicketFilterSchema(provider, facetRows) : []),
    [provider, facetRows],
  );

  // The pickers read the provider's own metadata, not the mirror's distinct
  // values — so a state you have never imported is still offerable. Loaded only
  // once the panel is opened, because it costs a provider round trip.
  useEffect(() => {
    if (!builderOpen || !provider) return;
    let live = true;
    void getConnectionsWithCapability("work_item")
      .then((connections) => {
        const match = connections.find((c) => c.provider === provider);
        return match ? getWorkItemMetadata(match.id) : EMPTY_META;
      })
      .then((loaded) => {
        if (live) setMetadata(loaded);
      })
      .catch(() => {
        // A failed metadata read leaves free-text controls rather than blocking
        // the panel: the query still runs, it just offers no pickers.
        if (live) setMetadata(EMPTY_META);
      });
    return () => {
      live = false;
    };
  }, [builderOpen, provider]);

  // Saved queries for the mirror, scoped to this project (#222's frontend half):
  // the project's own rows plus the workspace-wide ones, never another
  // project's. Re-read on `savedKey` so adding, copying or removing one
  // refreshes the strip without reloading the screen.
  const savedProjectId = scope.kind === "project" ? scope.projectId : undefined;
  useEffect(() => {
    if (!builderOpen) return;
    let live = true;
    void listSavedQueries("mirror", savedProjectId)
      .then((rows) => {
        if (live) setSaved(rows);
      })
      .catch(() => {
        if (live) setSaved([]);
      });
    return () => {
      live = false;
    };
  }, [builderOpen, savedKey, savedProjectId]);

  // Facets: one unfiltered page, within the scope.
  useEffect(() => {
    let live = true;
    void getTicketPage({ ...scopeQuery })
      .then((loaded) => {
        if (live) setFacetRows(loaded.items);
      })
      .catch(() => {
        if (live) setFacetRows([]);
      });
    return () => {
      live = false;
    };
  }, [scopeQuery, reloadKey]);

  // Rows: the same endpoint with the active filters, query and page.
  useEffect(() => {
    let live = true;
    const turned = shownPage.current !== page;
    if (turned) setTurning(true);
    else setStatus("loading");

    const load =
      appliedQuery && scope.kind === "project"
        ? searchTickets({
            query: appliedQuery,
            q: query,
            projectId: scope.projectId,
            page,
            pageSize: PAGE_SIZE,
          })
        : getTicketPage({ ...scopeQuery, filters, query, page, pageSize: PAGE_SIZE });

    void load
      .then((loaded) => {
        if (!live) return;
        setTickets(loaded.items);
        setTotal(loaded.total);
        shownPage.current = page;
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(err instanceof ApiError ? err.message : "The hub did not respond.");
        setStatus("error");
      })
      .finally(() => {
        if (live) setTurning(false);
      });
    return () => {
      live = false;
    };
  }, [scope, scopeQuery, filters, query, page, reloadKey, appliedQuery]);

  /**
   * Reset to page 1 whenever what is being *asked for* changes.
   *
   * This has to happen in the same state update as the change itself, not in an
   * effect afterwards. An effect would run alongside the row load, which still
   * holds the old page in its closure — so narrowing a filter while on page 3
   * fires a request for page 3 of a set that may now have one page, and only
   * then a request for page 1. The doomed request was measured, not theorised:
   * it showed up as `q=z&page=3` immediately before `q=z&page=1`.
   */
  const resetPage = useCallback(() => {
    setPage(1);
    shownPage.current = 1;
  }, []);

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
    setAppliedQuery(null);
    setDraftQuery(emptyQuery("mirror"));
    resetPage();
  }, [resetPage]);

  const applyQuery = useCallback(() => {
    // The pills and a clause query answer the same question two ways, so applying
    // one drops the other rather than silently intersecting them.
    setFilters({});
    setAppliedQuery(draftQuery);
    resetPage();
  }, [draftQuery, resetPage]);

  const openRow = useCallback(
    (ticket: Ticket) => navigate(ticketHref(ticket)),
    [navigate, ticketHref],
  );

  const providerName = provider ? PROVIDERS[provider].name : "";
  /**
   * The empty state's primary CTA, where there is one to offer.
   *
   * Copy is the handoff's, unchanged. The Unassigned bucket gets none: it is
   * read-only by decision (ADR 0011 §4), and an Import button there would pull
   * into whichever project the connection is bound to — not into the bucket.
   */
  const importButton =
    scope.kind === "project" ? (
      <Button
        variant="primary"
        className="h-auto rounded-button px-[18px] py-[11px] text-[13px]"
        icon={<Icon name="download" size={15} strokeWidth={2.3} />}
        onClick={() => setModal("import")}
      >
        Import work items
      </Button>
    ) : null;
  const filtered =
    Object.values(filters).some(Boolean) || Boolean(query) || appliedQuery !== null;

  return (
    <div className="flex animate-fade-in-up flex-col gap-3.5">
      <TicketsToolbar
        source={
          scope.kind === "project"
            ? { provider: scope.provider, label: scope.sourceLabel }
            : null
        }
        query={query}
        onQueryChange={changeQuery}
        schema={fields}
        filters={filters}
        onFilterPick={pickFilter}
        onClear={clear}
        importing={importing}
        lastImport={lastImportLabel(facetRows)}
        onImport={
          scope.kind === "project" ? () => setModal("import") : undefined
        }
        builderOpen={canBuildQuery ? builderOpen : undefined}
        onToggleBuilder={
          canBuildQuery ? () => setBuilderOpen((open) => !open) : undefined
        }
        queryActive={appliedQuery !== null}
      />

      {/* The clause builder over the mirror. Collapsed by default: the pills
          answer the common case in one click, and a five-row panel above every
          table would be in the way of simply reading it. */}
      {canBuildQuery && builderOpen && (
        <GlassCard radius="panel" className="flex flex-col gap-3.5 p-[18px]">
          <QueryBuilder
            draft={draftQuery}
            onDraftChange={setDraftQuery}
            applied={appliedQuery}
            destination="mirror"
            metadata={metadata}
            busy={status === "loading" || turning}
            saved={saved}
            savedProjectId={savedProjectId}
            onSavedChanged={() => setSavedKey((n) => n + 1)}
            onApply={applyQuery}
            onReset={() => {
              setDraftQuery(emptyQuery("mirror"));
              setAppliedQuery(null);
              resetPage();
            }}
            trailing={
              appliedQuery !== null ? (
                <Pill tone="ok" size="sm">
                  {total} {total === 1 ? "match" : "matches"}
                </Pill>
              ) : null
            }
          />
        </GlassCard>
      )}

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
            title={empty.title}
            body={empty.body}
            action={empty.action ?? importButton}
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

          <TableFootnote icon="lock">{footnote}</TableFootnote>
        </>
      )}

      {scope.kind === "project" && (
        <ImportDialog
          open={modal === "import"}
          provider={scope.provider}
          onClose={() => setModal(null)}
          onImport={run}
        />
      )}
    </div>
  );
}
