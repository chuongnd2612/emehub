// Handoff › 3. Projects › Project knowledge ("a chevron that rotates 90° when
// open") and Motion — transitions ("transform .22s on accordion/connection
// chevrons").

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Icon } from "./Icon";

export interface AccordionItemProps {
  /** Stable key, used by the controlled `openKeys` API. */
  itemKey: string;
  title: ReactNode;
  /** Right-aligned content in the header row (pills, counts, actions). */
  meta?: ReactNode;
  open: boolean;
  onToggle: (itemKey: string) => void;
  children?: ReactNode;
  className?: string;
}

export function AccordionItem({
  itemKey,
  title,
  meta,
  open,
  onToggle,
  children,
  className,
}: AccordionItemProps) {
  return (
    <div
      data-surface
      className={cn(
        "overflow-hidden rounded-control-lg border border-bd bg-card2",
        className,
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => onToggle(itemKey)}
        className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors duration-200 hover:bg-card3"
      >
        <span
          className={cn(
            "flex shrink-0 text-faint transition-transform duration-[.22s]",
            open && "rotate-90",
          )}
        >
          <Icon name="chevronRight" size={14} strokeWidth={2.4} />
        </span>
        <span className="min-w-0 flex-1 truncate text-[13.5px] font-bold text-txt2">
          {title}
        </span>
        {meta}
      </button>
      {open && children && (
        <div className="border-t border-bd3 px-4 py-3.5 text-[12.5px] leading-[1.6] text-txt3">
          {children}
        </div>
      )}
    </div>
  );
}

export interface AccordionProps {
  /** Controlled set of open keys. Omit to let the Accordion manage its own. */
  openKeys?: string[];
  onOpenChange?: (openKeys: string[]) => void;
  /** Keys open on first render when uncontrolled. */
  defaultOpenKeys?: string[];
  items: {
    key: string;
    title: ReactNode;
    meta?: ReactNode;
    content: ReactNode;
  }[];
  className?: string;
}

export function Accordion({
  openKeys,
  onOpenChange,
  defaultOpenKeys = [],
  items,
  className,
}: AccordionProps) {
  const [internal, setInternal] = useState<string[]>(defaultOpenKeys);
  const keys = openKeys ?? internal;

  const toggle = (key: string) => {
    const next = keys.includes(key)
      ? keys.filter((k) => k !== key)
      : [...keys, key];
    if (openKeys === undefined) setInternal(next);
    onOpenChange?.(next);
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {items.map((i) => (
        <AccordionItem
          key={i.key}
          itemKey={i.key}
          title={i.title}
          meta={i.meta}
          open={keys.includes(i.key)}
          onToggle={toggle}
        >
          {i.content}
        </AccordionItem>
      ))}
    </div>
  );
}
