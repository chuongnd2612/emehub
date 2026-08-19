// Handoff § Overlays › "Claude credential popover (header chip): 330px, model
// name + source + Admin-managed/Your token, status pill, CREDENTIAL mono name,
// Token expires <date · in N days>, segmented Shared | Personal, Manage Claude
// credentials → Claude Settings."
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
  Segmented,
  StatusPill,
} from "@/components/ui";
import {
  formatDaysLeft,
  formatExpiryIso,
  getClaudeCredentialRevision,
  getCredentialState,
  setCredentialMode,
  statusOfCredential,
  subscribeClaudeCredentials,
  type ClaudeCredentialState,
  type CredentialSource,
  type CredentialStatus,
} from "@/data";
import {
  placeBelow,
  useAnchorRect,
  useEscape,
} from "@/hooks/useAnchoredPosition";
import { cn } from "@/lib/cn";
import { useUi } from "@/store/ui";

const POPOVER_WIDTH = 330;
const POPOVER_HEIGHT = 268;

/**
 * The model shown in the popover header. Claude Settings › Models owns the
 * real value; until that screen exposes it, the shell renders the default.
 */
const DEFAULT_MODEL = "Claude Sonnet 4.6";

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
} as const satisfies Record<CredentialStatus, string>;

const SOURCE_OPTIONS = [
  { value: "shared" as const, label: "Shared" },
  { value: "personal" as const, label: "Personal" },
];

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

  const load = useCallback(() => {
    let live = true;
    void getCredentialState()
      .then((next) => {
        if (live) setState(next);
      })
      .catch(() => {
        /* The chip degrades to "unknown"; the header must never break. */
      });
    return () => {
      live = false;
    };
  }, []);

  // Every credential write announces itself (`@/data/credentials`), and the chip
  // re-reads on the signal. Opening the popover used to be the only trigger
  // besides mount, so changing the credential in Claude Settings left the header
  // describing the previous state until the page was reloaded — and a status
  // that is wrong until refreshed is worse than one that is absent, because
  // nothing about it looks stale.
  const revision = useSyncExternalStore(
    subscribeClaudeCredentials,
    getClaudeCredentialRevision,
  );

  useEffect(load, [load, revision]);
  // Still re-read on open, for a change made somewhere this signal cannot reach
  // — another tab, or an admin replacing the shared account.
  useEffect(() => {
    if (open) load();
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

  const status: CredentialStatus = meta ? statusOfCredential(meta) : "expired";

  const chipLabel = isShared ? "Shared account" : "Personal token";
  const credentialName = meta?.label || (meta ? ".credentials.json" : "Not attached");
  const expiryLabel = meta
    ? `${formatExpiryIso(meta.expiresAt)} · ${formatDaysLeft(meta.daysLeft)}`
    : "—";

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
      .catch(() => load());
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
        onClick={() => setClaudeOpen(!open)}
        className={cn(
          "flex h-[38px] shrink-0 cursor-pointer items-center gap-[9px] rounded-[12px]",
          "border border-bd2 bg-card2 px-[13px] hover:bg-bd",
        )}
      >
        <span
          className={cn(
            "size-2 shrink-0 animate-pulse-dot rounded-full [animation-duration:2.2s]",
            DOT_CLASS[status],
          )}
        />
        <ClaudeMark size={14} className="shrink-0 text-claude" />
        <span className="max-w-[110px] truncate text-[12.5px] font-semibold text-txt3">
          {chipLabel}
        </span>
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
              "fixed z-[1000] animate-scale-in rounded-card border border-bd2",
              "bg-pop p-4 shadow-pop",
            )}
            style={{
              top: pos.top,
              left: pos.left,
              width: POPOVER_WIDTH,
              transformOrigin: pos.transformOrigin,
            }}
          >
            <div className="flex items-center gap-[11px] border-b border-bd2 pb-[13px]">
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
                  {DEFAULT_MODEL}
                </div>
                <div className="mt-0.5 truncate text-[11px] text-muted">
                  {isShared ? "Shared account" : "Personal account"} ·{" "}
                  {isShared ? "Admin-managed" : "Your token"}
                </div>
              </div>
              <StatusPill status={STATUS_LABEL[status]} size="sm" />
            </div>

            <div className="pt-[13px]">
              <div className="text-[9.5px] font-bold tracking-[.11em] text-label">
                CREDENTIAL
              </div>
              <div className="mt-1.5 truncate font-mono text-[12px] text-txt2">
                {credentialName}
              </div>
              <div className="mt-[5px] text-[11.5px] text-muted">
                Token expires {expiryLabel}
              </div>

              <Segmented
                options={SOURCE_OPTIONS}
                value={source}
                onChange={onSourceChange}
                variant="solid"
                className="mt-[13px] flex w-full [&>button]:flex-1"
              />

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
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
