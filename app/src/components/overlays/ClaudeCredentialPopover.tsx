// Handoff § Overlays › "Claude credential popover (header chip): 330px, model
// name + source + Admin-managed/Your token, status pill, CREDENTIAL mono name,
// Token expires <date · in N days>, segmented Shared | Personal, Manage Claude
// credentials → Claude Settings."
//
// The handoff's panel is the credential half. The rest — the live model, the
// context window, the effort level and the week's usage — is the information
// architecture of QAgent's `ClaudeStatsButton`, which answers the question this
// chip is actually asked: *what will the next run use, and what has it spent?*
// The chip used to answer neither. It named a hardcoded model and reported only
// which of the two credentials was selected.
//
// ## What the hub cannot show, and why it does not pretend to
//
// QAgent runs the Claude CLI locally, so its panel can show a plan-usage
// percentage, a weekly budget gauge and a "Claude CLI unavailable" health
// state. **None of those are observable here.** The hub never invokes Claude
// for any of this: agents report each completed call and
// `api/app/services/claude_usage.py` aggregates what arrives. So:
//
//   • absolute figures only — no percentage of a limit nobody told us, no
//     budget the hub has no setting for;
//   • the status dot keeps its four credential-derived states and gains no
//     health dimension, because there is no probe behind one;
//   • the session window IS shown, and is not one of the above. It needs no
//     CLI — a rolling five hours over rows the hub already stores, resetting
//     five hours after the window's first call, which is exactly how QAgent
//     defines its own. The panel labels it `rolling 5h` so the figure explains
//     itself rather than looking like a number somebody chose;
//   • "Test credential" is a STORAGE check — present, decryptable, parseable,
//     unexpired. Its wording is taken verbatim from Claude Settings' own, since
//     two phrasings of a security-relevant claim drift apart.
//
// Trigger + popover live together because the popover is anchored to the
// trigger's rect. It is portalled to document.body with FIXED positioning —
// the header is a glass panel and its backdrop-filter traps z-index
// (CLAUDE.md › Frontend conventions).

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import {
  Button,
  ClaudeMark,
  Icon,
  Pill,
  Segmented,
  Skeleton,
  Spinner,
  StatusPill,
  toast,
  type SegmentedOption,
} from "@/components/ui";
import {
  formatCost,
  formatDaysLeft,
  formatExpiryIso,
  formatLatency,
  formatModel,
  formatRefreshed,
  formatResetsIn,
  formatTokens,
  getClaudeCredentialRevision,
  getClaudeUsage,
  getCredentialState,
  getModelPreferences,
  getModelPreferencesRevision,
  setCredentialMode,
  statusOfCredential,
  subscribeClaudeCredentials,
  subscribeModelPreferences,
  testCredential,
  type ClaudeCredentialMeta,
  type ClaudeCredentialState,
  type ClaudeUsage,
  type CredentialSource,
  type CredentialStatus,
  type ModelPreferences,
  type UsageWindow,
} from "@/data";
import {
  placeBelow,
  useAnchorRect,
  useEscape,
} from "@/hooks/useAnchoredPosition";
import { cn } from "@/lib/cn";
import { effortOption, modelOption } from "@/screens/Claude/state";
import { useUi } from "@/store/ui";

const POPOVER_WIDTH = 330;
/**
 * What the panel wants — measured against the fullest state: a credential with
 * a subscription and scopes, both usage windows, the four-way token breakdown
 * and a three-model rollup. `placeBelow` caps it to the room available and the
 * panel scrolls only when the window is genuinely too short. Under-declaring it
 * is not a harmless guess: the cap is `min(want, room)`, so a number below the
 * real content height makes the panel scroll on a tall window with 300px of
 * empty space beneath it.
 *
 * Measured, not estimated — `scrollHeight` of the panel in that state is 935.
 * It was 760 before the session/week rows and BY MODEL were added, and left
 * behind by them; re-measure this when the panel grows again. A rollup longer
 * than three models scrolls, which is the intended fallback rather than a
 * reason to keep inflating the number.
 */
