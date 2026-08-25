// Handoff › 6. Claude Settings › Credentials › "SHARED CLAUDE ACCOUNTS"
// — the admin section, wired to `PUT|DELETE /credentials/claude/shared`.
//
// The handoff drew a LIST of shared accounts with a `DEFAULT` chip and a
// `Set as default` action. The hub holds exactly one shared workspace
// credential (`api/app/services/claude_credentials.py` › `get_shared`), so
// this renders one card or the upload zone — and neither the chip nor the
// action survived. With one account there is nothing to be default *against*,
// and a menu item shipped permanently disabled is a control that lies about
// what the product can do. They come back with a second shared account.

import {
  ClaudeMark,
  Dropdown,
  Icon,
  Notice,
  Spinner,
  StatusPill,
} from "@/components/ui";
import {
  formatDaysLeft,
  formatExpiryIso,
  formatRefreshed,
  type ClaudeCredentialMeta,
} from "@/data";
import { cn } from "@/lib/cn";
import {
  FileUpload,
  Meta,
  ReadingToken,
  ScopeChips,
  StoredSecretRow,
} from "./parts";
import { metaStatusLabel, type ClaudeSettings } from "./state";

export function SharedAccounts({ s }: { s: ClaudeSettings }) {
  return (
    <>
      <div className="mt-1.5 flex items-center gap-3">
        <span className="text-[11px] font-bold tracking-[.12em] text-label">
          SHARED CLAUDE ACCOUNTS
        </span>
        <span className="h-px flex-1 bg-bd2" />
        <span className="rounded-pill bg-pt px-[9px] py-[3px] text-[9.5px] font-bold tracking-[.08em] text-ps-text">
          ADMIN
        </span>
      </div>

      {s.shared ? (
        <SharedCredentialCard meta={s.shared} s={s} />
      ) : (
        <FileUpload
          onFile={s.addShared}
          className="flex flex-col items-center gap-[9px] rounded-card border-[1.5px] border-dashed border-bd2 bg-transparent p-[26px] text-center hover:border-pb hover:bg-inset"
        >
          {s.uploadingShared ? (
            <ReadingToken />
          ) : (
            <>
              <span className="flex size-[42px] items-center justify-center rounded-button border border-pb bg-pt text-ps-text">
                <Icon name="plus" size={20} strokeWidth={2.4} />
              </span>
              <div className="text-[13.5px] font-bold text-txt">
                Add a shared Claude account
              </div>
              <div className="text-[12px] text-muted">
                Upload a{" "}
                <span className="font-mono text-[11px]">.credentials.json</span>{" "}
                exported from an authenticated Claude CLI
              </div>
            </>
          )}
        </FileUpload>
      )}

      <Notice tone="info">
        The workspace runs on a single shared account. Uploading replaces it for
        every member who has not attached their own.
      </Notice>
    </>
  );
}

function SharedCredentialCard({
  meta,
  s,
}: {
  meta: ClaudeCredentialMeta;
  s: ClaudeSettings;
}) {
  const status = metaStatusLabel(meta);
  // `Refreshes` is not a problem to escalate — the CLI renews it unprompted
  // (issue #63). Only a real lapse or an imminent one warrants the rotate banner.
  const needsRotation = status === "Expiring" || status === "Expired";
  const assigned = meta.assignedUsers ?? 0;

  return (
    <div
      data-surface
      className={cn(
        // Not <GlassCard/>: the border colour is derived, and `glass` sets the
        // border shorthand, which would out-specify a border-colour utility.
        "overflow-hidden rounded-panel border bg-card backdrop-blur-glass",
        needsRotation ? "border-warn/30" : "border-pb",
      )}
    >
      {needsRotation && (
        <div className="flex items-center gap-[9px] border-b border-warn/20 bg-warn-tint px-5 py-2.5 text-[12px] font-semibold text-warn">
          <span className="shrink-0">
            <Icon name="alert" size={14} strokeWidth={2.2} />
          </span>
          This token expires {formatDaysLeft(meta.daysLeft)} — rotate it to keep
          agent runs authenticated.
        </div>
      )}

      <div className="p-5">
        <div className="flex items-center gap-[13px]">
          <span className="flex size-[44px] shrink-0 items-center justify-center rounded-button-lg border border-claude/30 bg-claude-tint text-claude">
            <ClaudeMark size={22} />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-[9px]">
              <span className="truncate text-[15.5px] font-extrabold tracking-[-.02em] text-txt">
                {meta.label || "Shared Claude account"}
              </span>
            </div>
            <div className="mt-[3px] font-mono text-[11.5px] text-muted">
              {meta.subscriptionType ?? "Claude account"}
            </div>
          </div>

          <StatusPill status={status} />

          <Dropdown
            ddKey="cred-menu-shared"
            width={220}
            align="end"
            value={null}
            items={[
              {
                value: "remove" as const,
                label: "Remove credential",
                icon: <Icon name="trash" size={14} />,
                destructive: true,
              },
            ]}
            onSelect={(v) => {
              if (v === "remove") s.removeShared();
            }}
            trigger={({ ref, toggle }) => (
              <button
                ref={ref}
                type="button"
                data-surface
                onClick={toggle}
                aria-label="Shared credential actions"
                className="flex size-[30px] shrink-0 cursor-pointer items-center justify-center rounded-control border border-bd2 bg-card2 text-muted hover:bg-bd2"
              >
                <Icon
                  name="more"
                  size={16}
                  className="fill-current stroke-none"
                />
              </button>
            )}
          />
        </div>

        <div className="mt-[18px] grid grid-cols-4 gap-3">
          <Meta
            label="SUBSCRIPTION"
            value={meta.subscriptionType ?? "Claude account"}
          />
          <Meta
            label="EXPIRES"
            value={formatExpiryIso(meta.expiresAt)}
            sub={formatDaysLeft(meta.daysLeft)}
          />
          <Meta
            label="LAST REFRESHED"
            value={formatRefreshed(meta.lastRefreshed)}
          />
          <Meta
            label="ASSIGNED"
            value={`${assigned} ${assigned === 1 ? "member" : "members"}`}
          />
        </div>

        <div className="mt-4">
          <ScopeChips scopes={meta.scopes} />
        </div>

        <div className="mt-4">
          <StoredSecretRow />
        </div>

        <div className="mt-[15px] flex items-center gap-[9px] border-t border-bd3 pt-[14px]">
          <span className="shrink-0 text-faint">
            <Icon name="doc" size={12} />
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-faint">
            {meta.label || ".credentials.json"}
          </span>
          <FileUpload
            onFile={s.addShared}
            className="inline-flex items-center gap-2 rounded-control-lg border border-pb bg-pt px-[15px] py-[9px] text-[12.5px] font-bold text-ps-text hover:bg-bd"
          >
            {s.uploadingShared ? (
              <Spinner size={14} speed="run" />
            ) : (
              <Icon name="upload" size={14} />
            )}
            Rotate token
          </FileUpload>
        </div>
      </div>
    </div>
  );
}
