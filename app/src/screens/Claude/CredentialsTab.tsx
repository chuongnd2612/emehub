// Handoff › 6. Claude Settings › Credentials — the important tab, wired to
// `GET /credentials/claude`.
//
// Layout is unchanged: explainer banner, then a 1.5fr / 1fr split (Your Claude
// account | credential health + usage + API key fallback), then the admin-only
// SHARED CLAUDE ACCOUNTS section.
//
// Three things the handoff drew that the hub cannot supply, and how each is
// handled honestly rather than faked:
//
//   • **ACCESS TOKEN row with Reveal.** No credential endpoint reachable from
//     the SPA returns credential material, so there is nothing to mask and
//     nothing to reveal. The row states that instead of showing a token.
//   • **`Authenticated · 42ms` + HTTP 200.** `POST /credentials/claude/test`
//     is a storage check — the hub never calls Claude — so the row reports the
//     hub's own verdict and result code.
//   • **`62% of quota` + a Q-Agent / D-Agent split.** Usage carries no quota
//     and no per-agent attribution; the bar shows the real input/output
//     composition of the week's tokens instead.

import {
  GlassCard,
  Glyph,
  Icon,
  LoadingState,
  Notice,
  Spinner,
  StatusPill,
  ErrorState,
} from "@/components/ui";
import {
  formatDaysLeft,
  formatExpiryIso,
  formatRefreshed,
  formatResetsIn,
  formatTokens,
  type ClaudeCredentialMeta,
  type ClaudeUsage,
} from "@/data";
import { cn } from "@/lib/cn";
import {
  CodeChip,
  FileUpload,
  Meta,
  ReadingToken,
  ScopeChips,
  SelectedCheck,
  StoredSecretRow,
} from "./parts";
import { SharedAccounts } from "./SharedAccounts";
import { metaStatusLabel, statusNote, type ClaudeSettings } from "./state";

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

