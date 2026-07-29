// Handoff › 5. Import dialog › Basic — the three "WHAT TO PULL" radio rows.
//
// They map onto `SyncRequest.mode`: `sprint` (the connection's current sprint),
// `assigned` (the authenticated identity's items) and anything else, which the
// adapters read as "everything matching the filters".
//
// The handoff's `~24 items` / `~9 items` / `~118 items` hints are gone. Nothing
// counts a provider-side scope before the pull happens — `GET /connections/
// {id}/sprints` lists sprints, not sizes — so those numbers could only ever be
// the prototype's invention rendered next to real controls.

import type { ImportScope } from "@/data";

export interface ImportScopeOption {
  key: ImportScope;
  label: string;
  /** One-line description under the label. `{provider}` is substituted. */
  description: string;
}

export const IMPORT_SCOPE_OPTIONS: ImportScopeOption[] = [
  {
    key: "sprint",
    label: "Active sprint",
    description: "Pull the current sprint of {provider}",
  },
  {
    key: "assigned",
    label: "Assigned to me",
    description: "Everything currently on your plate",
  },
  {
    key: "all",
    label: "All open work items",
    description: "Every open item in the connected project",
  },
];
