// One condition: a field picker, an operator picker, a value control, and remove.
//
// **Nothing in here issues a request.** Every handler edits the draft and stops —
// selecting a field must not run a query. See `QueryBuilder` for why.
//
// The labels and the allowed operators come from `data/ticketQuery`, never from a
// second table here: one definition, and the same one the API validates against.
//
// `Dropdown`'s `ddKey` is globally exclusive — opening one closes every other — so
// every picker on every row needs its own key, hence the `index` in each.

import { Dropdown, Icon, Input, Pill } from "@/components/ui";
import type { WorkItemMetadata } from "@/data";
import {
  FIELD_LABELS,
  OPERATOR_LABELS,
  fieldsFor,
  operatorsFor,
  takesList,
  withField,
  withOperator,
  type ClauseField,
  type ClauseOperator,
  type Destination,
  type QueryClause,
  type QueryProblem,
} from "@/data/ticketQuery";
import { cn } from "@/lib/cn";
import { VALUE_HELP, namedTypesIn, valueOptions, type ValueOption } from "./options";

/** Non-breaking spaces, so a tree path indents inside a plain option label. */
const indent = (depth: number): string => "  ".repeat(Math.min(depth, 6));

const TRIGGER = [
  "flex h-10 w-full cursor-pointer items-center justify-between gap-2 rounded-control-lg",
  "border border-bd2 bg-card3 px-3 text-[12.5px] font-semibold text-txt2",
  "transition-colors duration-200 hover:bg-bd3",
].join(" ");

/**
 * The dropdown panel's z-index.
 *
 * `Dropdown` portals to `document.body` at z-1000, and the Import dialog sits at
 * z-1100 — so inside the dialog the panel renders *behind* the scrim and every
 * picker is unclickable. This was caught by a Playwright run reporting the scrim
 * intercepting the click, not by reading the code.
 *
 * Set unconditionally rather than only when in a dialog: the builder is also used
 * outside one, where a higher panel changes nothing.
 */
const PANEL_Z = "z-[1200]";

export interface ClauseRowProps {
  clause: QueryClause;
  index: number;
  destination: Destination;
  metadata: WorkItemMetadata;
  /** Every clause, so the state picker can narrow to the types named elsewhere. */
  allClauses: QueryClause[];
  problems: QueryProblem[];
  /** True on the first row only — the column labels are printed once. */
  showLabels: boolean;
  onChange: (clause: QueryClause) => void;
  onRemove: () => void;
  /** Enter in a single-value field applies; a search box ignoring Enter feels broken. */
  onSubmit: () => void;
}

