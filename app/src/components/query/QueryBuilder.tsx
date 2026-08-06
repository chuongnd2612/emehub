// The query builder — clause rows over a draft, applied on press.
//
// ## Apply on press, which everything here is arranged around
//
// **Selecting a field, an operator or a value must not run a query.** Every edit
// lands in the draft; only `Apply` hands it to the caller. The split is made
// legible rather than left implicit: an unapplied-changes line, an Apply that
// enables only when there is something to apply, and Reset.
//
// The same shape as the Settings save bar — a draft, a count of what differs, and
// one commit — so the app has one answer to "I changed something, now what".
//
// `Enter` in a single-value field applies, because a filter box that ignores Enter
// feels broken.
//
// ## Validation
//
// An invalid draft **disables Apply and says why, under the offending row**, from
// the same `validateQuery` the API refuses a hand-built request with. If those two
// ever disagree, "Apply is greyed out" stops matching "400 Bad Request" — which is
// why a test pins the two tables together.
//
// ## Where the values come from
//
// The connection's own metadata (`components/query/options.ts`), never a list this
// app invented. Where the metadata offers nothing, the control is a plain input.

import { useMemo } from "react";

import { Button, Icon, Pill, Segmented } from "@/components/ui";
import type { WorkItemMetadata } from "@/data";
import {
  describeQuery,
  effectiveClauses,
  generalProblems,
  MATCH_ANY_DESTINATIONS,
  newClause,
  problemsForClause,
  validateQuery,
  type Destination,
  type QueryClause,
  type TicketQuery,
} from "@/data/ticketQuery";
import { cn } from "@/lib/cn";
import { ClauseRow } from "./ClauseRow";
import { SavedQueries } from "./SavedQueries";

/** How many clauses differ between the draft and what was last applied. */
export function countChanges(draft: TicketQuery, applied: TicketQuery | null): number {
  if (applied === null) return effectiveClauses(draft).length;
  if (JSON.stringify(draft) === JSON.stringify(applied)) return 0;
  const before = applied.clauses.map((c) => JSON.stringify(c));
  const after = draft.clauses.map((c) => JSON.stringify(c));
  const changed =
    after.filter((c) => !before.includes(c)).length +
    before.filter((c) => !after.includes(c)).length;
  // A match or sort flip changes nothing clause-by-clause but changes the query.
  const shape =
    draft.match !== applied.match ||
    JSON.stringify(draft.sort) !== JSON.stringify(applied.sort)
      ? 1
      : 0;
  return Math.max(changed, shape ? Math.max(changed, 1) : changed);
}

export interface QueryBuilderProps {
  draft: TicketQuery;
  onDraftChange: (query: TicketQuery) => void;
  /** The query currently in force, or null before anything has been applied. */
  applied: TicketQuery | null;
  destination: Destination;
  metadata: WorkItemMetadata;
  onApply: () => void;
  onReset: () => void;
  /** True while the applied query is running — Apply says so and locks. */
  busy?: boolean;
  /** Rendered beside Apply, e.g. a preview count. */
  trailing?: React.ReactNode;
  /** Saved queries for this destination. Omit to hide the strip entirely. */
  saved?: import("@/data").SavedQuery[];
  /** Re-read the saved list after one is added, copied or removed. */
  onSavedChanged?: () => void;
}