export function CredentialsTab({ s }: { s: ClaudeSettings }) {
  if (s.load === "loading") {
    return <LoadingState label="Loading your Claude credentials…" />;
  }
  if (s.load === "error") {
    return (
      <ErrorState
        title="Could not load your Claude credentials"
        detail={s.loadError ?? undefined}
        onRetry={s.reload}
      />
    );
  }

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
              disabled={s.switching}
              onSelect={() => s.chooseSource("shared")}
              title="Shared account"
              tone="accent"
              icon={<Icon name="users" size={16} />}
              body="Maintained by a workspace admin. Nothing to set up — you are ready to run."
            />
            <SourceCard
              selected={s.credSource === "personal"}
              disabled={s.switching}
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
          {s.credSource === "shared" &&
            (s.shared ? (
              <SharedSummary meta={s.shared} />
            ) : (
              <Notice tone="warn">
                No shared Claude account is configured yet. An admin adds one
                below, or attach your own to run in the meantime.
              </Notice>
            ))}

          {/* Personal — attached card, or the dashed drop zone */}
          {s.credSource === "personal" &&
            (s.own ? (
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
                      {s.own.label || ".credentials.json"}
                    </div>
                    <div className="mt-[3px] text-[11.5px] text-muted">
                      Your personal Claude account
                    </div>
                  </div>
                  <StatusPill status={metaStatusLabel(s.own)} />
                </div>

                <StatusNote meta={s.own} />

                <div className="mt-4 grid grid-cols-3 gap-3">
                  <Meta
                    label="SUBSCRIPTION"
                    value={s.own.subscriptionType ?? "Claude account"}
                  />
                  <Meta
                    label="TOKEN EXPIRES"
                    value={
                      <>
                        {formatExpiryIso(s.own.expiresAt)}{" "}
                        <span className="font-medium text-muted">
                          · {formatDaysLeft(s.own.daysLeft)}
                        </span>
                      </>
                    }
                  />
                  <Meta
                    label="LAST REFRESHED"
                    value={formatRefreshed(s.own.lastRefreshed)}
                  />
                </div>

                <div className="mt-[15px]">
                  <ScopeChips scopes={s.own.scopes} />
                </div>

                <div className="mt-[15px]">
                  <StoredSecretRow tone="cyan" />
                </div>

                <div className="mt-4 flex gap-2.5 border-t border-bd3 pt-[14px]">
                  <FileUpload
                    onFile={s.attachPersonal}
                    className="inline-flex items-center gap-2 rounded-control-lg border border-bd2 bg-card3 px-[15px] py-[9px] text-[12.5px] font-semibold text-txt2 hover:bg-bd2"
                  >
                    {s.uploadingPersonal ? (
                      <Spinner size={14} speed="run" />
                    ) : (
                      <Icon name="upload" size={14} />
                    )}
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
          <HealthCard s={s} />
          <UsageCard usage={s.usage} error={s.usageError} />
        </div>
      </div>

      <SharedAccounts s={s} />
    </div>
  );
}

/* ── "Refreshes" explainer ───────────────────────────────────────────────── */

/**
 * One line under a `Refreshes` pill. A Claude access token lives hours, so this
 * is the state a real `.credentials.json` spends most of its life in — the pill
 * alone is too terse to stop it reading as a problem (issue #63). Renders
 * nothing for every other status.
 */
function StatusNote({ meta }: { meta: ClaudeCredentialMeta }) {
  const note = statusNote(meta);
  if (!note) return null;
  return (
    <div className="mt-3 flex items-start gap-2 text-[11.5px] leading-[1.5] text-muted text-pretty">
      <span className="mt-px shrink-0 text-cyan-soft">
        <Icon name="refresh" size={13} strokeWidth={2.2} />
      </span>
      {note}
    </div>
  );
}

/* ── Shared account summary ──────────────────────────────────────────────── */

function SharedSummary({ meta }: { meta: ClaudeCredentialMeta }) {
  return (
    <div data-surface className="rounded-[16px] border border-bd2 bg-inset p-4">
      <div className="flex items-center gap-3">
        <Glyph size={40} claude className="border border-claude/30" />
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-bold text-txt">
            {meta.label || "Shared Claude account"}
          </div>
          <div className="mt-0.5 font-mono text-[11.5px] text-muted">
            {meta.subscriptionType ?? "Claude account"}
          </div>
        </div>
        <StatusPill status={metaStatusLabel(meta)} />
      </div>

      <StatusNote meta={meta} />

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Meta
          label="SUBSCRIPTION"
          value={meta.subscriptionType ?? "Claude account"}
        />
        <Meta
          label="TOKEN EXPIRES"
          value={
            <>
              {formatExpiryIso(meta.expiresAt)}{" "}
              <span className="font-medium text-muted">
                · {formatDaysLeft(meta.daysLeft)}
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
        <b className="font-semibold text-muted">Your own account</b> to run on a
        personal plan instead.
      </div>
    </div>
  );
}

/* ── Credential health ───────────────────────────────────────────────────── */

const HEALTH_TONE = {
  ok: {
    box: "border-ok/25 bg-ok-tint",
    text: "text-ok",
    dot: "bg-ok shadow-[0_0_9px_var(--ok)]",
  },
  warn: {
    box: "border-warn/25 bg-warn-tint",
    text: "text-warn",
    dot: "bg-warn shadow-[0_0_9px_var(--warn)]",
  },
  danger: {
    box: "border-danger/30 bg-danger-tint",
    text: "text-danger",
    dot: "bg-danger shadow-[0_0_9px_var(--danger)]",
  },
} as const;

function HealthCard({ s }: { s: ClaudeSettings }) {
  const effective = s.mode === "own" ? s.own : s.mode === "shared" ? s.shared : null;
  const verdict = s.testResult;

  let tone: keyof typeof HEALTH_TONE = "danger";
  let line = "No Claude credential is configured.";
  let code = "none";

  if (verdict) {
    tone = verdict.ok ? "ok" : "danger";
    line = verdict.message;
    code = verdict.result;
  } else if (effective) {
    const label = metaStatusLabel(effective);
    // `Refreshes` is a ready credential: the access token has lapsed but the
    // CLI renews it on the next run (issue #63), so it is neither a warning
    // nor a failure — it reads ready, with the reason spelled out.
    tone =
      label === "Active" || label === "Refreshes"
        ? "ok"
        : label === "Expiring"
          ? "warn"
          : "danger";
    line =
      label === "Refreshes"
        ? s.mode === "own"
          ? "Ready · your own account, renews on next run"
          : "Ready · the shared account, renews on next run"
        : s.mode === "own"
          ? "Ready · your own account"
          : "Ready · the shared account";
    code = s.mode;
  }

  const t = HEALTH_TONE[tone];

  return (
    <GlassCard radius="panel" className="p-5">
      <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
        Connection health
      </div>
      <div
        className={cn(
          "mt-[14px] flex items-center gap-2.5 rounded-button border px-[15px] py-[13px]",
          t.box,
        )}
      >
        <span
          className={cn(
            "size-2 shrink-0 animate-pulse-dot rounded-full",
            t.dot,
          )}
        />
        <span className={cn("flex-1 text-[12.5px] font-bold text-pretty", t.text)}>
          {line}
        </span>
        <span className={cn("shrink-0 font-mono text-[11px]", t.text)}>
          {code}
        </span>
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
      <div className="mt-[9px] text-[11px] leading-[1.5] text-faint text-pretty">
        The hub checks the stored credential decrypts, parses, and either has
        not expired or carries a refresh token. It never calls Claude on your
        behalf.
      </div>
    </GlassCard>
  );
}

/* ── Usage ───────────────────────────────────────────────────────────────── */

/**
 * Real aggregates from `GET /credentials/claude/usage`
 * (`app/services/claude_usage.py` › `stats`), and they span THREE different
 * windows: the token total and its input/output split are the ISO week, the
 * dollar figure is the calendar month, the request count is today.
 *
 * The heading used to read "Usage this month", which described exactly one of
 * the three — and not the big number directly beneath it. It is now scope-free,
 * and every figure carries the window it actually covers in its own label.
 */
function UsageCard({
  usage,
  error,
}: {
  usage: ClaudeUsage | null;
  error: string | null;
}) {
  return (
    <GlassCard radius="panel" className="p-5">
      <div className="text-[14.5px] font-extrabold tracking-[-.01em] text-txt">
        Claude usage
      </div>

      {error && (
        <Notice tone="warn" className="mt-3">
          {error}
        </Notice>
      )}

      {!error && !usage && <LoadingState label="Loading usage…" compact />}

      {!error && usage && <UsageBody usage={usage} />}
    </GlassCard>
  );
}

function UsageBody({ usage }: { usage: ClaudeUsage }) {
  const { input, output } = usage.breakdown;
  const flow = input + output;
  const inputShare = flow > 0 ? Math.round((input / flow) * 100) : 0;

  return (
    <>
      <div className="mt-3 flex items-end gap-[9px]">
        <span className="text-[30px] leading-none font-black tracking-[-.04em] text-txt">
          {formatTokens(usage.weekTokens)}
        </span>
        <span className="pb-1 text-[11.5px] text-faint">
          tokens this week · resets {formatResetsIn(usage.weekResetsAt)}
        </span>
      </div>
      <div className="mt-[13px] h-[7px] overflow-hidden rounded-pill bg-bd2">
        {/* Computed width — the inline-style exemption. */}
        <div
          className="h-full rounded-pill bg-[linear-gradient(90deg,var(--pl),var(--p))]"
          style={{ width: `${inputShare}%` }}
        />
      </div>
      <div className="mt-[9px] flex justify-between text-[11px] text-label">
        <span>Input {formatTokens(input)}</span>
        <span>Output {formatTokens(output)}</span>
      </div>
      <div className="mt-[11px] border-t border-bd3 pt-[11px] text-[11px] text-faint">
        ${usage.costMonth.toFixed(2)} this month · {usage.requestsToday}{" "}
        {usage.requestsToday === 1 ? "request" : "requests"} today
      </div>
    </>
  );
}

/* ── Source chooser card ─────────────────────────────────────────────────── */

function SourceCard({
  selected,
  disabled,
  onSelect,
  title,
  body,
  icon,
  tone,
}: {
  selected: boolean;
  disabled?: boolean;
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
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        "flex-1 cursor-pointer rounded-[16px] p-4 text-left disabled:cursor-not-allowed",
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
