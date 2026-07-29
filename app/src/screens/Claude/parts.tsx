// Small pieces shared by the three Claude Settings tabs. Nothing here is a
// design decision of its own — each one is a fragment the handoff repeats
// across the credential cards (meta cell, scope chips, the masked ACCESS TOKEN
// row, the inline code chip, the hidden-input upload control).

import type { ChangeEvent, DragEvent, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Icon, Spinner } from "@/components/ui";

/** 9.5px/700/.09em tracked label above a meta value. */
export function MetaLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-[9.5px] font-bold tracking-[.09em] text-label">
      {children}
    </div>
  );
}

/** One cell of the 3-up / 4-up meta grids. */
export function Meta({
  label,
  value,
  sub,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  /** Optional second line, e.g. the "in 76 days" under EXPIRES. */
  sub?: ReactNode;
  /** Renders the value in the accent colour (MAINTAINED BY). */
  accent?: boolean;
}) {
  return (
    <div className="min-w-0">
      <MetaLabel>{label}</MetaLabel>
      <div
        className={cn(
          "mt-[5px] text-[12.5px] font-bold",
          accent ? "text-ps-text" : "text-txt2",
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-[2px] text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

/** Mono chips under the SCOPES label. */
export function ScopeChips({ scopes }: { scopes: string[] }) {
  return (
    <div>
      <div className="mb-[7px]">
        <MetaLabel>SCOPES</MetaLabel>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {scopes.map((s) => (
          <span
            key={s}
            data-surface
            className="rounded-[7px] border border-bd2 bg-card3 px-[9px] py-[3px] font-mono text-[11px] font-semibold text-txt3"
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * What replaced the handoff's ACCESS TOKEN row.
 *
 * The handoff drew a masked token with a `Reveal` toggle. No credential
 * endpoint the SPA may call returns credential material — `CredentialMetaOut`
 * has no token field, and the one endpoint that does return the blob
 * (`GET /credentials/claude/resolve`) exists for the agents, not for a settings
 * screen. There is therefore nothing to mask and nothing to reveal, and
 * rendering a plausible-looking fake would be worse than saying so.
 */
export function StoredSecretRow({
  tone = "accent",
}: {
  /** `cyan` on the personal card, `accent` on the shared card. */
  tone?: "accent" | "cyan";
}) {
  return (
    <div>
      <div className="mb-[7px]">
        <MetaLabel>ACCESS TOKEN</MetaLabel>
      </div>
      <div
        data-surface
        className="flex items-center gap-2.5 rounded-control-lg border border-bd2 bg-code px-[13px] py-[11px]"
      >
        <span
          className={cn(
            "shrink-0",
            tone === "cyan" ? "text-cyan-soft" : "text-ps-text",
          )}
        >
          <Icon name="lock" size={13} strokeWidth={2.2} />
        </span>
        <span className="min-w-0 flex-1 font-mono text-[12px] text-txt3">
          Encrypted at rest · never returned by the hub
        </span>
      </div>
    </div>
  );
}

/** Inline mono code chip — `.credentials.json`, `~/.claude/.credentials.json`. */
export function CodeChip({
  children,
  tinted = true,
}: {
  children: ReactNode;
  /** The banner chips sit on a Claude tint; inline mentions elsewhere do not. */
  tinted?: boolean;
}) {
  return (
    <span
      className={cn(
        "font-mono text-[12px] text-terra",
        tinted && "rounded-[5px] bg-claude-tint px-1.5 py-px",
      )}
    >
      {children}
    </span>
  );
}

/**
 * A `<label>` wrapping a hidden file input — the pattern the handoff uses for
 * every credential upload (drop zone, Replace file, Rotate token, Add shared).
 * The input is reset after each pick so the same file can be chosen twice.
 */
export function FileUpload({
  onFile,
  className,
  children,
}: {
  onFile: (file: File) => void;
  className?: string;
  children: ReactNode;
}) {
  const handle = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onFile(file);
  };
  // "Drop your .credentials.json — or click to browse": the label is both a
  // browse trigger and a real drop target.
  const handleDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  };
  return (
    <label
      data-surface
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      className={cn("cursor-pointer", className)}
    >
      <input
        type="file"
        accept=".json,application/json"
        onChange={handle}
        className="hidden"
      />
      {children}
    </label>
  );
}

/** `Reading token…` — the 850 ms dwell after a successful parse. */
export function ReadingToken({ sub }: { sub?: string }) {
  return (
    <>
      <Spinner size={30} speed="upload" className="text-pl" />
      <div className="text-[13.5px] font-bold text-txt">Reading token…</div>
      {sub && <div className="text-[11.5px] text-muted">{sub}</div>}
    </>
  );
}

/** The 20px filled check on the selected source-chooser card. */
export function SelectedCheck() {
  return (
    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-grad text-white">
      <Icon name="check" size={12} strokeWidth={3.2} />
    </span>
  );
}