export function QueryBuilder({
  draft,
  onDraftChange,
  applied,
  destination,
  metadata,
  onApply,
  onReset,
  busy = false,
  trailing,
  saved,
  onSavedChanged,
}: QueryBuilderProps) {
  const problems = useMemo(
    () => validateQuery(draft, destination),
    [draft, destination],
  );
  const general = generalProblems(problems);
  const valid = problems.length === 0;
  const canOr = MATCH_ANY_DESTINATIONS.has(destination);
  const changes = countChanges(draft, applied);
  const canApply = valid && !busy && (applied === null || changes > 0);

  const setClause = (index: number, clause: QueryClause) =>
    onDraftChange({
      ...draft,
      clauses: draft.clauses.map((c, i) => (i === index ? clause : c)),
    });

  const removeClause = (index: number) =>
    onDraftChange({ ...draft, clauses: draft.clauses.filter((_, i) => i !== index) });

  const addClause = () =>
    onDraftChange({ ...draft, clauses: [...draft.clauses, newClause(destination)] });

  const submit = () => {
    if (canApply) onApply();
  };

  return (
    <div
      className="flex flex-col gap-3.5"
      onKeyDown={(e) => {
        // ⌘↵ / Ctrl+↵ applies. Stopped here so a global shortcut elsewhere in the
        // shell does not also fire from a panel that has nothing to do with it.
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
          e.preventDefault();
          e.stopPropagation();
          submit();
        }
      }}
    >
      {saved !== undefined && onSavedChanged !== undefined && (
        <SavedQueries
          queries={saved}
          destination={destination}
          draft={draft}
          // Loading fills the DRAFT only. Nothing runs until Apply — the same
          // rule as every other control here.
          onLoad={onDraftChange}
          onChanged={onSavedChanged}
          canSave={valid}
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[10.5px] font-bold tracking-[.11em] text-label">
          MATCH
        </span>
        {canOr ? (
          <Segmented
            value={draft.match}
            onChange={(match) => onDraftChange({ ...draft, match })}
            options={[
              { value: "all" as const, label: "All conditions" },
              { value: "any" as const, label: "Any condition" },
            ]}
          />
        ) : (
          // GitHub search ANDs every qualifier and has no OR. Offering the toggle
          // and then refusing Apply would be a control that cannot work; saying so
          // once is the honest version.
          <span className="text-[11.5px] text-faint">
            All conditions — GitHub search cannot match “any”.
          </span>
        )}
        {metadata.fetchedAt && (
          <span className="ml-auto text-[11.5px] text-faint">
            {metadata.stale
              ? `Fields may be out of date — ${metadata.message}`
              : `Fields read ${readAgo(metadata.fetchedAt)}`}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-3">
        {draft.clauses.map((clause, index) => (
          <ClauseRow
            key={index}
            clause={clause}
            index={index}
            destination={destination}
            metadata={metadata}
            allClauses={draft.clauses}
            problems={problemsForClause(problems, index)}
            showLabels={index === 0}
            onChange={(next) => setClause(index, next)}
            onRemove={() => removeClause(index)}
            onSubmit={submit}
          />
        ))}
      </div>

      {general.map((problem) => (
        <p key={problem.message} className="m-0 text-[11.5px] text-warn">
          {problem.message}
        </p>
      ))}

      <div>
        <button
          type="button"
          onClick={addClause}
          className={cn(
            "inline-flex cursor-pointer items-center gap-1.5 rounded-control-lg border border-bd2",
            "bg-card3 px-3 py-[9px] text-[12.5px] font-semibold text-txt3",
            "transition-colors duration-200 hover:bg-bd3",
          )}
        >
          <Icon name="plus" size={13} strokeWidth={2.4} />
          Add condition
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-bd3 pt-3.5">
        <Button
          variant="primary"
          onClick={submit}
          disabled={!canApply}
          className="h-auto rounded-button px-[18px] py-[10px] text-[13px]"
        >
          {busy ? "Running…" : "Apply"}
        </Button>
        <button
          type="button"
          onClick={onReset}
          disabled={busy}
          className={cn(
            "cursor-pointer rounded-control-lg border border-bd2 bg-card3 px-[14px] py-[9px]",
            "text-[12.5px] font-semibold text-txt3 transition-colors hover:bg-bd3",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          Reset
        </button>

        {/* The draft/applied split, said out loud. Without this line an edit that
            has not been applied looks exactly like one that has. */}
        {changes > 0 && applied !== null && (
          <Pill tone="warn" size="sm">
            {changes} {changes === 1 ? "change" : "changes"} not applied
          </Pill>
        )}

        <span className="min-w-0 flex-1 truncate text-[11.5px] text-muted">
          {applied ? describeQuery(applied) : describeQuery(draft)}
        </span>

        {trailing}
      </div>
    </div>
  );
}

/** `4 minutes ago`; under a minute is `just now`, as a person would say it. */
export function readAgo(iso: string, now: number = Date.now()): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "at an unknown time";
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
