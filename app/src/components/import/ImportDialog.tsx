// Handoff § 5. Import dialog — opened from Tickets and from the Overview quick
// action, which is why it lives in `components/import/` rather than inside the
// Tickets screen.
//
//   580px wide, var(--pop), radius 22, shadow-dialog, scaleIn .22s; scrim
//   rgba(6,6,10,.62) + blur(7px) + fadeIn .2s          → <Modal size="dialog">
//   Basic    → WHAT TO PULL, three radio rows
//   Advanced → BUILD A QUERY, the clause builder
//
// ## Both tabs produce the same thing
//
// A clause query. Basic is a shortcut to three common ones (`scopes.ts`), Advanced
// builds one by hand — and since the hub has no other way to be told what to pull
// (#130), there is exactly one code path behind both.
//
// The old Advanced was a grid of single-value dropdowns whose options came from
// work items **already mirrored**, which is why it could not help you import: no
// synced tickets meant no options. The builder reads the provider's own metadata
// instead, which is the whole point of the change.
//
// ## No JQL or search-query field
//
// `SyncRequest` has no `jql` and no `searchQuery`. The compilers generate both from
// clauses, and a hand-written query string would be an unescaped one — see
// `services/jql.py` on why that field's posture does not carry over from
// dev-assistant.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PROVIDERS,
  getConnectionsWithCapability,
  getWorkItemMetadata,
  listSavedQueries,
  previewTicketQuery,
  type ImportRequest,
  type ImportScope,
  type ProviderKey,
  type SavedQuery,
  type WorkItemMetadata,
} from "@/data";
import {
  emptyQuery,
  type Destination,
  type TicketQuery as ClauseQuery,
} from "@/data/ticketQuery";
import {
  Button,
  Glyph,
  Icon,
  Modal,
  Notice,
  Pill,
  RadioGroup,
  Segmented,
  toast,
} from "@/components/ui";
import { QueryBuilder } from "@/components/query";
import { scopesFor } from "./scopes";

/** Which compiler a provider's query is destined for. */
const DESTINATION: Record<ProviderKey, Destination> = {
  ado: "azure_devops",
  jira: "jira",
  gh: "github",
};

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

export type ImportMode = "basic" | "advanced";

export interface ImportDialogProps {
  /** Controlled visibility. The dialog renders nothing when false. */
  open: boolean;
  /** Which provider to pull from. Exactly one is active at a time. */
  provider: ProviderKey;
  /** Scrim click, ✕, Esc and Cancel. */
  onClose: () => void;
  /**
   * "Import now". The dialog closes itself first, then calls this with the
   * composed request; the caller runs it (see `useImportRun`) so the spinner
   * can live on whichever button opened the dialog.
   */
  onImport: (request: ImportRequest) => void;
  /** Mode the dialog opens in. Defaults to `basic`. */
  defaultMode?: ImportMode;
  /** Scope the dialog opens on. Defaults to `sprint`. */
  defaultScope?: ImportScope;
}

const MODE_OPTIONS = [
  { value: "basic" as const, label: "Basic" },
  { value: "advanced" as const, label: "Advanced" },
];

/** Small tracked uppercase section label — `WHAT TO PULL` / `BUILD A QUERY`. */
function SectionLabel({ children }: { children: string }) {
  return (
    <div className="text-[10.5px] font-bold tracking-[.11em] text-label">
      {children}
    </div>
  );
}

