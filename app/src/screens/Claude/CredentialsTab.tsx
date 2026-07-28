// Handoff › 6. Claude Settings › Credentials — the important tab.
//
// Layout: explainer banner, then a 1.5fr / 1fr split (Your Claude account |
// connection health + usage + API key fallback), then the admin-only
// SHARED CLAUDE ACCOUNTS section.

import { GlassCard, Glyph, Icon, Spinner, StatusPill } from "@/components/ui";
import { formatDaysLeft, maskToken } from "@/data";
import { cn } from "@/lib/cn";
import {
  CodeChip,
  FileUpload,
  Meta,
  ReadingToken,
  ScopeChips,
  SelectedCheck,
  TokenRow,
} from "./parts";
import { SharedAccounts } from "./SharedAccounts";
import { defaultShared, statusLabel, type ClaudeSettings } from "./state";

/**
 * The one literal rgba in this screen. Handoff § 6 specifies the explainer
 * banner as `linear-gradient(135deg, rgba(217,119,87,.1), rgba(225,23,43,.05))`
 * — a two-brand blend (Claude terracotta into EMESOFT red) that no single token
 * expresses, and it is deliberately NOT accent-reactive, so it cannot be built
 * from `--pt`. Kept here, named, as the single documented exception to the
 * no-raw-colour rule.
 */
const CLAUDE_BANNER_GRADIENT =
  "linear-gradient(135deg, rgba(217,119,87,.1), rgba(225,23,43,.05))";

/** Usage this month — Handoff § 6, right column. */
const QUOTA_PERCENT = 62;

