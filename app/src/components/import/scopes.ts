// Handoff › 5. Import dialog › Basic — the "WHAT TO PULL" radio rows.
//
// ## They are presets now, not a mode
//
// They used to map onto `SyncRequest.mode`, which the hub no longer has (#130):
// every one of them is a clause query, and Basic is a shortcut to three common
// ones rather than a different way of asking. Which means Advanced can *edit* what
// Basic picked, and both paths go down exactly one code path server-side.
//
// ## A scope a provider has no equivalent for is not offered
//
// GitHub has no sprints, so there is no honest "Active sprint" for it — offering
// one and quietly pulling every open issue instead is precisely the silent
// widening the capability matrix exists to prevent. `query()` returns null and the
// option is left out.
//
// ## Why the state names are listed rather than negated
//
// There is no provider-neutral spelling of "open". Azure DevOps process templates
// disagree among themselves (Agile closes to `Closed`, Scrum to `Done`, Basic to
// `Done`), Jira adds `Resolved`, and GitHub has literally two states. So each
// destination carries its own list of what counts as finished. This mirrors
// `saved_queries.DONE_STATES` server-side; if one changes, both should.
//
// The handoff's `~24 items` / `~9 items` hints stay gone from the labels — but the
// count is no longer unknowable: Advanced previews a real total before importing.

import type { ImportScope } from "@/data";
import type { Destination, TicketQuery } from "@/data/ticketQuery";

/** What "finished" is called, per destination. See the note above. */
const DONE_STATES: Record<Destination, string[]> = {
  azure_devops: ["Closed", "Done", "Completed", "Removed"],
  jira: ["Done", "Closed", "Resolved"],
  github: ["closed"],
  mirror: ["Closed", "Done", "Completed"],
};

const query = (
  clauses: TicketQuery["clauses"],
  match: TicketQuery["match"] = "all",
): TicketQuery => ({
  clauses,
  match,
  sort: { field: "changedDate", direction: "desc" },
});

/**
 * "Not finished", in whatever `destination` can actually express.
 *
 * GitHub's matrix allows only `is`/`isNot` on state — because an issue has exactly
 * two of them, so "not closed" *is* "open" and a list would be pretending. Every
 * other destination has real state names, hence `notIn`.
 */
const openClause = (destination: Destination): TicketQuery["clauses"][number] =>
  destination === "github"
    ? { field: "state", operator: "is", values: ["open"] }
    : { field: "state", operator: "notIn", values: DONE_STATES[destination] };

export interface ImportScopeOption {
  key: ImportScope;
  label: string;
  /** One-line description under the label. `{provider}` is substituted. */
  description: string;
  /**
   * The query this scope means for `destination`, or null when the provider has
   * no equivalent — in which case the option is not offered at all.
   */
  query: (destination: Destination) => TicketQuery | null;
}

export const IMPORT_SCOPE_OPTIONS: ImportScopeOption[] = [
  {
    key: "sprint",
    label: "Active sprint",
    description: "Pull the current sprint of {provider}",
    query: (destination) => {
      // GitHub has no sprint concept, and neither does the mirror's own view of
      // one — a sprint there is just a name that came from somewhere else.
      if (destination === "github") return null;
      return query([
        {
          field: "iterationPath",
          // ADO wants the path prefix, so every child iteration counts; Jira
          // matches a sprint by name, and `@CurrentIteration` compiles to
          // `sprint in openSprints()`.
          operator: destination === "azure_devops" ? "under" : "is",
          values: ["@CurrentIteration"],
        },
      ]);
    },
  },
  {
    key: "assigned",
    label: "Assigned to me",
    description: "Everything currently on your plate",
    query: (destination) =>
      query([
        { field: "assignee", operator: "is", values: ["@Me"] },
        openClause(destination),
      ]),
  },
  {
    key: "all",
    label: "All open work items",
    description: "Every open item in the connected project",
    query: (destination) => query([openClause(destination)]),
  },
];

/** The scopes `destination` can actually express, in order. */
export const scopesFor = (destination: Destination): ImportScopeOption[] =>
  IMPORT_SCOPE_OPTIONS.filter((option) => option.query(destination) !== null);