export function ImportDialog({
  open,
  provider,
  onClose,
  onImport,
  defaultMode = "basic",
  defaultScope = "sprint",
}: ImportDialogProps) {
  const [mode, setMode] = useState<ImportMode>(defaultMode);
  const [scope, setScope] = useState<ImportScope>(defaultScope);

  const meta = PROVIDERS[provider];
  const destination = DESTINATION[provider];

  // The query builder's own state. `previewed` is the query the count belongs to,
  // which is what makes "3 changes not applied" meaningful — see QueryBuilder.
  const [draft, setDraft] = useState<ClauseQuery>(() => emptyQuery(destination));
  const [previewed, setPreviewed] = useState<ClauseQuery | null>(null);
  const [count, setCount] = useState<number | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [metadata, setMetadata] = useState<WorkItemMetadata>(EMPTY_META);
  const [metaError, setMetaError] = useState("");
  const [saved, setSaved] = useState<SavedQuery[]>([]);
  const [savedKey, setSavedKey] = useState(0);

  // The pickers are only as good as the provider metadata behind them, so it is
  // read once per open — cached hub-side, so a reopen is usually free.
  useEffect(() => {
    if (!open || mode !== "advanced") return;
    let live = true;
    setMetaError("");
    void getConnectionsWithCapability("work_item")
      .then(async (connections) => {
        const match = connections.find((c) => c.provider === provider);
        if (!match) {
          throw new Error(
            `No ${meta.name} connection is configured, so there are no fields to build a query from.`,
          );
        }
        return { id: match.id, metadata: await getWorkItemMetadata(match.id) };
      })
      .then(({ metadata: loaded }) => {
        if (live) setMetadata(loaded);
      })
      .catch((err: unknown) => {
        if (live) {
          setMetaError(
            err instanceof Error ? err.message : "Could not read the provider's fields.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [open, mode, provider, meta.name]);

  // Saved queries for this provider's own destination — a query built for ADO
  // cannot run on Jira, so the list is never mixed.
  useEffect(() => {
    if (!open || mode !== "advanced") return;
    let live = true;
    void listSavedQueries(destination)
      .then((rows) => {
        if (live) setSaved(rows);
      })
      .catch(() => {
        if (live) setSaved([]);
      });
    return () => {
      live = false;
    };
  }, [open, mode, destination, savedKey]);

  const preview = useCallback(() => {
    setPreviewing(true);
    void previewTicketQuery({ provider, query: draft })
      .then((result) => {
        setCount(result.total);
        setPreviewed(draft);
      })
      .catch((err: unknown) => {
        setCount(null);
        // A failed preview must not read as "no work items" — that is the
        // difference between a count of 0 and not knowing.
        toast(
          "Could not preview the query",
          "warn",
          err instanceof Error ? err.message : "The provider did not answer.",
        );
      })
      .finally(() => setPreviewing(false));
  }, [draft, provider]);

  // A provider switch changes the whole filter set, so nothing carries over. The
  // clause draft is reset with it: the fields a destination offers come from the
  // capability matrix, so a clause built for ADO can be one Jira has no column for
  // — carrying it over would show a row that only fails on Apply.
  useEffect(() => {
    setDraft(emptyQuery(destination));
    setPreviewed(null);
    setCount(null);
  }, [provider, destination]);

  // Every visit starts from the caller's defaults.
  useEffect(() => {
    if (!open) return;
    setMode(defaultMode);
    setScope(defaultScope);
  }, [open, defaultMode, defaultScope]);

  // Only the scopes this provider can express. GitHub has no sprints, so there is
  // no honest "Active sprint" for it — see `scopes.ts`.
  const available = useMemo(() => scopesFor(destination), [destination]);

  // A scope the new provider cannot express must not stay selected.
  useEffect(() => {
    if (!available.some((o) => o.key === scope)) {
      setScope(available[0]?.key ?? "all");
    }
  }, [available, scope]);

  const scopeOptions = useMemo(
    () =>
      available.map((o) => ({
        value: o.key,
        label: (
          <span className="flex flex-col gap-[2px]">
            <span className="text-[13.5px] font-bold text-txt">{o.label}</span>
            <span className="text-[12px] font-medium text-muted">
              {o.description.replace("{provider}", meta.name)}
            </span>
          </span>
        ),
      })),
    [available, meta.name],
  );

  // Basic and Advanced both come out as a clause query — Basic is a shortcut to a
  // common one, not a different way of asking. The hub has no other way to be told
  // what to pull (#130).
  const scopeQuery = useMemo(
    () => available.find((o) => o.key === scope)?.query(destination) ?? null,
    [available, scope, destination],
  );

  const submit = () => {
    const request: ImportRequest = {
      provider,
      mode,
      scope,
      // Only a query that has been APPLIED is imported. Importing the draft would
      // pull something the user never saw a count for.
      query: (mode === "advanced" ? previewed : scopeQuery) ?? undefined,
    };
    onClose();
    onImport(request);
  };

  // Nothing to import is not a state the dialog should let you press through: in
  // Advanced that means the query has not been applied yet, so the count on screen
  // would not belong to what got pulled.
  const canImport = mode === "advanced" ? previewed !== null : scopeQuery !== null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="dialog"
      title="Import tickets"
      subtitle={`Pull work items from ${meta.name}`}
      glyph={<Glyph size={34} fill={meta.color} label={meta.glyph} />}
      footer={
        <>
          <span className="flex-1 text-[11.5px] text-faint">
            Read-only pull · credentials stay encrypted
          </span>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={!canImport}
            title={canImport ? undefined : "Apply the query first"}
            icon={<Icon name="download" size={14} strokeWidth={2.3} />}
          >
            Import now
          </Button>
        </>
      }
    >
      {/* Mode switch — segmented Basic | Advanced in a 4px inset track. */}
      <Segmented
        options={MODE_OPTIONS}
        value={mode}
        onChange={setMode}
        className="w-full [&>button]:flex-1"
      />

      {mode === "basic" ? (
        <div className="flex flex-col gap-3">
          <SectionLabel>WHAT TO PULL</SectionLabel>
          <RadioGroup
            name="import-scope"
            value={scope}
            onChange={setScope}
            options={scopeOptions}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <SectionLabel>BUILD A QUERY</SectionLabel>
          {metaError ? (
            <Notice tone="warn">{metaError}</Notice>
          ) : (
            <QueryBuilder
              draft={draft}
              onDraftChange={setDraft}
              applied={previewed}
              destination={destination}
              metadata={metadata}
              busy={previewing}
              saved={saved}
              onSavedChanged={() => setSavedKey((n) => n + 1)}
              onApply={preview}
              onReset={() => setDraft(emptyQuery(destination))}
              trailing={
                previewed && count !== null ? (
                  <Pill tone={count > 0 ? "ok" : "neutral"} size="sm">
                    {count} {count === 1 ? "work item" : "work items"}
                  </Pill>
                ) : null
              }
            />
          )}
        </div>
      )}
    </Modal>
  );
}
