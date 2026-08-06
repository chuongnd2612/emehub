// What each clause field offers as values, derived from the connection's own
// provider metadata.
//
// **Nothing here is a hardcoded list of states, people, areas or tags.** A list
// the app invented would build queries that match nothing, and the user would read
// that as "there is no work" rather than as our mistake. Where the metadata has
// nothing to offer, the control falls back to a plain input and the user types.
//
// This is the whole reason slice 3 extended and cached the metadata read: the old
// filter derived its options from work items **already mirrored**, so it could
// never offer a value you had not already imported — which is useless for deciding
// what to import.

import type { WorkItemMetadata } from "@/data";
import type { ClauseField, ClauseOperator } from "@/data/ticketQuery";

export interface ValueOption {
  value: string;
  label: string;
  /** Indentation depth for tree paths — areas and iterations. */
  depth?: number;
  /** Groups states under their work item type. */
  group?: string;
}

/**
 * Macros offered by name, so they are discoverable rather than folklore.
 *
 * Only these two are worth surfacing: `@Me` is what an assignee filter almost
 * always wants, and `@CurrentIteration` saves picking a sprint that goes stale
 * every fortnight. The date macros are offered as hint text instead — `@Today - 7`
 * takes an argument, so it belongs in a field rather than a list.
 */
const ASSIGNEE_MACRO: ValueOption = { value: "@Me", label: "me (@Me)" };
const ITERATION_MACRO: ValueOption = {
  value: "@CurrentIteration",
  label: "current sprint (@CurrentIteration)",
};

/**
 * The states to offer, narrowed to the work item types the query already names.
 *
 * A Bug and a User Story do not share a state set. If the query says
 * `workItemType is Bug`, offering `Committed` builds a clause that matches
 * nothing — so the state picker follows the type picker, and groups what is left
 * by the type it belongs to.
 *
 * With no type named, every state is offered, ungrouped.
 */
export function stateOptions(
  metadata: WorkItemMetadata,
  namedTypes: string[],
): ValueOption[] {
  const types = metadata.workItemTypes.filter(
    (type) => namedTypes.length === 0 || namedTypes.includes(type.name),
  );
  if (types.length === 0) {
    return metadata.states.map((state) => ({ value: state, label: state }));
  }
  if (types.length === 1) {
    return types[0].states.map((state) => ({ value: state, label: state }));
  }
  const seen = new Set<string>();
  const out: ValueOption[] = [];
  for (const type of types) {
    for (const state of type.states) {
      const key = `${type.name}:${state}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ value: state, label: state, group: type.name });
    }
  }
  return out;
}

const nodes = (list: WorkItemMetadata["areaPaths"]): ValueOption[] =>
  list.map((node) => ({ value: node.path, label: node.name, depth: node.depth }));

/**
 * The options for one field, or an empty list meaning "let them type".
 *
 * `namedTypes` is the set of work item types the rest of the query names, which
 * only `state` uses.
 */
export function valueOptions(
  field: ClauseField,
  metadata: WorkItemMetadata,
  namedTypes: string[] = [],
): ValueOption[] {
  switch (field) {
    case "workItemType":
      return metadata.workItemTypes.map((t) => ({ value: t.name, label: t.name }));
    case "state":
      return stateOptions(metadata, namedTypes);
    case "assignee":
      return [
        ASSIGNEE_MACRO,
        ...metadata.members.map((m) => ({
          value: m.uniqueName,
          label: m.displayName || m.uniqueName,
        })),
      ];
    case "areaPath":
      return nodes(metadata.areaPaths);
    case "iterationPath":
      return [ITERATION_MACRO, ...nodes(metadata.iterationPaths)];
    case "tags":
      return metadata.tags.map((tag) => ({ value: tag, label: tag }));
    case "epic":
      return metadata.epics.map((e) => ({ value: e.key, label: e.name || e.key }));
    default:
      // title, changedSince, createdSince, parentId, priority — free text.
      return [];
  }
}

/**
 * What to say under a field that has no options to offer.
 *
 * Without this a free-text box is a guess: nobody knows that `changedSince`
 * accepts `@Today - 7`, or that `title` matches a substring rather than the whole
 * thing.
 */
export const VALUE_HELP: Partial<Record<ClauseField, string>> = {
  title: "Matched as a substring, as the provider matches it.",
  tags: "Matched as a substring of the tag list.",
  changedSince: "A date, or a macro: @Today, @Today - 7.",
  createdSince: "A date, or a macro: @Today, @Today - 30.",
  parentId: "The parent work item's id.",
  priority: "The provider's own priority value, e.g. 1.",
};

/** The work item types a query names positively — what narrows the state list. */
export function namedTypesIn(
  clauses: { field: ClauseField; operator: ClauseOperator; values: string[] }[],
): string[] {
  const out = new Set<string>();
  for (const clause of clauses) {
    // Only positive clauses narrow: "type is not Bug" says nothing about which
    // states are on the table.
    if (clause.field !== "workItemType") continue;
    if (clause.operator !== "is" && clause.operator !== "in") continue;
    clause.values.filter(Boolean).forEach((value) => out.add(value));
  }
  return [...out];
}
