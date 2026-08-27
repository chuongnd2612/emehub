// Saved ticket queries — the shipped presets and the user's own.
//
//   GET    /ticket-queries?destination=&projectId=  listSavedQueries
//   POST   /ticket-queries                          saveQuery
//   PATCH  /ticket-queries/{id}                     renameQuery / replaceQuery
//   DELETE /ticket-queries/{id}                     deleteSavedQuery
//   POST   /ticket-queries/{id}/duplicate           duplicateQuery
//
// **A built-in answers 409, not 403.** The caller is not being denied a permission
// — the request does not apply to what the row is. So the UI offers Duplicate on a
// preset rather than a disabled Edit, and the message names that way forward. The
// 409's own sentence is surfaced verbatim; it is never swallowed.
//
// **Filtered by destination, always.** A query naming `areaPath` cannot run on Jira
// and `parentId` has no column in the mirror, so a list unfiltered by destination
// would offer queries that are refused the moment they are applied.
//
// ## `projectId` — the container axis (#222 backend, #221 frontend)
//
// Under containment a saved *ticket* query is ticket-shaped data, so it has a
// project (ADR 0011 › *Decisions on the handoff's open questions*, 1, which
// reverses the model's own docstring). The parameter is threaded here rather than
// invented: `GET ?projectId=` returns that project's rows **plus** the
// workspace-wide ones, `POST`/`duplicate` bind the new row to the project, and
// `PATCH` forbids the field outright — a query's project is immutable, so
// re-homing one is a duplicate into the other project, not an edit.
//
// Omitting `projectId` is a different question, not a lax version of the same
// one: it means workspace-wide, which is what every row predating #222 stays and
// what every built-in is.

import { api } from "@/lib/api";
import type { Destination, TicketQuery } from "./ticketQuery";

export interface SavedQuery {
  id: number;
  name: string;
  destination: Destination;
  query: TicketQuery;
  /** Derived hub-side from the clauses, so it cannot disagree with them. */
  description: string;
  /** A shipped preset: usable and copyable, never editable or deletable. */
  builtIn: boolean;
  /** Lives in the shared namespace rather than one member's. */
  shared: boolean;
  /**
   * The project row this query belongs to, or `null` for workspace-wide (#222).
   *
   * `null` is the honest answer for a built-in and for anything saved before the
   * project axis existed — both are offered inside every project on their
   * destination, which is why the list can show a project's own rows and the
   * workspace's together without either pretending to be the other.
   */
  projectId: number | null;
  createdAt: string | null;
}

/**
 * The saved queries offerable on one destination.
 *
 * `projectId` narrows to that project's rows **plus** the workspace-wide ones —
 * never another project's. Omitting it lists everything the caller may see,
 * which is the management view rather than the in-project one.
 */
export const listSavedQueries = (
  destination: Destination,
  projectId?: number,
): Promise<SavedQuery[]> =>
  api.get<SavedQuery[]>("/ticket-queries", { query: { destination, projectId } });

export const saveQuery = (options: {
  name: string;
  destination: Destination;
  query: TicketQuery;
  shared?: boolean;
  /** Bind the query to a project. Omit for workspace-wide. */
  projectId?: number;
}): Promise<SavedQuery> =>
  api.post<SavedQuery>("/ticket-queries", {
    name: options.name,
    destination: options.destination,
    query: options.query,
    shared: options.shared ?? false,
    projectId: options.projectId,
  });

export const renameQuery = (id: number, name: string): Promise<SavedQuery> =>
  api.patch<SavedQuery>(`/ticket-queries/${id}`, { name });

export const replaceQuery = (id: number, query: TicketQuery): Promise<SavedQuery> =>
  api.patch<SavedQuery>(`/ticket-queries/${id}`, { query });

/**
 * Always yields an editable copy the caller owns — including from a built-in.
 *
 * `projectId` copies into that project, which is how a project gets its own
 * version of a shipped preset. Omitted, the copy keeps the source's own scope.
 */
export const duplicateQuery = (
  id: number,
  options?: { name?: string; projectId?: number },
): Promise<SavedQuery> =>
  api.post<SavedQuery>(`/ticket-queries/${id}/duplicate`, {
    name: options?.name,
    projectId: options?.projectId,
  });

export const deleteSavedQuery = async (id: number): Promise<void> => {
  await api.delete(`/ticket-queries/${id}`);
};
