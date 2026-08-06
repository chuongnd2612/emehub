// Saved queries — the shipped presets and the user's own, above the clause rows.
//
// One list, both kinds, told apart by a `Preset` pill. That is deliberate: they do
// the same job, and splitting them into two lists would make the shipped ones feel
// like documentation rather than something to click.
//
// **A preset offers Duplicate, not a disabled Edit.** The hub answers 409 with
// "Duplicate it and edit the copy", and this mirrors that: the answer to "I want
// that but slightly different" is one click, which is what keeps a read-only preset
// from being a dead end.
//
// Loading a query only fills the **draft** — it does not run. Same rule as the rest
// of the builder: nothing queries until Apply.

import { useState } from "react";

import { Icon, Input, Pill, toast } from "@/components/ui";
import {
  deleteSavedQuery,
  duplicateQuery,
  saveQuery,
  type SavedQuery,
} from "@/data";
import type { Destination, TicketQuery } from "@/data/ticketQuery";
import { cn } from "@/lib/cn";

export interface SavedQueriesProps {
  queries: SavedQuery[];
  destination: Destination;
  /** The query to save when the user names one. */
  draft: TicketQuery;
  /** Fills the draft. Never runs it — Apply does that. */
  onLoad: (query: TicketQuery) => void;
  /** Re-read the list after a change. */
  onChanged: () => void;
  /** False while the draft is invalid, so an unsaveable query cannot be saved. */
  canSave: boolean;
}

export function SavedQueries({
  queries,
  destination,
  draft,
  onLoad,
  onChanged,
  canSave,
}: SavedQueriesProps) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await saveQuery({ name: trimmed, destination, query: draft });
      setNaming(false);
      setName("");
      onChanged();
      toast("Query saved");
    } catch (err) {
      // A 409 here is a name clash, and its message says so — worth showing
      // verbatim rather than replaced with "could not save".
      toast(
        "Could not save the query",
        "warn",
        err instanceof Error ? err.message : "The hub rejected it.",
      );
    } finally {
      setBusy(false);
    }
  };

  const act = async (run: () => Promise<unknown>, failure: string) => {
    setBusy(true);
    try {
      await run();
      onChanged();
    } catch (err) {
      toast(failure, "warn", err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-3">
        <span className="text-[10.5px] font-bold tracking-[.11em] text-label">
          SAVED
        </span>
        {!naming && (
          <button
            type="button"
            onClick={() => setNaming(true)}
            disabled={!canSave}
            title={canSave ? undefined : "Finish the query first"}
            className={cn(
              "ml-auto cursor-pointer rounded-control border border-bd2 bg-card3 px-2.5 py-1",
              "text-[11.5px] font-semibold text-txt3 transition-colors hover:bg-bd3",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            Save this query
          </button>
        )}
      </div>

      {naming && (
        <div className="flex items-center gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void save();
              }
              if (e.key === "Escape") setNaming(false);
            }}
            placeholder="Name this query"
            className="h-9 max-w-[260px]"
            autoFocus
            aria-label="Query name"
          />
          <button
            type="button"
            onClick={() => void save()}
            disabled={busy || !name.trim()}
            className={cn(
              "cursor-pointer rounded-control border border-pb bg-pt px-3 py-[7px]",
              "text-[11.5px] font-bold text-ps-text disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => setNaming(false)}
            className="cursor-pointer bg-transparent p-1 text-[11.5px] font-semibold text-muted hover:text-txt3"
          >
            Cancel
          </button>
        </div>
      )}

      {queries.length === 0 ? (
        <p className="m-0 text-[11.5px] text-faint">
          Nothing saved for this provider yet.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {queries.map((saved) => (
            <span
              key={saved.id}
              className={cn(
                "group flex items-center gap-1.5 rounded-control border border-bd2 bg-card3",
                "py-1 pr-1 pl-2.5 transition-colors hover:border-pb",
              )}
            >
              <button
                type="button"
                onClick={() => onLoad(saved.query)}
                title={saved.description}
                className="cursor-pointer bg-transparent p-0 text-[12px] font-semibold text-txt2"
              >
                {saved.name}
              </button>

              {saved.builtIn ? (
                <Pill tone="neutral" size="sm">
                  Preset
                </Pill>
              ) : saved.shared ? (
                <Pill tone="info" size="sm">
                  Shared
                </Pill>
              ) : null}

              {/* A preset offers Duplicate; anything else offers Delete. The hub
                  refuses to edit or delete a built-in (409), so offering either
                  here would be a control that cannot work. */}
              {saved.builtIn ? (
                <button
                  type="button"
                  onClick={() => void act(() => duplicateQuery(saved.id), "Could not duplicate")}
                  disabled={busy}
                  aria-label={`Duplicate ${saved.name}`}
                  title="Duplicate it and edit the copy"
                  className="cursor-pointer bg-transparent p-1 text-txt4 hover:text-ps-text disabled:opacity-50"
                >
                  <Icon name="copy" size={12} strokeWidth={2.3} />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void act(() => deleteSavedQuery(saved.id), "Could not delete")}
                  disabled={busy}
                  aria-label={`Delete ${saved.name}`}
                  className="cursor-pointer bg-transparent p-1 text-txt4 hover:text-danger disabled:opacity-50"
                >
                  <Icon name="close" size={12} strokeWidth={2.4} />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
