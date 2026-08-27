// Where a project's work items come from — derived, never switched (#221).
//
// ADR 0011 §3, adopted from Q-Agent's ADR 0015 §3: **provider is a property of
// the project.** A provider switch on a ticket list means the same screen can
// show work items from a provider that has nothing to do with the project the
// user believes they are in, and a filter does not fix that — containment does.
// So there is no `?source=` and no switcher anywhere in the ticket flow; the
// source is read from the project's own configured connection.
//
// ## The binding, and the direction that is actually unambiguous
//
// `project_config.work_item_connection_id` is a single column on the project, so
// **project → connection is single-valued** and deriving the provider from it
// cannot be ambiguous.
//
// The reverse is not true, and it is worth writing down because #217 found it in
// the live database: one connection is bound to TWO projects (`surency-2` and
// `surency-3` both point at connection 8). That makes *connection → project*
// non-unique — which is why #217 could not backfill `Ticket.project_id` from
// `connection_id` alone — but it does not touch this derivation. Two projects
// sharing a connection simply derive the same provider, which is the truth.
//
// ## What can still fail, and what the UI does about it
//
// Four outcomes, kept apart because collapsing any two of them means guessing a
// provider, and a guessed provider is the exact defect this slice removes:
//
//   `resolved`     the connection resolves to exactly one provider — the source
//   `none`         no work-item connection is configured on the project at all
//   `unresolved`   a connection id that resolves to no connection this caller
//                  can see (removed, or owned by someone else), or one whose
//                  kind is not a provider the UI knows
//   `unavailable`  the config or the connection list could not be read — a
//                  different fact from "there is none", and never rendered as one
//
// Only `resolved` renders a ticket list. Everything else renders an honest state
// that says which of the four it is and points at where the binding is set.

import { getConnectionsWithCapability } from "./connections";
import type { Project, ProviderKey } from "./types";

export type TicketSource =
  | {
      state: "resolved";
      provider: ProviderKey;
      connectionId: number;
      /** `"<Provider name> · <connection label>"`, as the config picker spells it. */
      label: string;
    }
  | { state: "none" }
  | { state: "unresolved"; connectionId: number }
  | { state: "unavailable" };

/**
 * The project's ticket source.
 *
 * Reads the connection list once. `project.config` comes from the project detail
 * read the caller already did, so nothing here re-fetches the project.
 */
export const resolveTicketSource = async (
  project: Project,
): Promise<TicketSource> => {
  // `config === null` means the config read failed or was not permitted — not
  // that the project has no work-item connection. Saying "not connected" here
  // would be a claim the app cannot support.
  if (project.config === null) return { state: "unavailable" };

  const connectionId = project.config.workItemConnectionId;
  if (connectionId === null) return { state: "none" };

  let connections: { id: number; label: string; provider: ProviderKey }[];
  try {
    connections = await getConnectionsWithCapability("work_item");
  } catch {
    return { state: "unavailable" };
  }

  const matches = connections.filter((c) => c.id === connectionId);
  // Exactly one, or nothing is assumed. `> 1` cannot happen — `id` is the
  // connection's primary key — but the check is what makes "exactly one" a
  // property of this function rather than an assumption about the endpoint.
  if (matches.length !== 1) return { state: "unresolved", connectionId };

  const match = matches[0];
  return {
    state: "resolved",
    provider: match.provider,
    connectionId,
    label: match.label,
  };
};
