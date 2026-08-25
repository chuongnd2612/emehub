// The tab strip for User Management — Handoff § 8 ("Tabs Members · Roles ·
// Invitations, right-aligned `Invite member` primary") and the prototype's
// `tabStyle`: active = var(--pt) + var(--pb) + var(--pOn), inactive =
// transparent on transparent, `background/color .18s`.
//
// Only Members survives (#191) — the other two rendered fabricated data. The
// strip stays because it is what carries the right-aligned action slot.

import { cn } from "@/lib/cn";

export interface Tab<T extends string> {
  value: T;
  label: string;
}

export interface TabStripProps<T extends string> {
  tabs: readonly Tab<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Right-aligned action — the `Invite member` primary. */
  action?: React.ReactNode;
}

export function TabStrip<T extends string>({
  tabs,
  value,
  onChange,
  action,
}: TabStripProps<T>) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="tablist">
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={cn(
              "cursor-pointer rounded-control-lg border px-4 py-[9px] text-[12.5px] font-bold",
              "transition-[background-color,border-color,color] duration-200",
              active
                ? "border-pb bg-pt text-p-on"
                : "border-transparent bg-transparent text-muted hover:text-txt3",
            )}
          >
            {t.label}
          </button>
        );
      })}
      {action && <span className="ml-auto flex items-center">{action}</span>}
    </div>
  );
}
