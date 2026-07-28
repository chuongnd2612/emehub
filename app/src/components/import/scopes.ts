// Handoff › 5. Import dialog › Basic — the three "WHAT TO PULL" radio rows.
//
// `IMPORT_SCOPES` exists in `data/fixtures/tickets.ts` but is NOT re-exported
// from `@/data`, and screens may only import from `@/data` (never a fixture
// path). The copy is final either way, so it lives here next to the dialog that
// renders it. Fold it into the data layer if an endpoint ever returns counts.

import type { ImportScope } from "@/data";

export interface ImportScopeOption {
  key: ImportScope;
  label: string;
  /** One-line description under the label. `{provider}` is substituted. */
  description: string;
  /** Mono right-aligned estimate. */
  count: string;
}

export const IMPORT_SCOPE_OPTIONS: ImportScopeOption[] = [
  {
    key: "sprint",
    label: "Active sprint",
    description: "Pull the current sprint of {provider}",
    count: "~24 items",
  },
  {
    key: "assigned",
    label: "Assigned to me",
    description: "Everything currently on your plate",
    count: "~9 items",
  },
  {
    key: "all",
    label: "All open work items",
    description: "Every open item in the connected project",
    count: "~118 items",
  },
];
