// Handoff › 6. Claude Settings › Credentials › "SHARED CLAUDE ACCOUNTS"
// — the admin section: one card per shared credential plus the dashed
// "Add a shared Claude account" upload zone.

import { ClaudeMark, Dropdown, Icon, StatusPill } from "@/components/ui";
import { formatDaysLeft, maskToken, type SharedCredential } from "@/data";
import { cn } from "@/lib/cn";
import {
  FileUpload,
  Meta,
  ReadingToken,
  ScopeChips,
  TokenRow,
} from "./parts";
import { statusLabel, type ClaudeSettings } from "./state";

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

      {s.shared.map((cred) => (
        <SharedCredentialCard key={cred.id} cred={cred} s={s} />
      ))}

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
    </>
  );
}

function SharedCredentialCard({
  cred,
  s,
}: {
  cred: SharedCredential;
  s: ClaudeSettings;
}) {
  const status = statusLabel(cred.daysLeft);
  const needsRotation = status !== "Active";
  const revealed = !!s.revealed[cred.id];

  return (
    <div
      data-surface
      className={cn(
        // Not <GlassCard/>: the border colour is derived, and `glass` sets the
        // border shorthand, which would out-specify a border-colour utility.
        "overflow-hidden rounded-panel border bg-card backdrop-blur-glass",
        cred.isDefault
          ? "border-pb"
          : needsRotation
            ? "border-warn/30"
            : "border-bd",
      )}
    >
      {needsRotation && (
        <div className="flex items-center gap-[9px] border-b border-warn/20 bg-warn-tint px-5 py-2.5 text-[12px] font-semibold text-warn">
          <span className="shrink-0">
            <Icon name="alert" size={14} strokeWidth={2.2} />
          </span>
          This token expires {formatDaysLeft(cred.daysLeft)} — rotate it to keep
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
                {cred.label}
              </span>
              {cred.isDefault && (
                <span className="shrink-0 rounded-pill bg-pt px-2 py-[3px] text-[9px] font-bold tracking-[.09em] text-ps-text">
                  DEFAULT
                </span>
              )}
            </div>
            <div className="mt-[3px] font-mono text-[11.5px] text-muted">
              {cred.email}
            </div>
          </div>

          <StatusPill status={status} />

          <Dropdown
            ddKey={`cred-menu-${cred.id}`}
            width={196}
            align="end"
            value={null}
            items={[
              ...(cred.isDefault
                ? []
                : [
                    {
                      value: "default" as const,
                      label: "Set as default",
                      icon: <Icon name="spark" size={14} />,
                    },
                  ]),
              {
                value: "remove" as const,
                label: "Remove credential",
                icon: <Icon name="trash" size={14} />,
                destructive: true,
              },
            ]}
            onSelect={(v) =>
              v === "default" ? s.makeDefault(cred.id) : s.removeShared(cred.id)
            }
            trigger={({ ref, toggle }) => (
              <button
                ref={ref}
                type="button"
                data-surface
                onClick={toggle}
                aria-label={`Credential actions for ${cred.label}`}
                className="flex size-[30px] shrink-0 cursor-pointer items-center justify-center rounded-control border border-bd2 bg-card2 text-muted hover:bg-bd2"
              >
                <Icon name="more" size={16} className="fill-current stroke-none" />
              </button>
            )}
          />
        </div>

        <div className="mt-[18px] grid grid-cols-4 gap-3">
          <Meta label="SUBSCRIPTION" value={cred.subscription} />
          <Meta
            label="EXPIRES"
            value={cred.expiresDisplay}
            sub={formatDaysLeft(cred.daysLeft)}
          />
          <Meta label="LAST REFRESHED" value={cred.lastRefreshed} />
          <Meta
            label="ASSIGNED"
            value={`${cred.members} ${cred.members === 1 ? "member" : "members"}`}
          />
        </div>

        <div className="mt-4">
          <ScopeChips scopes={cred.scopes} />
        </div>

        <div className="mt-4">
          <TokenRow
            revealed={revealed}
            onToggle={() => s.toggleReveal(cred.id)}
            value={revealed ? cred.token : maskToken(cred.token)}
          />
        </div>

        <div className="mt-[15px] flex items-center gap-[9px] border-t border-bd3 pt-[14px]">
          <span className="shrink-0 text-faint">
            <Icon name="doc" size={12} />
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-faint">
            {cred.source}
          </span>
          <FileUpload
            onFile={(file) => s.rotateShared(cred.id, file)}
            className="inline-flex items-center gap-2 rounded-control-lg border border-pb bg-pt px-[15px] py-[9px] text-[12.5px] font-bold text-ps-text hover:bg-bd"
          >
            <Icon name="upload" size={14} />
            Rotate token
          </FileUpload>
        </div>
      </div>
    </div>
  );
}
