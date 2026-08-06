// The ticket query model — clauses, the capability matrix, validation.
//
// The client half of `api/app/services/ticket_query.py`. **Both halves must agree.**
// The client validates to disable Apply before anything is sent; the API validates
// to refuse a request the client did not build. If they drift, "Apply is greyed
// out" stops matching "400 Bad Request" and the user is told two different stories.
//
// Ported from `dev-assistant/packages/shared/src/filter.ts`, which keeps one
// definition for both sides in a shared package. We cannot share a module across
// Python and TypeScript, so the tables are duplicated deliberately and a backend
// test pins the pairing.
//
// ## What a query is
//
// A **flat** list of clauses plus one global `match`. No nesting, no per-clause
// conjunction — a deliberate limit carried over from the source, because mixed
// AND/OR trees are a large jump in both UI and compiler complexity and nothing
// asked for so far needs them.
//
// ## Why the capability matrix exists
//
// One builder serves Azure DevOps, Jira, GitHub and the hub's own mirror, and they
// genuinely differ: JQL has no area-path tree, GitHub's search API has qualifiers
// rather than a query language. The matrix says what each destination can run so
// the UI never offers a clause that would be **silently dropped** — and a dropped
// clause returns *more* tickets than were asked for, which is the worst way for a
// filter to fail.

export type ClauseField =
  | "workItemType"
  | "state"
  | "assignee"
  | "areaPath"
  | "iterationPath"
  | "tags"
  | "title"
  | "changedSince"
  | "createdSince"
  | "parentId"
  | "priority"
  | "epic";

export type ClauseOperator =
  | "is"
  | "isNot"
  | "in"
  | "notIn"
  | "contains"
  | "notContains"
  | "under"
  | "onOrAfter"
  | "onOrBefore";

export type SortField = "changedDate" | "createdDate" | "id" | "state";
export type SortDirection = "asc" | "desc";

/** Where a query is going. `mirror` is the hub's own `tickets` table. */
export type Destination = "azure_devops" | "jira" | "github" | "mirror";

export interface QueryClause {
  field: ClauseField;
  operator: ClauseOperator;
  values: string[];
}

export interface TicketQuery {
  clauses: QueryClause[];
  /** `all` joins with AND, `any` with OR. Flat — see the header. */
  match: "all" | "any";
  sort: { field: SortField; direction: SortDirection };
}

/** The only operators that take more than one value. */
export const LIST_OPERATORS: readonly ClauseOperator[] = ["in", "notIn"];

export const takesList = (operator: ClauseOperator): boolean =>
  LIST_OPERATORS.includes(operator);

export const FIELD_LABELS: Record<ClauseField, string> = {
  workItemType: "work item type",
  state: "state",
  assignee: "assigned to",
  areaPath: "area path",
  iterationPath: "sprint",
  tags: "tags",
  title: "title",
  changedSince: "changed date",
  createdSince: "created date",
  parentId: "parent",
  priority: "priority",
  epic: "epic",
};

export const OPERATOR_LABELS: Record<ClauseOperator, string> = {
  is: "is",
  isNot: "is not",
  in: "is any of",
  notIn: "is none of",
  contains: "contains",
  notContains: "does not contain",
  under: "under",
  onOrAfter: "on or after",
  onOrBefore: "on or before",
};

/* ── the capability matrix ───────────────────────────────────────────────── */

// Named operator sets, so the matrix reads as intent rather than as lists.
// `PATH` leads with `under` because `=` on an area or iteration path silently
// excludes every child, which is almost never what was meant. `TEXT` is substring
// only. `DATE` gets the range operators and nothing else — a work item is never
// changed *at* exactly a date.
const EQUALITY: ClauseOperator[] = ["is", "isNot", "in", "notIn"];
const PATH: ClauseOperator[] = ["under", "is", "isNot"];
const TEXT: ClauseOperator[] = ["contains", "notContains"];
const DATE: ClauseOperator[] = ["onOrAfter", "onOrBefore"];

/**
 * What each destination can actually run. Mirrors `CAPABILITIES` in
 * `api/app/services/ticket_query.py` — keep them in step.
 *
 * The insertion order is the order the UI offers fields in.
 */
