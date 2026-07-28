// Handoff § 9. Integrations — one provider block: 34px glyph, name 15.5px/800,
// `2 connections · 4 projects`, and a `+ Add connection` accent-tint button,
// followed by that provider's connection rows.

import { Glyph, Icon } from "@/components/ui";
import type { Provider, ProviderConnection, ProviderConnectionGroup } from "@/data";
import { cn } from "@/lib/cn";
import { ConnectionRow } from "./ConnectionRow";

export interface ProviderGroupProps {
  group: ProviderConnectionGroup;
  provider: Provider;
  /** Display name — from the integrations summary, e.g. "Azure DevOps". */
  name: string;
  expandedId: string | null;
  testingId: string | null;
  onToggle: (connectionId: string) => void;
  onFieldChange: (connectionId: string, fieldKey: string, value: string) => void;
  onTest: (connection: ProviderConnection) => void;
  onSave: (connection: ProviderConnection) => void;
  onRemove: (connection: ProviderConnection) => void;
  onAdd: () => void;
}

export function ProviderGroup({
  group,
  provider,
  name,
  expandedId,
  testingId,
  onToggle,
  onFieldChange,
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
            {connectionsLabel} · {group.projectsLabel}
          </div>
        </div>

        <button
          type="button"
          onClick={onAdd}
          className={cn(
            "inline-flex shrink-0 cursor-pointer items-center gap-[7px] rounded-control-lg",
            "border border-pb bg-pt px-[14px] py-[9px] text-[12.5px] font-bold text-ps-text",
            "transition-colors duration-200 hover:bg-pb/40",
          )}
        >
          <Icon name="plus" size={14} strokeWidth={2.5} />
          Add connection
        </button>
      </div>

      {group.connections.map((c) => (
        <ConnectionRow
          key={c.id}
          connection={c}
          expanded={expandedId === c.id}
          testing={testingId === c.id}
          onToggle={() => onToggle(c.id)}
          onFieldChange={(fieldKey, value) => onFieldChange(c.id, fieldKey, value)}
          onTest={() => onTest(c)}
          onSave={() => onSave(c)}
          onRemove={() => onRemove(c)}
        />
      ))}
    </section>
  );
}
