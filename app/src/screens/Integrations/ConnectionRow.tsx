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
import { AzureDevOpsSetup } from "./AzureDevOpsSetup";

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
  /**
   * The outcome of the last test **in this session**, or null if it has not been
   * tested here yet.
   *
   * Persisted on the row rather than only toasted: a toast is gone in 3.2s, and
   * the useful half of a failure is the provider's own reason. `lastTested`
   * alone tells you *when* it was tried, never *what it said*.
   */
  result: ConnectionTestOutcome | null;
  /** Organisation URLs already configured elsewhere — see AzureDevOpsSetup. */
  knownOrgUrls?: string[];
}

/** Kept alongside the row so a failure's reason stays on screen. */
export interface ConnectionTestOutcome {
  ok: boolean;
  message: string;
  /**
   * The hub could not be reached at all, as opposed to the provider rejecting
   * us. Different problems with different fixes, so they must not read the same
   * (INTEGRATION.md §5 draws the same line for the hub as a whole).
   */
  unreachable: boolean;
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
  result,
  knownOrgUrls,
}: ConnectionRowProps) {
  // A connection with no stored credential cannot be tested — the request is
  // guaranteed to fail, so say why instead of firing it.
  const untestable = !connection.hasPat;
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
        <div className="border-t border-bd3 px-[18px] pt-1 pb-[16px]">
          {/* Three columns, not two, and the component's own 36px field height
              rather than a local 40px override. The form is six short values;
              at 2-up and 40px it filled a screen and read as heavier than the
              decisions it holds. */}
          <div className="mt-3 mb-[10px] grid grid-cols-3 gap-x-[14px] gap-y-[10px]">
            <div>
              <div className="mb-[5px] text-[11px] font-semibold text-muted">
                Label
              </div>
              <Input
                type="text"
                value={connection.label}
                onChange={(e) => onLabelChange(e.target.value)}
                autoComplete="off"
                aria-label="Label"
              />
            </div>

            {/* Azure DevOps is configured credential-first and discovers the
                rest of its own settings, so it owns its fields (#166). It renders
                *inside* this grid — the component wraps them in `display:
                contents` so they take their own columns rather than starting a
                second grid underneath, which is what stacked them full-width.
                The other providers keep the plain grid: GitHub and Jira have
                equivalent account APIs, but each with its own auth quirks, and a
                shared abstraction guessed at from one example would be worse than
                two honest implementations. */}
            {connection.kind === "azure_devops" && (
              <AzureDevOpsSetup
                connection={connection}
                onFieldChange={onFieldChange}
                knownOrgUrls={knownOrgUrls}
              />
            )}
            {connection.kind !== "azure_devops" &&
              connection.fields.map((f) => (
                <div key={f.key}>
                  <div className="mb-[5px] text-[11px] font-semibold text-muted">
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
                  />
                </div>
              ))}
          </div>

          <div className="mt-[14px] flex flex-wrap items-center gap-[8px]">
            <button
              type="button"
              onClick={onTest}
              disabled={testing || untestable}
              title={
                untestable
                  ? "Add an access token first — there is no stored credential to test"
                  : undefined
              }
              className={cn(
                "inline-flex cursor-pointer items-center gap-2 rounded-control-lg px-4 py-[10px]",
                "border border-pb bg-pt text-[12.5px] font-bold text-ps-text",
                "transition-colors duration-200 hover:bg-pb/40 disabled:cursor-not-allowed",
                "disabled:opacity-50",
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

          {/* One container owns the spacing below the button row. Both notices
              were previously margin-less, so each sat flush against the buttons
              and against the other — the block read as one run-on surface rather
              than as separate statements. */}
          <div className="mt-[14px] flex flex-col gap-[10px] empty:mt-0">
          {/* Why there is no stored credential to test, stated rather than left
              to a disabled button with no explanation. */}
          {untestable && connection.kind !== "azure_devops" && (
            <p className="m-0 text-[12px] leading-[1.5] text-faint">
              No access token is stored for this connection yet. Add one above and
              save, then test it.
            </p>
          )}

          {/* The last outcome, kept on screen. A toast is gone in 3.2s and the
              provider's reason is the part worth reading. */}
          {result && (
            <div
              role="status"
              className={cn(
                "flex items-start gap-2.5 rounded-card border px-3.5 py-3 text-[12px] leading-[1.5]",
                result.ok
                  ? "border-ok/30 bg-ok-tint text-ok"
                  : "border-warn/30 bg-warn-tint text-warn",
              )}
            >
              <Icon
                name={result.ok ? "check" : "alert"}
                size={14}
                strokeWidth={2.3}
                className="mt-[1px] shrink-0"
              />
              <span className="min-w-0">
                <strong className="font-bold">
                  {result.ok
                    ? "Connection verified"
                    : result.unreachable
                      ? "EmeHub is unreachable"
                      : `${connection.label} rejected the credentials`}
                </strong>
                {result.message && (
                  <>
                    {" — "}
                    {result.message}
                  </>
                )}
              </span>
            </div>
          )}
          </div>
        </div>
      )}
    </div>
  );
}