export const CAPABILITIES: Record<
  Destination,
  Partial<Record<ClauseField, ClauseOperator[]>>
> = {
  azure_devops: {
    workItemType: EQUALITY,
    state: EQUALITY,
    assignee: EQUALITY,
    areaPath: PATH,
    iterationPath: PATH,
    tags: TEXT,
    title: TEXT,
    changedSince: DATE,
    createdSince: DATE,
    parentId: EQUALITY,
    priority: EQUALITY,
  },
  jira: {
    workItemType: EQUALITY,
    state: EQUALITY,
    assignee: EQUALITY,
    iterationPath: ["is", "isNot", "in", "notIn"],
    tags: EQUALITY,
    title: TEXT,
    changedSince: DATE,
    createdSince: DATE,
    parentId: ["is", "isNot"],
    priority: EQUALITY,
    epic: ["is", "isNot", "in", "notIn"],
  },
  github: {
    workItemType: ["is"],
    state: ["is", "isNot"],
    assignee: ["is", "isNot"],
    tags: ["is", "isNot", "in"],
    title: ["contains"],
    changedSince: DATE,
    createdSince: DATE,
  },
  mirror: {
    workItemType: EQUALITY,
    state: EQUALITY,
    assignee: EQUALITY,
    areaPath: PATH,
    iterationPath: PATH,
    tags: TEXT,
    title: TEXT,
    changedSince: DATE,
    createdSince: DATE,
    priority: EQUALITY,
    epic: EQUALITY,
  },
};

/** The fields `destination` can filter on, in the order to offer them. */
export const fieldsFor = (destination: Destination): ClauseField[] =>
  Object.keys(CAPABILITIES[destination]) as ClauseField[];

/** The operators `destination` allows on `field`; empty when unsupported. */
export const operatorsFor = (
  destination: Destination,
  field: ClauseField,
): ClauseOperator[] => CAPABILITIES[destination][field] ?? [];

/* ── validation ──────────────────────────────────────────────────────────── */

export interface QueryProblem {
  message: string;
  /**
   * Which clause the message belongs to, so the UI can print it under that row.
   *
   * `dev-assistant` encoded this in the message text (`Condition 3: …`) and
   * re-parsed it on the client; carrying it as a field means no sentence has to
   * be parsed to lay out a form.
   */
  clauseIndex: number | null;
}