export function CredentialsTab({ s }: { s: ClaudeSettings }) {
  const shared = defaultShared(s.shared);
  const personalRevealed = !!s.revealed.personal;

  return (
    <div className="flex flex-col gap-[14px]">
      {/* ── Explainer banner ─────────────────────────────────────────── */}
      <div
        className="flex gap-[14px] rounded-card border border-claude/22 px-[18px] py-4"
        style={{ background: CLAUDE_BANNER_GRADIENT }}
      >
        <Glyph size={38} claude className="border border-claude/30" />
        <div className="text-[13px] leading-[1.65] text-txt3 text-pretty">
          Agents authenticate with the OAuth token inside a{" "}
          <CodeChip>.credentials.json</CodeChip>. Run on a{" "}
          <b className="font-bold text-txt">shared workspace account</b> an admin
          maintains, or attach your own Claude plan — whichever you pick is
          written to{" "}
          <CodeChip tinted={false}>~/.claude/.credentials.json</CodeChip> before
          every run of Q‑Agent and D‑Agent.
        </div>
      </div>

      {/* ── Your Claude account (1.5fr) | health column (1fr) ────────── */}
      <div className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] items-start gap-[14px]">
        <GlassCard radius="panel" className="flex flex-col gap-4 p-[22px]">
          <div>
            <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
              Your Claude account
            </div>
            <div className="mt-1 text-[12.5px] text-muted">
              Applies to your own agent runs only. Other members choose
              independently.
            </div>
          </div>

          {/* Source chooser */}
          <div className="flex gap-3">
            <SourceCard
              selected={s.credSource === "shared"}
              onSelect={() => s.chooseSource("shared")}
              title="Shared account"
              tone="accent"
              icon={<Icon name="users" size={16} />}
              body="Maintained by a workspace admin. Nothing to set up — you are ready to run."
            />
            <SourceCard
              selected={s.credSource === "personal"}
              onSelect={() => s.chooseSource("personal")}
              title="Your own account"
              tone="cyan"
              icon={<Icon name="key" size={16} />}
              body={
                <>
                  Attach a personal{" "}
                  <span className="font-mono text-[11px]">
                    .credentials.json
                  </span>{" "}
                  to spend your own Claude plan.
                </>
              }
            />
          </div>

          {/* Shared summary */}
          {s.credSource === "shared" && shared && (
            <div
              data-surface
              className="rounded-[16px] border border-bd2 bg-inset p-4"
            >
              <div className="flex items-center gap-3">
                <Glyph size={40} claude className="border border-claude/30" />
                <div className="min-w-0 flex-1">
                  <div className="text-[14px] font-bold text-txt">
                    {shared.label}
                  </div>
                  <div className="mt-0.5 font-mono text-[11.5px] text-muted">
                    {shared.email}
                  </div>
                </div>
                <StatusPill status={statusLabel(shared.daysLeft)} />
              </div>

              <div className="mt-4 grid grid-cols-3 gap-3">
                <Meta label="SUBSCRIPTION" value={shared.subscription} />
                <Meta
                  label="TOKEN EXPIRES"
                  value={
                    <>
                      {shared.expiresDisplay}{" "}
                      <span className="font-medium text-muted">
                        · {formatDaysLeft(shared.daysLeft)}
                      </span>
                    </>
                  }
                />
                <Meta label="MAINTAINED BY" value="Workspace admin" accent />
              </div>

              <div className="mt-4 flex items-center gap-[9px] border-t border-bd3 pt-[14px] text-[11.5px] text-faint text-pretty">
                <span className="shrink-0">
                  <Icon name="lock" size={13} />
                </span>
                An admin rotates this token. Switch to{" "}
                <b className="font-semibold text-muted">Your own account</b> to
                run on a personal plan instead.
              </div>
            </div>
          )}

          {/* Personal — attached card, or the dashed drop zone */}
          {s.credSource === "personal" &&
            (s.personal ? (
              <div
                data-surface
                className="rounded-[16px] border border-dagent/25 bg-inset p-4"
              >
                <div className="flex items-center gap-3">
                  <Glyph
                    size={40}
                    fill="dagent"
                    icon={<Icon name="doc" size={18} />}
                    className="border border-dagent/30"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-[13px] font-bold text-txt">
                      {s.personal.filename}
                    </div>
                    <div className="mt-[3px] text-[11.5px] text-muted">
                      Your personal Claude account
                    </div>
                  </div>
                  <StatusPill status={statusLabel(s.personal.daysLeft)} />
                </div>

                <div className="mt-4 grid grid-cols-3 gap-3">
                  <Meta label="SUBSCRIPTION" value={s.personal.subscription} />
                  <Meta
                    label="TOKEN EXPIRES"
                    value={
                      <>
                        {s.personal.expiresDisplay}{" "}
                        <span className="font-medium text-muted">
                          · {formatDaysLeft(s.personal.daysLeft)}
                        </span>
                      </>
                    }
                  />
                  <Meta
                    label="LAST REFRESHED"
                    value={s.personal.lastRefreshed}
                  />
                </div>

                <div className="mt-[15px]">
                  <ScopeChips scopes={s.personal.scopes} />
                </div>

                <div className="mt-[15px]">
                  <TokenRow
                    tone="cyan"
                    revealed={personalRevealed}
                    onToggle={() => s.toggleReveal("personal")}
                    value={
                      personalRevealed
                        ? s.personal.token
                        : maskToken(s.personal.token)
                    }
                  />
                </div>

                <div className="mt-4 flex gap-2.5 border-t border-bd3 pt-[14px]">
                  <FileUpload
                    onFile={s.attachPersonal}
                    className="inline-flex items-center gap-2 rounded-control-lg border border-bd2 bg-card3 px-[15px] py-[9px] text-[12.5px] font-semibold text-txt2 hover:bg-bd2"
                  >
                    <Icon name="upload" size={14} />
                    Replace file
                  </FileUpload>
                  <button
                    type="button"
                    data-surface
                    onClick={s.removePersonal}
                    className="inline-flex cursor-pointer items-center gap-2 rounded-control-lg border border-danger/30 bg-danger-tint px-[15px] py-[9px] text-[12.5px] font-bold text-danger hover:bg-danger/20"
                  >
                    <Icon name="trash" size={14} />
                    Remove &amp; use shared
                  </button>
                </div>
              </div>
            ) : (
              <FileUpload
                onFile={s.attachPersonal}
                className="flex flex-col items-center gap-[9px] rounded-[16px] border-[1.5px] border-dashed border-pb bg-pt p-8 text-center hover:bg-bd3"
              >
                {s.uploadingPersonal ? (
                  <ReadingToken sub="Parsing your .credentials.json" />
                ) : (
                  <>
                    <span className="flex size-[44px] items-center justify-center rounded-glyph-lg border border-pb bg-pt text-ps-text">
                      <Icon name="upload" size={21} strokeWidth={2.1} />
                    </span>
                    <div className="text-[14px] font-bold text-txt">
                      Drop your{" "}
                      <span className="font-mono text-[12.5px]">
                        .credentials.json
                      </span>
                    </div>
                    <div className="text-[12px] text-muted">
                      or click to browse · found at{" "}
                      <span className="font-mono text-[11px]">
                        ~/.claude/.credentials.json
                      </span>
                    </div>
                  </>
                )}
              </FileUpload>
            ))}
        </GlassCard>

        {/* Right column */}
        <div className="flex flex-col gap-[14px]">
          <GlassCard radius="panel" className="p-5">
            <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
              Connection health
            </div>
            <div className="mt-[14px] flex items-center gap-2.5 rounded-button border border-ok/25 bg-ok-tint px-[15px] py-[13px]">
              <span className="size-2 shrink-0 animate-pulse-dot rounded-full bg-ok shadow-[0_0_9px_var(--ok)]" />
              <span className="flex-1 text-[12.5px] font-bold text-ok">
                Authenticated · 42ms
              </span>
              <span className="font-mono text-[11px] text-ok">200</span>
            </div>
            <button
              type="button"
              data-surface
              onClick={s.testConnection}
              disabled={s.testing}
              className="mt-[11px] flex w-full cursor-pointer items-center justify-center gap-2 rounded-control-lg border border-bd2 bg-card2 py-[11px] text-[12.5px] font-semibold text-txt3 hover:bg-bd disabled:cursor-not-allowed"
            >
              {s.testing && <Spinner size={13} speed="run" />}
              {s.testing ? "Testing…" : "Test connection"}
            </button>
          </GlassCard>

          <GlassCard radius="panel" className="p-5">
            <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
              Usage this month
            </div>
            <div className="mt-3 flex items-end gap-[9px]">
              <span className="text-[30px] leading-none font-black tracking-[-.04em] text-txt">
                18.4M
              </span>
              <span className="pb-1 text-[11.5px] text-faint">
                tokens · {QUOTA_PERCENT}% of quota
              </span>
            </div>
            <div className="mt-[13px] h-[7px] overflow-hidden rounded-pill bg-bd2">
              {/* Computed width — the inline-style exemption. */}
              <div
                className="h-full rounded-pill bg-[linear-gradient(90deg,var(--pl),var(--p))]"
                style={{ width: `${QUOTA_PERCENT}%` }}
              />
            </div>
            <div className="mt-[9px] flex justify-between text-[11px] text-label">
              <span>Q‑Agent 14.1M</span>
              <span>D‑Agent 4.3M</span>
            </div>
          </GlassCard>

          <div
            data-surface
            className="rounded-panel border border-bd3 bg-inset p-5"
          >
            <div className="text-[13.5px] font-extrabold tracking-[-.01em] text-txt">
              API key fallback
            </div>
            <div className="mt-1 text-[12px] leading-[1.5] text-muted">
              Used by headless CI runners that have no Claude account attached.
            </div>
            <div
              data-surface
              className="mt-[13px] flex items-center gap-2.5 rounded-control-lg border border-bd2 bg-code px-[13px] py-[11px]"
            >
              <span className="shrink-0 text-ps-text">
                <Icon name="key" size={14} strokeWidth={2.2} />
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-txt3">
                {s.showKey ? s.apiKey : maskToken(s.apiKey)}
              </span>
              <button
                type="button"
                onClick={() => s.setShowKey(!s.showKey)}
                className="shrink-0 cursor-pointer bg-transparent text-[11.5px] font-semibold text-ps-text"
              >
                {s.showKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <SharedAccounts s={s} />
    </div>
  );
}

/* ── Source chooser card ─────────────────────────────────────────────────── */

function SourceCard({
  selected,
  onSelect,
  title,
  body,
  icon,
  tone,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  body: React.ReactNode;
  icon: React.ReactNode;
  tone: "accent" | "cyan";
}) {
  return (
    <button
      type="button"
      data-surface
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex-1 cursor-pointer rounded-[16px] p-4 text-left",
        selected ? "border border-pb bg-pt" : "border border-bd2 bg-inset",
      )}
    >
      <div className="mb-2 flex items-center gap-[9px]">
        <span
          className={cn(
            "flex size-[30px] shrink-0 items-center justify-center rounded-[10px] border",
            tone === "accent"
              ? "border-pb bg-pt text-ps-text"
              : "border-dagent/30 bg-dagent-tint text-cyan-soft",
          )}
        >
          {icon}
        </span>
        <span className="flex-1 text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
          {title}
        </span>
        {selected && <SelectedCheck />}
      </div>
      <div className="text-[12px] leading-[1.5] text-muted">{body}</div>
    </button>
  );
}
