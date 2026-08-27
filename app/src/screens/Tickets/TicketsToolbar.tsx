// Handoff § 4. Tickets › Toolbar — a single wrapping row, gap 9:
//   source · divider · search · one filter pill per schema field ·
//   × Clear · "last import 4 minutes ago" + the primary Import button.
//
// ## The source picker is not a picker any more (#221, ADR 0011 §3)
//
// The handoff's first control was a `TICKET SOURCE` dropdown, and this screen's
// governing rule used to be "exactly one provider is active at a time and the
// filter set changes with it", selected by `?source=`. Under containment the
// provider is **derived from the project** — `project_config` already binds the
// connection — so the dropdown is DELETED, not hidden: a switch on a ticket list
// means the same screen can show work items from a provider that has nothing to
// do with the project the user believes they are in, which is the argument that
// decided Q-Agent's ADR 0015 against a mere filter.
//
// What survives is the *statement*: a static chip naming the source this list is
// reading, because "which provider am I looking at" is still a question the user
// needs answered — it just is not one they get to answer here. It is a `span`,
// carries no handler and opens nothing; the place to change the binding is the
// project's Settings tab.
//
// The filter set still changes with the provider. It just follows the project's
// source instead of a URL parameter.
//
// "last import 4 minutes ago" was a hard-coded string in the prototype. It is
// now the newest `syncedAt` across the rows in scope — the only import time the
// hub actually knows — and reads "never imported" when there are none.

import {
  PROVIDERS,
  type ProviderKey,
  type TicketFilterField,
  type TicketFilters,
} from "@/data";
import {
  Button,
  Dropdown,
  Glyph,
  Icon,
  Input,
  Spinner,
} from "@/components/ui";
import { cn } from "@/lib/cn";

export interface TicketsToolbarProps {
  /**
   * The list's ticket source, derived from the project (#221) — displayed, never
   * chosen. `null` where there is no single source to name, which is the
   * Unassigned bucket: those rows belong to no project and may have arrived
   * through more than one connection.
   */
  source: { provider: ProviderKey; label: string } | null;
  query: string;
  onQueryChange: (query: string) => void;
  schema: TicketFilterField[];
  filters: TicketFilters;
  /** Picking the same value again clears the field. */
  onFilterPick: (key: string, value: string) => void;
  onClear: () => void;
  /** True while `POST /tickets/sync` is in flight. */
  importing: boolean;
  /**
   * Already-humanised `Ticket.synced` of the newest row in scope (the data layer
   * owns the wire-to-display translation), or null when there are none.
   */
  lastImport: string | null;
  /**
   * Omitted where importing does not apply — the Unassigned bucket, which is
   * read-only by decision (ADR 0011 §4). A disabled button would suggest the
   * action exists on this screen somewhere; it does not.
   */
  onImport?: () => void;
  /** True while the clause builder panel is open. Omit both to hide the control. */
  builderOpen?: boolean;
  onToggleBuilder?: () => void;
  /** A clause query is in force, so the pills are not what is filtering. */
  queryActive: boolean;
}

/** One provider-variant filter pill: 36px, radius 11, 12.5px/600 + chevron. */
function FilterPill({
  field,
  value,
  onPick,
}: {
  field: TicketFilterField;
  value: string | undefined;
  onPick: (value: string) => void;
}) {
  const set = Boolean(value);
  return (
    <Dropdown
      ddKey={`ticket-filter-${String(field.key)}`}
      width={200}
      value={value ?? null}
      onSelect={onPick}
      items={field.options.map((o) => ({ value: o, label: o }))}
      trigger={({ ref, toggle }) => (
        <button
          ref={ref}
          type="button"
          data-surface
          data-testid={`ticket-filter-${String(field.key)}`}
          onClick={toggle}
          className={cn(
            "flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-control-lg border px-3",
            "text-[12.5px] font-semibold",
            set
              ? "border-pb bg-pt text-p-on"
              : "border-bd2 bg-card2 text-txt4 hover:bg-card3",
          )}
        >
          {value ?? field.label}
          <Icon name="chevronDown" size={12} strokeWidth={2.2} />
        </button>
      )}
    />
  );
}