const POPOVER_HEIGHT = 940;

/**
 * The chip's four credential states plus `none` — no credential attached at
 * all. `none` is deliberately not folded into `expired`: a fresh account has
 * nothing wrong with it, and telling a member their credential has expired when
 * they never had one sends them looking for a problem that does not exist.
 */
type ChipState = CredentialStatus | "none";

const STATUS_LABEL = {
  active: "Active",
  expiring: "Expiring",
  // Issue #63 — elapsed access token, refresh token on file, CLI renews it.
  refreshable: "Refreshes",
  expired: "Expired",
} as const satisfies Record<CredentialStatus, string>;

const DOT_CLASS = {
  active: "bg-ok shadow-[0_0_8px_var(--ok)]",
  expiring: "bg-warn shadow-[0_0_8px_var(--warn)]",
  refreshable: "bg-cyan-soft shadow-[0_0_8px_var(--dagent)]",
  expired: "bg-danger shadow-[0_0_8px_var(--danger)]",
  // No glow: nothing is live, so nothing should look lit.
  none: "bg-muted",
} as const satisfies Record<ChipState, string>;

/** The chip's `title`. A dot with no explanation is a colour, not a status. */
const STATUS_TITLE = {
  active: "Claude credential is active",
  expiring: "Claude credential expires soon — open to review it",
  refreshable:
    "The access token has lapsed; the refresh token on file renews it on the next run",
  expired: "Claude credential has expired — open to re-attach it",
  none: "No Claude credential attached — open to add one",
} as const satisfies Record<ChipState, string>;

/**
 * Typed one wider than the two options it lists, so the control can be given a
 * value that matches neither and render with nothing selected. `source` falls
 * back to "shared" for any mode that is not "own" — including "none" — so
 * without this the switch highlights the shared account on a member who has no
 * credential at all, which is the same wrong claim the header sub-line made.
 */
const SOURCE_OPTIONS: SegmentedOption<CredentialSource | "none">[] = [
  { value: "shared", label: "Shared" },
  { value: "personal", label: "Personal" },
];

/**
 * One line, used in two places — under the Test credential button and as the
 * outcome's toast body. Lifted verbatim from Claude Settings › Connection
 * health rather than reworded: it is a claim about whether the hub called
 * Claude, and a second phrasing of that is a second thing to keep true.
 */
const TEST_SCOPE_NOTE =
  "The hub checks the stored credential decrypts, parses, and either has not " +
  "expired or carries a refresh token. It never calls Claude on your behalf.";

/** Chip label — "Claude Opus 5" does not fit, "Opus 5" does. */
function shortModel(label: string): string {
  return label.replace(/^Claude\s+/i, "").trim() || label;
}

