// Saved ticket queries — the shipped presets and the user's own.
//
//   GET    /ticket-queries?destination=   listSavedQueries
//   POST   /ticket-queries                saveQuery
//   PATCH  /ticket-queries/{id}           renameQuery / replaceQuery
//   DELETE /ticket-queries/{id}           deleteSavedQuery
//   POST   /ticket-queries/{id}/duplicate duplicateQuery
//
// **A built-in answers 409, not 403.** The caller is not being denied a permission
// — the request does not apply to what the row is. So the UI offers Duplicate on a
// preset rather than a disabled Edit, and the message names that way forward.
//
// **Filtered by destination, always.** A query naming `areaPath` cannot run on Jira
// and `parentId` has no column in the mirror, so a list unfiltered by destination
// would offer queries that are refused the moment they are applied.

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
  createdAt: string | null;
}

export const listSavedQueries = (destination: Destination): Promise<SavedQuery[]> =>
  api.get<SavedQuery[]>("/ticket-queries", { query: { destination } });

export const saveQuery = (options: {
  name: string;
  destination: Destination;
  query: TicketQuery;
  shared?: boolean;
}): Promise<SavedQuery> =>
  api.post<SavedQuery>("/ticket-queries", {
    name: options.name,
    destination: options.destination,
    query: options.query,
    shared: options.shared ?? false,
  });

export const renameQuery = (id: number, name: string): Promise<SavedQuery> =>
  api.patch<SavedQuery>(`/ticket-queries/${id}`, { name });

export const replaceQuery = (id: number, query: TicketQuery): Promise<SavedQuery> =>
  api.patch<SavedQuery>(`/ticket-queries/${id}`, { query });

/** Always yields an editable copy the caller owns — including from a built-in. */
export const duplicateQuery = (id: number, name?: string): Promise<SavedQuery> =>
  api.post<SavedQuery>(`/ticket-queries/${id}/duplicate`, name ? { name } : {});

export const deleteSavedQuery = async (id: number): Promise<void> => {
  await api.delete(`/ticket-queries/${id}`);
};