export function ClauseRow({
  clause,
  index,
  destination,
  metadata,
  allClauses,
  problems,
  showLabels,
  onChange,
  onRemove,
  onSubmit,
}: ClauseRowProps) {
  const fields = fieldsFor(destination);
  const operators = operatorsFor(destination, clause.field);
  const options = valueOptions(clause.field, metadata, namedTypesIn(allClauses));
  const list = takesList(clause.operator);
  const help = VALUE_HELP[clause.field];

  const setValues = (values: string[]) => onChange({ ...clause, values });

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-start gap-2">
        <Column label={showLabels ? "FIELD" : undefined} className="w-[168px]">
          <Dropdown<ClauseField>
            ddKey={`qb-field-${index}`}
            className={PANEL_Z}
            heading="FIELD"
            width={210}
            value={clause.field}
            items={fields.map((field) => ({ value: field, label: FIELD_LABELS[field] }))}
            onSelect={(field) => onChange(withField(clause, field, destination))}
            trigger={({ ref, toggle }) => (
              <button type="button" ref={ref} onClick={toggle} className={TRIGGER}>
                <span className="truncate">{FIELD_LABELS[clause.field]}</span>
                <Icon name="chevronDown" size={14} strokeWidth={2.2} />
              </button>
            )}
          />
        </Column>

        <Column label={showLabels ? "IS" : undefined} className="w-[150px]">
          <Dropdown<ClauseOperator>
            ddKey={`qb-op-${index}`}
            className={PANEL_Z}
            heading="OPERATOR"
            width={190}
            value={clause.operator}
            items={operators.map((op) => ({ value: op, label: OPERATOR_LABELS[op] }))}
            onSelect={(operator) => onChange(withOperator(clause, operator))}
            trigger={({ ref, toggle }) => (
              <button type="button" ref={ref} onClick={toggle} className={TRIGGER}>
                <span className="truncate">{OPERATOR_LABELS[clause.operator]}</span>
                <Icon name="chevronDown" size={14} strokeWidth={2.2} />
              </button>
            )}
          />
        </Column>

        <Column label={showLabels ? "VALUE" : undefined} className="min-w-[220px] flex-1">
          {list ? (
            <MultiValue
              index={index}
              values={clause.values.filter(Boolean)}
              options={options}
              onChange={setValues}
            />
          ) : options.length > 0 ? (
            <Dropdown<string>
              ddKey={`qb-value-${index}`}
              className={PANEL_Z}
              heading="VALUE"
              width={280}
              value={clause.values[0] ?? ""}
              items={options.map((option) => ({
                value: option.value,
                label: `${indent(option.depth ?? 0)}${option.label}`,
              }))}
              onSelect={(value) => setValues([value])}
              trigger={({ ref, toggle }) => (
                <button type="button" ref={ref} onClick={toggle} className={TRIGGER}>
                  <span className={cn("truncate", !clause.values[0] && "text-faint")}>
                    {clause.values[0] || "Pick a value"}
                  </span>
                  <Icon name="chevronDown" size={14} strokeWidth={2.2} />
                </button>
              )}
            />
          ) : (
            <Input
              value={clause.values[0] ?? ""}
              onChange={(e) => setValues([e.target.value])}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSubmit();
                }
              }}
              placeholder={help ? "Type a value" : "Value"}
              className="h-10"
              aria-label={`${FIELD_LABELS[clause.field]} value`}
            />
          )}
        </Column>

        <div className={cn("flex", showLabels && "pt-[19px]")}>
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove the ${FIELD_LABELS[clause.field]} condition`}
            className={cn(
              "flex size-10 cursor-pointer items-center justify-center rounded-control-lg",
              "border border-bd2 bg-card3 text-txt4 transition-colors hover:text-danger",
            )}
          >
            <Icon name="close" size={14} strokeWidth={2.4} />
          </button>
        </div>
      </div>

      {/* The hint only earns its place where there is nothing to pick from —
          nobody knows `@Today - 7` is accepted unless it is said. */}
      {help && options.length === 0 && (
        <p className="m-0 pl-[2px] text-[11.5px] text-faint">{help}</p>
      )}

      {problems.map((problem) => (
        <p key={problem.message} className="m-0 pl-[2px] text-[11.5px] text-warn">
          {problem.message}
        </p>
      ))}
    </div>
  );
}

function Column({
  label,
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-[5px]", className)}>
      {label && (
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          {label}
        </span>
      )}
      {children}
    </div>
  );
}

/**
 * The value control for `in` / `notIn`: chosen values as removable chips, plus a
 * picker (or an input) to add another.
 *
 * `Dropdown` is single-select and there is no multi-select primitive in the app,
 * so this composes one rather than widening `Dropdown` — a select that sometimes
 * closes and sometimes does not is a worse primitive than two clear ones.
 */
function MultiValue({
  index,
  values,
  options,
  onChange,
}: {
  index: number;
  values: string[];
  options: ValueOption[];
  onChange: (values: string[]) => void;
}) {
  const remaining = options.filter((option) => !values.includes(option.value));
  const add = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !values.includes(trimmed)) onChange([...values, trimmed]);
  };

  return (
    <div className="flex flex-col gap-2">
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onChange(values.filter((v) => v !== value))}
              aria-label={`Remove ${value}`}
              className="cursor-pointer border-none bg-transparent p-0"
            >
              <Pill tone="accent" size="sm">
                {value} ×
              </Pill>
            </button>
          ))}
        </div>
      )}

      {options.length > 0 ? (
        <Dropdown<string>
          ddKey={`qb-value-${index}`}
          className={PANEL_Z}
          heading="ADD A VALUE"
          width={280}
          items={remaining.map((option) => ({
            value: option.value,
            label: `${indent(option.depth ?? 0)}${option.label}`,
          }))}
          onSelect={add}
          trigger={({ ref, toggle }) => (
            <button
              type="button"
              ref={ref}
              onClick={toggle}
              disabled={remaining.length === 0}
              className={cn(TRIGGER, "disabled:cursor-not-allowed disabled:opacity-50")}
            >
              <span className="truncate text-faint">
                {remaining.length === 0 ? "All values added" : "Add a value…"}
              </span>
              <Icon name="chevronDown" size={14} strokeWidth={2.2} />
            </button>
          )}
        />
      ) : (
        <Input
          placeholder="Value, then Enter"
          className="h-10"
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            add((e.target as HTMLInputElement).value);
            (e.target as HTMLInputElement).value = "";
          }}
          aria-label="Add a value"
        />
      )}
    </div>
  );
}
