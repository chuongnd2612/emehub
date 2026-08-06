// Handoff § 9. Integrations — one provider block: 34px glyph, name 15.5px/800,
// `2 connections · work items · repositories`, and a `+ Add connection`
// accent-tint button, followed by that provider's connection rows.
//
// The handoff's second sub-line figure was "4 projects". A connection carries
// no project count on the wire (`GET /connections/{id}/projects` is a live
// provider call, far too expensive for a list header), so the block reports
// what the connections actually advertise instead: their capabilities.

import { Glyph, Icon, Spinner } from "@/components/ui";
import type { Connection, ConnectionGroup, Provider } from "@/data";
import { cn } from "@/lib/cn";
import { ConnectionRow } from "./ConnectionRow";
import type { ConnectionTestOutcome } from "./ConnectionRow";

export interface ProviderGroupProps {
  group: ConnectionGroup;
  provider: Provider;
  /** Display name, e.g. "Azure DevOps". */
  name: string;
  expandedId: string | null;
  testingId: number | null;
  savingId: number | null;
  /** Last test outcome per connection id — see ConnectionRow's `result`. */
  results: Record<number, ConnectionTestOutcome>;
  adding: boolean;
  onToggle: (connectionId: number) => void;
  onFieldChange: (connectionId: number, fieldKey: string, value: string) => void;
  onLabelChange: (connectionId: number, value: string) => void;
  onTest: (connection: Connection) => void;
  onSave: (connection: Connection) => void;
  onRemove: (connection: Connection) => void;
  onAdd: () => void;
}

export function ProviderGroup({
  group,
  provider,
  name,
  expandedId,
  testingId,
  savingId,
  results,
  adding,
  onToggle,
  onFieldChange,
  onLabelChange,
  onTest,
  onSave,
  onRemove,
  onAdd,
}: ProviderGroupProps) {
  const count = group.connections.length;
  const connectionsLabel = `${count} ${count === 1 ? "connection" : "connections"}`;

  return (
    <section className="flex flex-col gap-[10px]">
      <div className="flex items-center gap-[13px]">
        <Glyph size={34} fill={provider.color} label={provider.glyph} />

        <div className="min-w-0 flex-1">
          <div className="text-[15.5px] font-extrabold tracking-[-.02em] text-txt">
            {name}
          </div>
          <div className="mt-[2px] text-[11.5px] text-muted">
            {count === 0
              ? "No connections yet"
              : `${connectionsLabel} · ${group.capabilitiesLabel}`}
          </div>
        </div>

        <button
          type="button"
          onClick={onAdd}
          disabled={adding}
          className={cn(
            "inline-flex shrink-0 cursor-pointer items-center gap-[7px] rounded-control-lg",
            "border border-pb bg-pt px-[14px] py-[9px] text-[12.5px] font-bold text-ps-text",
            "transition-colors duration-200 hover:bg-pb/40 disabled:cursor-not-allowed",
          )}
        >
          {adding ? (
            <Spinner size={14} speed="run" />
          ) : (
            <Icon name="plus" size={14} strokeWidth={2.5} />
          )}
          Add connection
        </button>
      </div>

      {group.connections.map((c) => (
        <ConnectionRow
          key={c.id}
          connection={c}
          expanded={expandedId === String(c.id)}
          testing={testingId === c.id}
          saving={savingId === c.id}
          result={results[c.id] ?? null}
          onToggle={() => onToggle(c.id)}
          onFieldChange={(fieldKey, value) => onFieldChange(c.id, fieldKey, value)}
          onLabelChange={(value) => onLabelChange(c.id, value)}
          onTest={() => onTest(c)}
          onSave={() => onSave(c)}
          onRemove={() => onRemove(c)}
        />
      ))}
    </section>
  );
}
