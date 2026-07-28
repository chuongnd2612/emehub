// Handoff § 5. Import dialog — opened from Tickets today and from the Overview
// quick action later, which is why it lives in `components/import/` rather than
// inside the Tickets screen.
//
//   580px wide, var(--pop), radius 22, shadow-dialog, scaleIn .22s; scrim
//   rgba(6,6,10,.62) + blur(7px) + fadeIn .2s          → <Modal size="dialog">
//   Basic  → WHAT TO PULL + three radio rows
//   Advanced → FILTER BY FIELD, a 2-column grid of the SAME provider schema the
//   Tickets toolbar renders, each showing `Any` until set; Jira adds a mono JQL
//   field, GitHub a mono search-query field.
//
// Running an import closes the dialog and hands the request to `onImport` —
// the caller owns the 1500 ms spinner (see `useImportRun`).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getTicketFilterSchema,
  PROVIDERS,
  type ImportRequest,
  type ImportScope,
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
  Modal,
  RadioGroup,
  Segmented,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { IMPORT_SCOPE_OPTIONS } from "./scopes";

export type ImportMode = "basic" | "advanced";

export interface ImportDialogProps {
  /** Controlled visibility. The dialog renders nothing when false. */
  open: boolean;
  /** Which provider to pull from. Exactly one is active at a time. */
  provider: ProviderKey;
  /** Scrim click, ✕, Esc and Cancel. */
  onClose: () => void;
  /**
   * "Import now". The dialog closes itself first, then calls this with the
   * composed request; the caller runs it (see `useImportRun`) so the spinner
   * can live on whichever button opened the dialog.
   */
  onImport: (request: ImportRequest) => void;
  /** Mode the dialog opens in. Defaults to `basic`. */
  defaultMode?: ImportMode;
  /** Scope the dialog opens on. Defaults to `sprint`. */
  defaultScope?: ImportScope;
}

const MODE_OPTIONS = [
  { value: "basic" as const, label: "Basic" },
  { value: "advanced" as const, label: "Advanced" },
];

/** Small tracked uppercase section label — `WHAT TO PULL` / `FILTER BY FIELD`. */
function SectionLabel({ children }: { children: string }) {
  return (
    <div className="text-[10.5px] font-bold tracking-[.11em] text-label">
      {children}
    </div>
  );
}

/** One full-width field dropdown in the Advanced grid. Shows `Any` until set. */
function FieldSelect({
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
    <div className="flex flex-col gap-[7px]">
      <span className="text-[11.5px] font-semibold text-muted">
        {field.label}
      </span>
      <Dropdown
        ddKey={`import-field-${String(field.key)}`}
        width={264}
        value={value ?? null}
        onSelect={onPick}
        items={field.options.map((o) => ({ value: o, label: o }))}
        // The dialog sits at z-1100; the panel has to clear it.
        className="z-[1200]"
        trigger={({ ref, toggle }) => (
          <button
            ref={ref}
            type="button"
            data-surface
            onClick={toggle}
            className={cn(
              "flex w-full cursor-pointer items-center justify-between gap-1.5 rounded-control-lg",
              "border px-3.5 py-[10px] text-[12.5px] font-semibold",
              set
                ? "border-pb bg-pt text-p-on"
                : "border-bd2 bg-inset text-txt4 hover:bg-card3",
            )}
          >
            <span className="min-w-0 truncate">{value ?? "Any"}</span>
            <Icon name="chevronDown" size={12} strokeWidth={2.2} />
          </button>
        )}
      />
    </div>
  );
}