export function TicketsToolbar({
  source,
  query,
  onQueryChange,
  schema,
  filters,
  onFilterPick,
  onClear,
  importing,
  lastImport,
  onImport,
  builderOpen,
  onToggleBuilder,
  queryActive,
}: TicketsToolbarProps) {
  const dirty =
    Boolean(query) || schema.some((f) => Boolean(filters[String(f.key)]));

  return (
    <div className="flex flex-wrap items-center gap-[9px]">
      {/* 1. The source — a statement, not a control. */}
      {source && (
        <>
          <span
            data-testid="ticket-source"
            title={`Work items are read from ${source.label}. The binding lives on the project's Settings tab.`}
            className={cn(
              "flex h-9 shrink-0 items-center gap-[9px] rounded-control-lg",
              "border border-bd2 bg-card2 px-3 transition-colors duration-200",
            )}
          >
            <Glyph
              size={22}
              fill={PROVIDERS[source.provider].color}
              label={PROVIDERS[source.provider].glyph}
            />
            <span className="text-[12.5px] font-bold whitespace-nowrap text-txt2">
              {PROVIDERS[source.provider].name}
            </span>
          </span>

          {/* 2. Divider, then the search field. */}
          <span className="h-6 w-px shrink-0 bg-bd2" />
        </>
      )}

      <Input
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Search tickets…"
        icon={<Icon name="search" size={14} strokeWidth={2.2} />}
        className="max-w-[250px] min-w-[170px] flex-1"
      />

      {/* 3. One pill per provider-variant schema field.
              Hidden while a clause query is in force: the two answer the same
              question, and showing pills that are not what is filtering is how a
              control starts lying. */}
      {!queryActive &&
        schema.map((field) => (
          <FilterPill
            key={String(field.key)}
            field={field}
            value={filters[String(field.key)]}
            onPick={(value) => onFilterPick(String(field.key), value)}
          />
        ))}

      {/* 3b. The clause builder. Its options come from the provider's own
              metadata, so it can filter on a value that has never been imported —
              which the pills, built from mirrored rows, cannot. */}
      {onToggleBuilder && (
        <button
          type="button"
          data-surface
          onClick={onToggleBuilder}
          aria-expanded={builderOpen}
          className={cn(
            "flex h-9 shrink-0 cursor-pointer items-center gap-[6px] rounded-control-lg border px-[11px]",
            "text-[12px] font-semibold transition-colors duration-200",
            builderOpen || queryActive
              ? "border-pb bg-pt text-p-on"
              : "border-bd2 bg-card2 text-txt4 hover:bg-card3",
          )}
        >
          <Icon name="filter" size={13} strokeWidth={2.3} />
          {queryActive ? "Query" : "Build a query"}
          <Icon
            name={builderOpen ? "chevronUp" : "chevronDown"}
            size={13}
            strokeWidth={2.3}
          />
        </button>
      )}

      {/* 4. × Clear — only once a filter or the query is set. */}
      {dirty && (
        <button
          type="button"
          data-surface
          onClick={onClear}
          className={cn(
            "flex shrink-0 cursor-pointer items-center gap-[5px] rounded-control-lg px-[11px] py-2",
            "text-[12px] font-semibold text-muted hover:text-danger",
          )}
        >
          <Icon name="close" size={13} strokeWidth={2.2} />
          Clear
        </button>
      )}

      {/* 5. Import status + the primary Import button. */}
      <div className="ml-auto flex shrink-0 items-center gap-[11px]">
        <span className="text-[11px] whitespace-nowrap text-label">
          {importing
            ? "pulling now…"
            : lastImport
              ? `last import ${lastImport}`
              : "never imported"}
        </span>
        {onImport && (
          <Button
            variant="primary"
            onClick={onImport}
            icon={
              importing ? (
                <Spinner size={14} speed="run" />
              ) : (
                <Icon name="download" size={14} strokeWidth={2.3} />
              )
            }
          >
            {importing ? "Importing…" : "Import"}
          </Button>
        )}
      </div>
    </div>
  );
}
