// Handoff § Overlays › "Claude credential popover (header chip): 330px, model
// name + source + Admin-managed/Your token, status pill, CREDENTIAL mono name,
// Token expires <date · in N days>, segmented Shared | Personal, Manage Claude
// credentials → Claude Settings."
//
// Trigger + popover live together because the popover is anchored to the
// trigger's rect. It is portalled to document.body with FIXED positioning —
// the header is a glass panel and its backdrop-filter traps z-index
// (CLAUDE.md › Frontend conventions).

import { useCallback, useEffect, useRef, useState } from "react";
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
  derivedCredentialStatus,
  formatDaysLeft,
  getSharedCredentials,
  type CredentialSource,
  type CredentialStatus,
  type SharedCredential,
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

  const [shared, setShared] = useState<SharedCredential[]>([]);
  // Which credential the workspace runs on. Claude Settings › Credentials owns
  // the persisted value; the shell keeps its own until that screen lands.
  const [source, setSource] = useState<CredentialSource>("shared");

  useEffect(() => {
    let live = true;
    void getSharedCredentials().then((rows) => {
      if (live) setShared(rows);
    });
    return () => {
      live = false;
    };
  }, []);

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

  // The default shared credential is `isDefault`, falling back to the first.
  const defaultCred = shared.find((c) => c.isDefault) ?? shared[0] ?? null;
  const isShared = source === "shared";

  // Derived status: shared → the default credential's; personal → always
  // "expired" until a personal token is attached (none is, see below).
  const status: CredentialStatus = isShared
    ? defaultCred
      ? derivedCredentialStatus(defaultCred)
      : "expired"
    : "expired";

  const chipLabel = isShared ? "Shared account" : "Personal token";
  const credentialName = isShared
    ? (defaultCred?.label ?? "—")
    : "Not attached";
  const expiryLabel =
    isShared && defaultCred
      ? `${defaultCred.expiresDisplay} · ${formatDaysLeft(defaultCred.daysLeft)}`
      : "—";

  const onSourceChange = (next: CredentialSource) => {
    setSource(next);
    // Handoff › derived rules: switching to personal with nothing attached
    // navigates to Claude Settings › Credentials and prompts an upload. There
    // is no personal-credential endpoint yet, so this is always the case.
    if (next === "personal") {
      close();
      navigate("/app/claude");
    }
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
