// Handoff › Async behaviours — "Import now: button label → `Importing…` +
// spinning icon, then success toast."
//
// The 1500 ms was the prototype's fake timing. The spinner now runs for exactly
// as long as `POST /tickets/sync` takes; no artificial delay is added.
//
// The spinner lives on the CALLER's button (the Tickets toolbar today, the
// Overview quick action too), so the run state is a hook rather than dialog
// state: mount `<ImportDialog>` anywhere, drive its `onImport` with `run`, and
// render `importing` on whichever control opened it.
//
// ## The failure path is a real answer, not a swallowed error
//
// `POST /tickets/sync` answers **404** when no work-item connection of that
// kind is configured, **502** when the provider call fails and **503** when the
// deployment has no adapter layer. Every one of those is information the person
// who pressed Import needs, so the hub's own `detail` message is surfaced
// verbatim in a warn toast — never a silent no-op, and never a success toast
// reading "0 work items pulled", which would read as "the sprint is empty".

import { useCallback, useEffect, useRef, useState } from "react";
import { runImport, type ImportRequest } from "@/data";
import { toast } from "@/components/ui";
import { ApiError } from "@/lib/api";

export interface ImportRun {
  /** True from "Import now" until the sync resolves or fails. */
  importing: boolean;
  /** Fire an import. Resolves when the toast has been shown. */
  run: (request: ImportRequest) => Promise<void>;
}

/** Copy for the statuses the sync endpoint answers with. */
const failureTitle = (status: number): string => {
  if (status === 404) return "No connection to import from";
  if (status === 502) return "The provider rejected the request";
  if (status === 503) return "Import is unavailable";
  return "Import failed";
};

/**
 * @param onImported Called after a successful sync so the caller can re-read
 *   the mirror — the new rows are already in the hub, not in the screen.
 */
export function useImportRun(onImported?: () => void): ImportRun {
  const [importing, setImporting] = useState(false);
  const alive = useRef(true);
  const imported = useRef(onImported);
  imported.current = onImported;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const run = useCallback(async (request: ImportRequest) => {
    setImporting(true);
    try {
      const result = await runImport(request);
      // Copy is final — Handoff § 5. Import dialog › Footer.
      toast(
        "Import complete",
        `${result.count} work item${result.count === 1 ? "" : "s"} pulled from ${result.provider} · ${result.scopeLabel}`,
        "ok",
      );
      imported.current?.();
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      const detail =
        error instanceof ApiError
          ? error.message
          : "The hub did not respond. Try again in a moment.";
      toast(failureTitle(status), detail, "warn");
    } finally {
      if (alive.current) setImporting(false);
    }
  }, []);

  return { importing, run };
}