export function ClaudeCredentialChip() {
  const navigate = useNavigate();
  const open = useUi((s) => s.claudeOpen);
  const setClaudeOpen = useUi((s) => s.setClaudeOpen);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const anchor = useAnchorRect(triggerRef, open);

  // The whole credential state, so the chip reports what the hub will ACTUALLY
  // run with. This used to default `source` to "shared" and fetch only the
  // shared credential, so a user on their own token saw the shared one's
  // status — an expired shared account made the chip read "Expired" while
  // their own credential was fine (issue #70).
  const [state, setState] = useState<ClaudeCredentialState | null>(null);
  const [prefs, setPrefs] = useState<ModelPreferences | null>(null);
  const [usage, setUsage] = useState<ClaudeUsage | null>(null);
  const [usageFailed, setUsageFailed] = useState(false);
  /** False only before the first answer. Drives the chip's skeleton. */
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  // A generation counter rather than a per-effect `live` flag, because the
  // refresh button fires the same load imperatively: two loads can be in flight
  // at once and only the newest may write.
  const generation = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /**
   * Re-read what the chip reports. `withUsage` is false for the background
   * reads: usage is only rendered inside the panel, so fetching it on every
   * credential signal would be a request for a figure nobody is looking at.
   *
   * Every leg degrades on its own. The header must never break, and a panel
   * missing its usage block is worth more than no header at all.
   */
  const load = useCallback((withUsage: boolean) => {
    const mine = ++generation.current;
    const mineStill = () => alive.current && generation.current === mine;
    setBusy(true);

    const jobs: Promise<unknown>[] = [
      getCredentialState()
        .then((next) => {
          if (mineStill()) setState(next);
        })
        .catch(() => {
          /* The chip degrades to "unknown". */
        }),
      getModelPreferences()
        .then((next) => {
          if (mineStill()) setPrefs(next);
        })
        .catch(() => {
          /* The model name degrades to "Claude". */
        }),
    ];

    if (withUsage) {
      jobs.push(
        getClaudeUsage()
          .then((next) => {
            if (!mineStill()) return;
            setUsage(next);
            setUsageFailed(false);
          })
          .catch(() => {
            if (mineStill()) setUsageFailed(true);
          }),
      );
    }

    void Promise.all(jobs).then(() => {
      if (!mineStill()) return;
      setBusy(false);
      setReady(true);
    });
  }, []);

  // Every credential write announces itself (`@/data/credentials`), and every
  // model-preference write announces itself the same way (`@/data/models`). The
  // chip re-reads on either signal. Opening the popover used to be the only
  // trigger besides mount, so changing the credential — or, once the chip named
  // a real model, changing the model — in Claude Settings left the header
  // describing the previous state until the page was reloaded. A status that is
  // wrong until refreshed is worse than one that is absent, because nothing
  // about it looks stale.
  const credentialRevision = useSyncExternalStore(
    subscribeClaudeCredentials,
    getClaudeCredentialRevision,
  );
  const modelRevision = useSyncExternalStore(
    subscribeModelPreferences,
    getModelPreferencesRevision,
  );

  useEffect(() => {
    load(false);
  }, [load, credentialRevision, modelRevision]);

  // Still re-read on open, for a change made somewhere those signals cannot
  // reach — another tab, or an admin replacing the shared account — and to pull
  // the usage the panel is about to render.
  useEffect(() => {
    if (open) load(true);
  }, [open, load]);

  const close = useCallback(() => setClaudeOpen(false), [setClaudeOpen]);
  useEscape(open, close);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (panelRef.current?.contains(t)) return;
      if (triggerRef.current?.contains(t)) return;
      close();
    };
    document.addEventListener("mousedown", onDown, true);
    return () => document.removeEventListener("mousedown", onDown, true);
  }, [open, close]);

  // `mode` is what the hub RESOLVES for this user (own → shared → none), which
  // is the only honest thing for the chip to report. It is not a local
  // preference and must never default.
  const source: CredentialSource = state?.mode === "own" ? "personal" : "shared";
  const isShared = source === "shared";
  const meta = isShared ? (state?.shared ?? null) : (state?.own ?? null);

  const chipState: ChipState = meta ? statusOfCredential(meta) : "none";

  const model = prefs ? modelOption(prefs.mainModel) : null;
  // An id the hub knows and this build does not still renders as itself, which
  // is more use than an empty control.
  const modelName = model?.label ?? prefs?.mainModel ?? "Claude";

  const onSourceChange = (next: CredentialSource) => {
    const wantsOwn = next === "personal";
    // Nothing to switch to — send them to Claude Settings to attach one,
    // rather than silently selecting a credential that does not exist.
    if (wantsOwn && !state?.hasOwn) {
      close();
      navigate("/app/claude");
      return;
    }
    if (!wantsOwn && !state?.hasShared) {
      close();
      navigate("/app/claude");
      return;
    }
    // A real, persisted switch — `PUT /credentials/claude/mode`.
    void setCredentialMode(wantsOwn ? "own" : "shared")
      .then(setState)
      .catch(() => load(false));
  };

  const onTest = () => {
    setTesting(true);
    void testCredential()
      .then((result) => {
        // The hub's verdict verbatim on failure; a pass is qualified with what
        // was actually checked, so "verified" cannot be read as "Claude
        // answered".
        toast(
          result.ok ? "Credential verified" : "Credential check failed",
          result.ok ? "ok" : "warn",
          result.ok ? TEST_SCOPE_NOTE : result.message,
        );
      })
      .catch(() => {
        toast("Credential check failed", "warn", "The hub did not answer");
      })
      .finally(() => {
        if (alive.current) setTesting(false);
      });
  };

  const pos = anchor
    ? placeBelow(anchor, POPOVER_WIDTH, POPOVER_HEIGHT, "end", 8)
    : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        data-surface
        aria-haspopup="dialog"
        aria-expanded={open}
        // Before the first answer there is nothing to open — and no honest
        // status to show either, which is why the dot is a placeholder too.
        disabled={!ready}
        title={ready ? STATUS_TITLE[chipState] : "Loading Claude status…"}
        onClick={() => setClaudeOpen(!open)}
        className={cn(
          "flex h-[38px] shrink-0 cursor-pointer items-center gap-[9px] rounded-[12px]",
          "border border-bd2 bg-card2 px-[13px] hover:bg-bd",
          "disabled:cursor-default disabled:hover:bg-card2",
        )}
      >
        {ready ? (
          <span
            className={cn(
              "size-2 shrink-0 animate-pulse-dot rounded-full [animation-duration:2.2s]",
              DOT_CLASS[chipState],
            )}
          />
        ) : (
          <Skeleton radius="pill" className="size-2 shrink-0" />
        )}
        <ClaudeMark size={14} className="shrink-0 text-claude" />
        {ready ? (
          <span className="max-w-[110px] truncate text-[12.5px] font-semibold text-txt3">
            {shortModel(modelName)}
          </span>
        ) : (
          <Skeleton className="h-[11px] w-[62px]" />
        )}
        <Icon
          name="chevronDown"
          size={13}
          strokeWidth={2.4}
          className="shrink-0 text-faint"
        />
      </button>

      {open &&
        pos &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label="Claude credential"
            className={cn(
              "fixed z-[1000] animate-scale-in overflow-x-hidden overflow-y-auto",
              "rounded-card border border-bd2 bg-pop p-4 shadow-pop",
            )}
            // `maxHeight` for the same reason as the dropdown's: this panel has a
            // declared height, but a short window (or browser zoom) can still
            // leave less room than that, and the part that falls off the bottom
            // here is the Shared|Personal switch.
            style={{
              top: pos.top,
              left: pos.left,
              width: POPOVER_WIDTH,
              maxHeight: pos.maxHeight,
              transformOrigin: pos.transformOrigin,
            }}
          >
            <PanelHeader
              modelName={modelName}
              ctxWindow={model?.ctxWindow ?? null}
              // `source` falls back to "shared" whenever the mode is not "own",
              // which includes "none" — so the header must be told there is no
              // credential rather than inferring an account from it. It read
              // "Shared account · Admin-managed" on an account that had none.
              hasCredential={meta != null}
              isShared={isShared}
              chipState={chipState}
              busy={busy}
              onRefresh={() => load(true)}
            />

            <EffortRow prefs={prefs} />

            <CredentialBlock
              meta={meta}
              chipState={chipState}
              source={source}
              isShared={isShared}
              testing={testing}
              onSourceChange={onSourceChange}
              onTest={onTest}
            />

            <UsageBlock usage={usage} failed={usageFailed} />

            <Button
              variant="ghost"
              className="mt-[11px] w-full"
              onClick={() => {
                close();
                navigate("/app/claude");
              }}
            >
              Manage Claude credentials
            </Button>
          </div>,
          document.body,
        )}
    </>
  );
}