export function ImportDialog({
  open,
  provider,
  onClose,
  onImport,
  defaultMode = "basic",
  defaultScope = "sprint",
}: ImportDialogProps) {
  const [schema, setSchema] = useState<TicketFilterField[]>([]);
  const [mode, setMode] = useState<ImportMode>(defaultMode);
  const [scope, setScope] = useState<ImportScope>(defaultScope);
  const [filters, setFilters] = useState<TicketFilters>({});
  /** Serves the Jira JQL field and the GitHub search-query field. */
  const [expression, setExpression] = useState("");

  const meta = PROVIDERS[provider];

  useEffect(() => {
    let live = true;
    getTicketFilterSchema().then((s) => {
      if (live) setSchema(s[provider]);
    });
    return () => {
      live = false;
    };
  }, [provider]);

  // A provider switch changes the whole filter set, so nothing carries over.
  useEffect(() => {
    setFilters({});
    setExpression("");
  }, [provider]);

  // Every visit starts from the caller's defaults.
  useEffect(() => {
    if (!open) return;
    setMode(defaultMode);
    setScope(defaultScope);
  }, [open, defaultMode, defaultScope]);

  const pick = useCallback((key: string, value: string) => {
    // Picking the same value again clears the field.
    setFilters((f) => ({ ...f, [key]: f[key] === value ? undefined : value }));
  }, []);

  const scopeOptions = useMemo(
    () =>
      IMPORT_SCOPE_OPTIONS.map((o) => ({
        value: o.key,
        label: (
          <span className="flex flex-col gap-[2px]">
            <span className="text-[13.5px] font-bold text-txt">{o.label}</span>
            <span className="text-[12px] font-medium text-muted">
              {o.description.replace("{provider}", meta.name)}
            </span>
          </span>
        ),
        hint: <span className="font-mono text-[11.5px]">{o.count}</span>,
      })),
    [meta.name],
  );

  const submit = () => {
    const request: ImportRequest = {
      provider,
      mode,
      scope,
      filters: mode === "advanced" ? filters : {},
      ...(mode === "advanced" && provider === "jira"
        ? { jql: expression || undefined }
        : null),
      ...(mode === "advanced" && provider === "gh"
        ? { searchQuery: expression || undefined }
        : null),
    };
    onClose();
    onImport(request);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="dialog"
      title="Import tickets"
      subtitle={`Pull work items from ${meta.name}`}
      glyph={<Glyph size={34} fill={meta.color} label={meta.glyph} />}
      footer={
        <>
          <span className="flex-1 text-[11.5px] text-faint">
            Read-only pull · credentials stay encrypted
          </span>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            icon={<Icon name="download" size={14} strokeWidth={2.3} />}
          >
            Import now
          </Button>
        </>
      }
    >
      {/* Mode switch — segmented Basic | Advanced in a 4px inset track. */}
      <Segmented
        options={MODE_OPTIONS}
        value={mode}
        onChange={setMode}
        className="w-full [&>button]:flex-1"
      />

      {mode === "basic" ? (
        <div className="flex flex-col gap-3">
          <SectionLabel>WHAT TO PULL</SectionLabel>
          <RadioGroup
            name="import-scope"
            value={scope}
            onChange={setScope}
            options={scopeOptions}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <SectionLabel>FILTER BY FIELD</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            {schema.map((field) => (
              <FieldSelect
                key={String(field.key)}
                field={field}
                value={filters[String(field.key)]}
                onPick={(value) => pick(String(field.key), value)}
              />
            ))}
          </div>

          {provider === "jira" && (
            <div className="mt-1 flex flex-col gap-[7px]">
              <span className="text-[11.5px] font-semibold text-muted">
                JQL (optional)
              </span>
              <Input
                mono
                value={expression}
                onChange={(e) => setExpression(e.target.value)}
                placeholder="project = LED AND status != Done"
                className="h-auto py-[10px]"
              />
            </div>
          )}

          {provider === "gh" && (
            <div className="mt-1 flex flex-col gap-[7px]">
              <span className="text-[11.5px] font-semibold text-muted">
                Search query (optional)
              </span>
              <Input
                mono
                value={expression}
                onChange={(e) => setExpression(e.target.value)}
                placeholder="is:issue is:open label:qa"
                className="h-auto py-[10px]"
              />
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