const phrase = (values: string[]): string =>
  values.length <= 1
    ? (values[0] ?? "")
    : `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;

const filled = (clause: QueryClause): string[] =>
  clause.values.filter((value) => value.trim() !== "");

/**
 * Clauses with at least one non-blank value — what actually gets compiled.
 *
 * A half-typed clause must not become `field = ''`, which matches nothing and
 * reads as "there is no work" rather than as unfinished input.
 */
export const effectiveClauses = (query: TicketQuery): QueryClause[] =>
  query.clauses.filter((clause) => filled(clause).length > 0);

/** Every problem with `query` for `destination`; empty means valid. */
export function validateQuery(
  query: TicketQuery,
  destination: Destination,
): QueryProblem[] {
  const problems: QueryProblem[] = [];
  const add = (message: string, clauseIndex: number | null = null) =>
    problems.push({ message, clauseIndex });

  if (query.clauses.length === 0) add("Add at least one condition.");
  if (query.match !== "all" && query.match !== "any") {
    add(`“${String(query.match)}” is not a way to combine conditions.`);
  }

  query.clauses.forEach((clause, index) => {
    const allowed = operatorsFor(destination, clause.field);
    const label = FIELD_LABELS[clause.field] ?? String(clause.field);

    if (allowed.length === 0) {
      add(
        clause.field in FIELD_LABELS
          ? `${label} cannot be filtered on this provider.`
          : `“${String(clause.field)}” is not a field that can be filtered.`,
        index,
      );
      return;
    }

    if (!allowed.includes(clause.operator)) {
      const readable = OPERATOR_LABELS[clause.operator] ?? String(clause.operator);
      const options = phrase(allowed.map((op) => OPERATOR_LABELS[op]));
      add(`${label} cannot be filtered with “${readable}”. Use ${options}.`, index);
      return;
    }

    const blanks = clause.values.filter((value) => value.trim() === "");
    if (clause.values.length === 0 || blanks.length === clause.values.length) {
      // No values, or every one blank: the control is untouched, so ask for a
      // value rather than reporting an "empty value" — which reads as a mistake
      // the user made rather than one still to make.
      add(`Give ${label} a value.`, index);
    } else if (blanks.length > 0) {
      add(`One of the ${label} values is empty.`, index);
    }

    if (!takesList(clause.operator) && clause.values.length > 1) {
      const readable = OPERATOR_LABELS[clause.operator];
      add(
        `“${readable}” takes one value, not ${clause.values.length}. ` +
          "Use “is any of” for several.",
        index,
      );
    }
  });

  return problems;
}

export const queryIsValid = (query: TicketQuery, destination: Destination): boolean =>
  validateQuery(query, destination).length === 0;

/** The problems for one clause row, for printing under it. */
export const problemsForClause = (
  problems: QueryProblem[],
  index: number,
): QueryProblem[] => problems.filter((problem) => problem.clauseIndex === index);

/** The problems that belong to the query as a whole rather than to a row. */
export const generalProblems = (problems: QueryProblem[]): QueryProblem[] =>
  problems.filter((problem) => problem.clauseIndex === null);

/* ── prose ───────────────────────────────────────────────────────────────── */

/**
 * The query as a person would say it — `assigned to is @Me · state is any of …`.
 *
 * Deliberately lossy: prose for a confirmation line, never something to compile
 * back from.
 */
export function describeQuery(query: TicketQuery): string {
  const parts = effectiveClauses(query).map((clause) => {
    const label = FIELD_LABELS[clause.field] ?? String(clause.field);
    const operator = OPERATOR_LABELS[clause.operator] ?? String(clause.operator);
    return `${label} ${operator} ${phrase(filled(clause))}`;
  });
  if (parts.length === 0) return "everything in the project";
  return parts.join(query.match === "all" ? " · " : " or ");
}

/* ── construction helpers the UI needs ───────────────────────────────────── */

/** An empty query for `destination`, opening on its first offerable field. */
export function emptyQuery(destination: Destination): TicketQuery {
  return {
    clauses: [newClause(destination)],
    match: "all",
    sort: { field: "changedDate", direction: "desc" },
  };
}

/**
 * A fresh clause on `destination`'s first field, with that field's first operator.
 *
 * `assignee` opens on `@Me` because it is overwhelmingly the value wanted, and
 * it is the one macro worth pre-filling.
 */
export function newClause(destination: Destination): QueryClause {
  const field = fieldsFor(destination)[0] ?? "state";
  return {
    field,
    operator: operatorsFor(destination, field)[0] ?? "is",
    values: field === "assignee" ? ["@Me"] : [""],
  };
}

/**
 * `clause` moved onto `field` — operator reset to the first the matrix allows,
 * values cleared.
 *
 * Keeping the old operator would leave a state/`under` pair that validation then
 * has to reject, which is a worse experience than silently picking the sane one.
 */
export function withField(
  clause: QueryClause,
  field: ClauseField,
  destination: Destination,
): QueryClause {
  return {
    field,
    operator: operatorsFor(destination, field)[0] ?? "is",
    values: field === "assignee" ? ["@Me"] : [""],
  };
}

/**
 * `clause` moved onto `operator`, remapping values across the list boundary.
 *
 * Into a list: keep everything non-blank. Out of a list: keep the first, because
 * dropping to one value silently is better than refusing the change.
 */
export function withOperator(
  clause: QueryClause,
  operator: ClauseOperator,
): QueryClause {
  const wasList = takesList(clause.operator);
  const isList = takesList(operator);
  if (wasList === isList) return { ...clause, operator };
  const values = isList ? filled(clause) : [filled(clause)[0] ?? ""];
  return { ...clause, operator, values: values.length > 0 ? values : [""] };
}