/* ── Header ──────────────────────────────────────────────────────────────── */

function PanelHeader({
  modelName,
  ctxWindow,
  hasCredential,
  isShared,
  chipState,
  busy,
  onRefresh,
}: {
  modelName: string;
  ctxWindow: string | null;
  hasCredential: boolean;
  isShared: boolean;
  chipState: ChipState;
  busy: boolean;
  onRefresh: () => void;
}) {
  return (
    <>
      <div className="flex items-center gap-[11px]">
        <span
          className={cn(
            "flex size-[34px] shrink-0 items-center justify-center rounded-[11px]",
            "border border-claude/30 bg-claude-tint",
          )}
        >
          <ClaudeMark size={18} className="text-claude" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-extrabold tracking-[-.01em] text-txt">
            {modelName}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-muted">
            {!hasCredential
              ? "No credential attached"
              : isShared
                ? "Shared account · Admin-managed"
                : "Personal account · Your token"}
          </div>
        </div>
        <button
          type="button"
          data-surface
          onClick={onRefresh}
          disabled={busy}
          title="Refresh"
          aria-label="Refresh"
          className={cn(
            "flex size-7 shrink-0 cursor-pointer items-center justify-center",
            "rounded-control border border-bd2 bg-card2 text-txt3",
            "hover:bg-bd disabled:cursor-default",
          )}
        >
          {/* A busy indicator keeps turning under `prefers-reduced-motion` —
              theme.css carves the spinners out of the blanket rule on purpose
              (#180): a frozen spinner reads as a hang, not as reduced motion. */}
          {busy ? (
            <Spinner size={13} speed="run" />
          ) : (
            <Icon name="refresh" size={13} strokeWidth={2.2} />
          )}
        </button>
      </div>

      <div className="mt-[11px] flex flex-wrap items-center gap-1.5 border-b border-bd2 pb-[13px]">
        {chipState === "none" ? (
          <Pill tone="neutral" size="sm">
            Not set
          </Pill>
        ) : (
          <StatusPill status={STATUS_LABEL[chipState]} size="sm" />
        )}
        {ctxWindow && (
          <Pill tone="claude" size="sm" mono>
            {ctxWindow} ctx
          </Pill>
        )}
      </div>
    </>
  );
}

