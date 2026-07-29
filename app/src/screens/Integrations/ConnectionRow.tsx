// Handoff § 9. Integrations — one provider connection.
//
// Collapsed: chevron (rotates 90° when open, `transform .22s`), label + mono
// summary, status pill, `tested <when>`, trash button (hover → rose).
// Expanded: a 2-column field grid (text/password inputs, focus border --pb) +
// `Test connection` + `Save connection` + "Credentials encrypted at rest".
//
// ## The credential field
//
// `GET /connections` returns `hasPat`, never the PAT, so the secret input is
// ALWAYS empty on load — there is nothing to prefill and no Reveal to offer.
// Its placeholder says whether one is stored. Leaving it blank on save keeps
// the stored credential (the hub treats an omitted `pat` as "keep"); typing
// replaces it.

import { Icon, Input, Spinner, StatusPill } from "@/components/ui";
import type { Connection } from "@/data";
import { cn } from "@/lib/cn";

export interface ConnectionRowProps {
  connection: Connection;
  expanded: boolean;
  testing: boolean;
  saving: boolean;
  onToggle: () => void;
  onFieldChange: (fieldKey: string, value: string) => void;
  onLabelChange: (value: string) => void;
  onTest: () => void;
  onSave: () => void;
  onRemove: () => void;
}

export function ConnectionRow({
  connection,
  expanded,
  testing,
  saving,
  onToggle,
  onFieldChange,
  onLabelChange,
  onTest,
  onSave,
  onRemove,
}: ConnectionRowProps) {
  return (
    <div className="glass overflow-hidden rounded-card">
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
        className={cn(
          "flex cursor-pointer items-center gap-[13px] px-[18px] py-[15px]",
          "transition-colors duration-200 outline-none hover:bg-card3 focus-visible:bg-card3",
        )}
      >
        <Icon
          name="chevronRight"
          size={15}
          strokeWidth={2.4}
          className={cn(
            "shrink-0 text-muted transition-transform duration-[.22s]",
            expanded && "rotate-90",
          )}
        />

        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-bold text-txt2">
            {connection.label}
          </div>
          <div className="mt-[3px] truncate font-mono text-[11px] text-faint">
            {connection.summary}
          </div>
        </div>

        {connection.shared && (
          <span className="shrink-0 rounded-pill bg-pt px-2 py-[3px] text-[9px] font-bold tracking-[.09em] text-ps-text">
            SHARED
          </span>
        )}

        <StatusPill status={connection.status} size="sm" />

        <span className="shrink-0 text-[10.5px] whitespace-nowrap text-label">
          tested {connection.lastTested}
        </span>

        <button
          type="button"
          aria-label={`Remove ${connection.label}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className={cn(
            "flex size-[30px] shrink-0 cursor-pointer items-center justify-center rounded-control",
            "border border-bd2 bg-card2 text-muted transition-colors duration-200",
            "hover:bg-danger-tint hover:text-danger",
          )}
        >
          <Icon name="trash" size={14} />
        </button>
      </div>

      {expanded && (
        <div className="border-t border-bd3 px-[18px] pt-1 pb-[18px]">
          <div className="my-4 grid grid-cols-2 gap-[14px]">
            <div>
              <div className="mb-[7px] text-[11.5px] font-semibold text-muted">
                Label
              </div>
              <Input
                type="text"
                value={connection.label}
                onChange={(e) => onLabelChange(e.target.value)}
                autoComplete="off"
                aria-label="Label"
                className="h-10"
              />
            </div>

            {connection.fields.map((f) => (
              <div key={f.key}>
                <div className="mb-[7px] text-[11.5px] font-semibold text-muted">
                  {f.label}
                </div>
                {/* Secret fields stay type="password" and start empty — the hub
                    never returns the stored value. */}
                <Input
                  type={f.type}
                  value={f.value}
                  placeholder={f.placeholder}
                  onChange={(e) => onFieldChange(f.key, e.target.value)}
                  autoComplete="off"
                  aria-label={f.label}
                  className="h-10"
                />
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-[10px]">
            <button
              type="button"
              onClick={onTest}
              disabled={testing}
              className={cn(
                "inline-flex cursor-pointer items-center gap-2 rounded-control-lg px-4 py-[10px]",
                "border border-pb bg-pt text-[12.5px] font-bold text-ps-text",
                "transition-colors duration-200 hover:bg-pb/40 disabled:cursor-not-allowed",
              )}
            >
              {testing ? (
                <Spinner size={14} speed="run" />
              ) : (
                <Icon name="check" size={14} strokeWidth={2.2} />
              )}
              {testing ? "Testing…" : "Test connection"}
            </button>

            <button
              type="button"
              onClick={onSave}
              disabled={saving}
              className={cn(
                "inline-flex cursor-pointer items-center gap-2 rounded-control-lg border border-bd2",
                "bg-card3 px-4 py-[10px] text-[12.5px] font-semibold text-txt2",
                "transition-colors duration-200 hover:bg-bd2 disabled:cursor-not-allowed",
              )}
            >
              {saving && <Spinner size={14} speed="run" />}
              {saving ? "Saving…" : "Save connection"}
            </button>

            <span className="ml-auto text-[11.5px] text-faint">
              Credentials encrypted at rest
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
