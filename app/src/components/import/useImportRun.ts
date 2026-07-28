// Handoff › Async behaviours — "Import now: button label → `Importing…` +
// spinning icon, then success toast. 1500 ms."
//
// The spinner lives on the CALLER's button (the Tickets toolbar today, the
// Overview quick action later), so the run state is a hook rather than dialog
// state: mount `<ImportDialog>` anywhere, drive its `onImport` with `run`, and
// render `importing` on whichever control opened it.

import { useCallback, useEffect, useRef, useState } from "react";
import { runImport, type ImportRequest } from "@/data";
import { toast } from "@/components/ui";

export interface ImportRun {
  /** True from "Import now" until the 1500 ms pull resolves. */
  importing: boolean;
  /** Fire an import. Resolves when the toast has been shown. */
  run: (request: ImportRequest) => Promise<void>;
}

export function useImportRun(): ImportRun {
  const [importing, setImporting] = useState(false);
  const alive = useRef(true);

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
        `${result.count} work items pulled from ${result.provider} · ${result.scopeLabel}`,
        "ok",
      );
    } finally {
      if (alive.current) setImporting(false);
    }
  }, []);

  return { importing, run };
}