/* ── Effort ──────────────────────────────────────────────────────────────── */

/**
 * The one setting on this panel that changes what a run *spends*: the hub
 * resolves `claude --effort` from these preferences before invoking the CLI
 * (`api/app/services/model_preferences.py` › `resolve_for_run`). It is stated
 * and not editorialised — the trade-off is explained where it is chosen, on
 * Claude Settings › Models.
 */
function EffortRow({ prefs }: { prefs: ModelPreferences | null }) {
  if (!prefs) return null;
  const effort = effortOption(prefs.effort);
  return (
    <div className="border-b border-bd2 py-[13px]">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          EFFORT
        </span>
        <span className="truncate text-[12px] font-bold text-txt2">
          {effort?.label ?? prefs.effort}
        </span>
      </div>
      <div className="mt-[5px] text-[11px] leading-[1.5] text-faint text-pretty">
        {prefs.usingDefaults
          ? "The workspace default, applied to knowledge builds the hub runs."
          : "Applied to knowledge builds the hub runs."}
      </div>
    </div>
  );
}

/* ── Credential ──────────────────────────────────────────────────────────── */

function CredentialBlock({
  meta,
  chipState,
  source,
  isShared,
  testing,
  onSourceChange,
  onTest,
}: {
  meta: ClaudeCredentialMeta | null;
  chipState: ChipState;
  source: CredentialSource;
  isShared: boolean;
  testing: boolean;
  onSourceChange: (next: CredentialSource) => void;
  onTest: () => void;
}) {
  return (
    <div className="border-b border-bd2 py-[13px]">
      <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
        CREDENTIAL
      </div>

      {meta ? (
        <>
          <div className="mt-1.5 truncate font-mono text-[12px] text-txt2">
            {meta.label || ".credentials.json"}
          </div>
          {(meta.subscriptionType || meta.scopes.length > 0) && (
            <div className="mt-[5px] truncate text-[11.5px] text-muted">
              {[meta.subscriptionType, meta.scopes.join(", ")]
                .filter(Boolean)
                .join(" · ")}
            </div>
          )}
          <div className="mt-[5px] text-[11.5px] text-muted">
            Token expires {formatExpiryIso(meta.expiresAt)} ·{" "}
            {formatDaysLeft(meta.daysLeft)}
          </div>
          <div className="mt-[3px] text-[11.5px] text-muted">
            Last refreshed {formatRefreshed(meta.lastRefreshed)}
          </div>
        </>
      ) : (
        // A fresh account, not a broken one. Rows of em dashes would say
        // nothing; one sentence and the switch below say what to do next.
        <div className="mt-1.5 text-[11.5px] leading-[1.5] text-muted text-pretty">
          No Claude credential is attached yet. Attach one in Claude Settings, or
          switch to the shared account if your workspace has one.
        </div>
      )}

      <Segmented
        options={SOURCE_OPTIONS}
        // Nothing is selected when nothing is attached.
        value={meta ? source : "none"}
        // The options list holds only the two real sources, so a change can
        // never carry the "none" sentinel back out.
        onChange={(next) => onSourceChange(next as CredentialSource)}
        variant="solid"
        className="mt-[13px] flex w-full [&>button]:flex-1"
      />

      <button
        type="button"
        data-surface
        onClick={onTest}
        disabled={testing || !meta}
        className={cn(
          "mt-[9px] flex w-full cursor-pointer items-center justify-center gap-2",
          "rounded-control-lg border border-bd2 bg-card2 py-[9px]",
          "text-[12px] font-semibold text-txt3 hover:bg-bd",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        {testing ? (
          <Spinner size={12} speed="run" />
        ) : (
          <Icon name="shield" size={12} strokeWidth={2.2} />
        )}
        {testing ? "Testing…" : "Test credential"}
      </button>
      <div className="mt-[7px] text-[11px] leading-[1.5] text-faint text-pretty">
        {TEST_SCOPE_NOTE}
      </div>

      {chipState === "expired" && (
        <div className="mt-[7px] text-[11px] font-semibold text-warn">
          This credential has expired — re-attach it or switch account.
        </div>
      )}
      {isShared && chipState === "none" && (
        <div className="mt-[7px] text-[11px] font-semibold text-warn">
          Runs will fail until a credential is attached.
        </div>
      )}
    </div>
  );
}

/* ── Usage ───────────────────────────────────────────────────────────────── */

/**
 * One rolling window: a label, the window's cost as the headline, and a sub-line
 * of what that cost is made of.
 *
 * QAgent puts a "% of plan used" gauge here. The hub cannot: it is told about
 * calls after they finish and knows no limit to be a percentage of. Cost is not
 * a consolation prize for that — it is the same figure QAgent itself falls back
 * to whenever the CLI does not hand it a limit.
 */
function UsageWindowRow({
  label,
  qualifier,
  window,
}: {
  label: string;
  qualifier: string;
  window: UsageWindow;
}) {
  return (
    <div className="mt-[13px] first:mt-0">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
            {label}
          </span>
          <span className="truncate text-[10px] text-faint">{qualifier}</span>
        </div>
        <span className="shrink-0 font-mono text-[12.5px] font-bold text-txt">
          {formatCost(window.costUsd)}
        </span>
      </div>
      <div className="mt-[5px] text-[11px] text-muted">
        {formatTokens(window.tokens)} tokens · {window.requests}{" "}
        {window.requests === 1 ? "request" : "requests"} · resets{" "}
        {formatResetsIn(window.resetsAt)}
      </div>
    </div>
  );
}

/**
 * `GET /credentials/claude/usage`. Two rolling windows (session, week), the
 * week's four-way token breakdown, the week's spend per model, and a footer of
 * the three figures that carry their own windows — month cost, today's requests,
 * today's latency.
 *
 * Every figure states the window it covers, because no single heading describes
 * all of them.
 */
function UsageBlock({
  usage,
  failed,
}: {
  usage: ClaudeUsage | null;
  failed: boolean;
}) {
  if (failed) {
    return (
      <div className="py-[13px] text-[11.5px] text-muted">
        Usage is unavailable right now.
      </div>
    );
  }

  if (!usage) {
    return (
      <div className="py-[13px]">
        <Skeleton className="h-[9px] w-[54px]" />
        <Skeleton className="mt-2.5 h-[18px] w-[130px]" />
        <Skeleton className="mt-2.5 h-[11px] w-full" />
        <Skeleton className="mt-1.5 h-[11px] w-4/5" />
      </div>
    );
  }

  const { input, output, cacheRead, cacheWrite } = usage.breakdown;
  // Tone tokens, never a hex — and each is a background here, so the light-mode
  // darkening map does not come into it.
  const rows: Array<[string, number, string]> = [
    ["Input", input, "bg-p"],
    ["Output", output, "bg-info"],
    ["Cache read", cacheRead, "bg-ok"],
    ["Cache write", cacheWrite, "bg-warn"],
  ];
  // One model is not a comparison, so the rollup earns its space from two up —
  // below that the week row already says everything it would.
  const byModel = usage.byModel.length > 1 ? usage.byModel : [];

  return (
    <div className="py-[13px]">
      <UsageWindowRow
        label="CURRENT SESSION"
        qualifier="rolling 5h"
        window={usage.session}
      />
      <UsageWindowRow
        label="CURRENT WEEK"
        qualifier="since Monday"
        window={usage.week}
      />

      {usage.weekTokens > 0 && (
        <div className="mt-[13px] flex flex-col gap-1.5 border-t border-bd3 pt-[11px]">
          {rows.map(([label, value, dot]) => (
            <div key={label} className="flex items-center gap-2">
              <span className={cn("size-2 shrink-0 rounded-full", dot)} />
              <span className="flex-1 text-[11px] text-muted">{label}</span>
              <span className="font-mono text-[11px] font-semibold text-txt2">
                {formatTokens(value)}
              </span>
            </div>
          ))}
        </div>
      )}

      {byModel.length > 0 && (
        <div className="mt-[13px] border-t border-bd3 pt-[11px]">
          <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
            BY MODEL
          </div>
          <div className="mt-[9px] flex flex-col gap-1.5">
            {byModel.map((entry) => (
              <div key={entry.model} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[11px] text-muted">
                  {formatModel(entry.model)}
                </span>
                <span className="shrink-0 text-[10.5px] text-faint">
                  {formatTokens(entry.tokens)} tokens
                </span>
                <span className="shrink-0 font-mono text-[11px] font-semibold text-txt2">
                  {formatCost(entry.costUsd)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-[11px] border-t border-bd3 pt-[9px] text-[11px] text-faint">
        {formatCost(usage.costMonth)} this month · {usage.requestsToday}{" "}
        {usage.requestsToday === 1 ? "request" : "requests"} today
        {usage.avgLatencyMs > 0 && ` · ${formatLatency(usage.avgLatencyMs)} avg`}
      </div>
      <div className="mt-[7px] flex items-start gap-1.5 text-[11px] leading-[1.5] text-faint text-pretty">
        <Icon
          name="alert"
          size={12}
          strokeWidth={2.2}
          className="mt-[2px] shrink-0"
        />
        <span>
          Estimated from token usage, and limited to what agents have reported to
          the hub.
        </span>
      </div>
    </div>
  );
}
