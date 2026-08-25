// Functional port of Q-Agent's `ProjectSettingsForm.tsx` — the piece of that
// screen the EmeHub design handoff never drew (the handoff's Settings tab is
// knowledge-policy toggles + a read-only meta grid; Q-Agent's actual settings
// screen is connection bindings, a base URL, environments and test accounts).
// Requested explicitly: EmeHub's project configuration should DO what
// Q-Agent's does, not just look like the mockup.
//
// Same shape as Q-Agent's form: everything here is local state, and NOTHING
// persists until "Save changes" — no autosave, no per-field PATCH. One
// `PUT /projects/{key}/config` sends the whole patch (`data/projects.ts ›
// saveProjectConfig`).
//
// ## One draft, diffed against what is saved (#200)
//
// The fields used to be six separate `useState`s with no dirty tracking at all:
// Save was enabled with zero changes, and there was no way to tell a touched
// form from a changed one. They are now ONE draft object diffed per key against
// a `saved` baseline, which gives a true "no net change" test — revert a field
// by hand and the count drops back to zero and the save bar hides itself again.
// That is the same idiom the Settings screen used before its draft fields were
// removed (#191), and `SaveBar` is the shared affordance for it.
//
// ## Why the reset effect keys on a serialized value, not on `config`
//
// The parent no longer blanks the screen while it refetches after a save, so
// this form now stays MOUNTED across a refetch — which is the point, and also
// the hazard. `ProjectDetail` builds a brand-new `project` on every load and
// `toConfig()` rebuilds the nested config with it, so the `config` object's
// identity changes even when the server returned exactly what we already had.
// An effect keyed on that identity would wipe a draft the user is still typing
// into, every time anything else on the screen asked for a refresh. Keying on
// the SERIALIZED draft-shaped value means an identical answer is a no-op.
//
// The save path does not rely on that alone: `PUT /projects/{key}/config`
// returns the whole saved config, so the new baseline is seated from the
// response the moment the request resolves. By the time the parent's silent
// refetch lands, the key already matches and the effect has nothing to do.
//
// Not ported, because it isn't the hub's job: Q-Agent's "Manual Login" capture
// drives a real (headed) browser on the machine running the request. The hub
// does no domain work and owns no workspace filesystem (ROADMAP Phase 4) — a
// "Capture login" button here would have nothing to drive. `manualAuth` is
// still a real, saved column, so the intent is exposed as a plain toggle with
// a note saying the capture itself happens on whichever agent runs the project.

import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Dropdown,
  GlassCard,
  Icon,
  Input,
  Notice,
  SaveBar,
  Toggle,
  toast,
} from "@/components/ui";
import {
  getConnectionsWithCapability,
  saveProjectConfig,
  type Project,
  type ProjectConfig,
  type ProjectConfigPatch,
  type ProjectEnvironment,
  type ProjectTestAccount,
} from "@/data";
import { ApiError } from "@/lib/api";

interface ConnectionOption {
  id: number;
  label: string;
}

/** A test-account row being edited. `password` is local-only until saved. */
interface EditableAccount extends ProjectTestAccount {
  password: string;
}

const toEditableAccount = (a: ProjectTestAccount): EditableAccount => ({
  ...a,
  password: "",
});

const emptyAccount = (): EditableAccount => ({
  role: "",
  username: "",
  notes: "",
  hasPassword: false,
  password: "",
});

const emptyEnvironment = (): ProjectEnvironment => ({
  name: "",
  baseUrl: "",
  notes: "",
});

/**
 * Everything this form edits, in one object. A single draft rather than six
 * `useState`s so there is something to diff a saved baseline against — with the
 * fields apart there was no answer to "has anything actually changed?".
 */
interface ConfigDraft {
  workItemConnectionId: number | null;
  repositoryConnectionId: number | null;
  baseUrl: string;
  manualAuth: boolean;
  environments: ProjectEnvironment[];
  accounts: EditableAccount[];
}

const DRAFT_KEYS = [
  "workItemConnectionId",
  "repositoryConnectionId",
  "baseUrl",
  "manualAuth",
  "environments",
  "accounts",
] as const;

/** The saved config, in draft shape. Deterministic — same config, same result. */
const draftFrom = (config: ProjectConfig | null | undefined): ConfigDraft => ({
  workItemConnectionId: config?.workItemConnectionId ?? null,
  repositoryConnectionId: config?.repositoryConnectionId ?? null,
  baseUrl: config?.baseUrl ?? "",
  manualAuth: config?.manualAuth ?? false,
  environments: config?.environments ?? [],
  accounts: (config?.testAccounts ?? []).map(toEditableAccount),
});

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
      {children}
    </span>
  );
}

function RemoveRowButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      data-surface
      aria-label="Remove"
      onClick={onClick}
      className="flex size-8 shrink-0 items-center justify-center rounded-control border border-bd2 text-faint transition-colors duration-200 hover:border-danger hover:text-danger"
    >
      <Icon name="trash" size={13} strokeWidth={2.2} />
    </button>
  );
}

export function ProjectConfigForm({
  project,
  onSaved,
}: {
  project: Project;
  onSaved: () => void;
}) {
  const config = project.config;

  const incoming = useMemo(() => draftFrom(config), [config]);
  /** What the hub has. The thing `draft` is measured against. */
  const [saved, setSaved] = useState<ConfigDraft>(incoming);
  const [draft, setDraft] = useState<ConfigDraft>(incoming);

  const [workItemOptions, setWorkItemOptions] = useState<ConnectionOption[]>([]);
  const [repoOptions, setRepoOptions] = useState<ConnectionOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const patch = (next: Partial<ConfigDraft>) =>
    setDraft((d) => ({ ...d, ...next }));

  const setAccounts = (
    update: (rows: EditableAccount[]) => EditableAccount[],
  ) => setDraft((d) => ({ ...d, accounts: update(d.accounts) }));

  const setEnvironments = (
    update: (rows: ProjectEnvironment[]) => ProjectEnvironment[],
  ) => setDraft((d) => ({ ...d, environments: update(d.environments) }));

  /**
   * A genuinely different saved config adopts itself into the form — a new
   * project, or a value that really did change on the hub.
   *
   * The dependency is the SERIALIZED value, not the `config` object: the parent
   * hands us a fresh object on every refetch, and this form now survives those
   * refetches instead of being unmounted by a full-screen loading state. Keying
   * on identity would clobber whatever the user is typing each time anything
   * else on the screen refreshed. See the note at the top of this file.
   */
  const incomingKey = JSON.stringify(incoming);
  useEffect(() => {
    setSaved(incoming);
    setDraft(incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, incomingKey]);

  /**
   * How many fields differ from what is saved.
   *
   * A per-key compare rather than one whole-object boolean because the save bar
   * shows the number, and "3 unsaved changes" is more useful than "unsaved
   * changes". Serialized because four of the six are objects or arrays; it is a
   * handful of small values, recomputed on a keystroke the browser is already
   * re-rendering for.
   */
  const dirtyCount = useMemo(
    () =>
      DRAFT_KEYS.filter(
        (key) => JSON.stringify(draft[key]) !== JSON.stringify(saved[key]),
      ).length,
    [draft, saved],
  );

  useEffect(() => {
    let live = true;
    void Promise.all([
      getConnectionsWithCapability("work_item"),
      getConnectionsWithCapability("repository"),
    ]).then(([workItem, repo]) => {
      if (!live) return;
      setWorkItemOptions(workItem);
      setRepoOptions(repo);
    });
    return () => {
      live = false;
    };
  }, []);

  const optionsFor = (options: ConnectionOption[]) =>
    options.map((o) => ({ value: String(o.id), label: o.label }));

  const save = async () => {
    setSaving(true);
    setError("");
    const body: ProjectConfigPatch = {
      workItemConnectionId: draft.workItemConnectionId,
      repositoryConnectionId: draft.repositoryConnectionId,
      baseUrl: draft.baseUrl.trim(),
      manualAuth: draft.manualAuth,
      environments: draft.environments.filter(
        (e) => e.name.trim() || e.baseUrl.trim(),
      ),
      testAccounts: draft.accounts
        .filter((a) => a.role.trim() || a.username.trim())
        .map((a) => ({
          role: a.role,
          username: a.username,
          // A blank password preserves whatever the hub already has stored —
          // never send the masked placeholder back as if it were real.
          password: a.password,
          notes: a.notes,
        })),
    };
    try {
      // The PUT answers with the whole saved config, so the new baseline comes
      // from the hub rather than from what we hoped it accepted — the bar goes
      // away because the server agrees, not because we asked it to.
      const stored = await saveProjectConfig(project.id, body);
      const next = draftFrom(stored);
      setSaved(next);
      setDraft(next);
      toast("Configuration saved");
      onSaved();
    } catch (err) {
      // Both, and deliberately. The toast is the thing a user reading the save
      // bar will actually notice; the notice is the detail that has to stay on
      // screen while they decide what to do about it. Neither clears the draft
      // or advances `saved`, so the bar keeps its count and Save is one click
      // away from a retry.
      const message =
        err instanceof ApiError
          ? err.message
          : "The hub did not respond. Try again in a moment.";
      setError(message);
      toast("Could not save the configuration", "warn", message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-[14px]">
      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em]">
          Provider connections
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          Which connection supplies this project's tickets, and which supplies
          its repositories.
        </div>

        <div className="mt-4 grid grid-cols-2 gap-[14px]">
          <div className="flex flex-col gap-[7px]">
            <SectionLabel>WORK ITEM PROVIDER</SectionLabel>
            <Dropdown
              ddKey="settings-work-item-connection"
              width={280}
              value={
                draft.workItemConnectionId !== null
                  ? String(draft.workItemConnectionId)
                  : null
              }
              onSelect={(v) => patch({ workItemConnectionId: Number(v) })}
              items={optionsFor(workItemOptions)}
              trigger={({ ref, toggle }) => (
                <button
                  ref={ref}
                  type="button"
                  data-surface
                  onClick={toggle}
                  className="flex h-9 w-full items-center justify-between gap-2 rounded-control-lg border border-bd2 bg-card2 px-3 text-left text-[12.5px] font-semibold text-txt2 transition-colors duration-200"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {workItemOptions.find(
                      (o) => o.id === draft.workItemConnectionId,
                    )?.label ??
                      (workItemOptions.length
                        ? "Select connection"
                        : "No work item connections")}
                  </span>
                  <Icon
                    name="chevronDown"
                    size={14}
                    strokeWidth={2.3}
                    className="shrink-0 text-faint"
                  />
                </button>
              )}
            />
          </div>

          <div className="flex flex-col gap-[7px]">
            <SectionLabel>REPOSITORY PROVIDER</SectionLabel>
            <Dropdown
              ddKey="settings-repo-connection"
              width={280}
              value={
                draft.repositoryConnectionId !== null
                  ? String(draft.repositoryConnectionId)
                  : null
              }
              onSelect={(v) => patch({ repositoryConnectionId: Number(v) })}
              items={optionsFor(repoOptions)}
              trigger={({ ref, toggle }) => (
                <button
                  ref={ref}
                  type="button"
                  data-surface
                  onClick={toggle}
                  className="flex h-9 w-full items-center justify-between gap-2 rounded-control-lg border border-bd2 bg-card2 px-3 text-left text-[12.5px] font-semibold text-txt2 transition-colors duration-200"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {repoOptions.find(
                      (o) => o.id === draft.repositoryConnectionId,
                    )?.label ??
                      (repoOptions.length
                        ? "Select connection"
                        : "No repository connections")}
                  </span>
                  <Icon
                    name="chevronDown"
                    size={14}
                    strokeWidth={2.3}
                    className="shrink-0 text-faint"
                  />
                </button>
              )}
            />
          </div>
        </div>
      </GlassCard>

      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em]">
          Application
        </div>
        <div className="mt-4">
          <Input
            label="BASE URL"
            placeholder="https://staging.example.com"
            value={draft.baseUrl}
            onChange={(e) => patch({ baseUrl: e.target.value })}
          />
        </div>

        <div className="mt-4 border-t border-bd3 pt-4">
          <Toggle
            checked={draft.manualAuth}
            onChange={(manualAuth) => patch({ manualAuth })}
            label="Manual login required"
            description="The agent running this project captures a real browser session before it works, instead of using a saved token. Capturing itself happens on the agent — the hub only records the intent."
          />
        </div>
      </GlassCard>

      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[15px] font-extrabold tracking-[-.01em]">
              Test accounts
            </div>
            <div className="mt-1 text-[12.5px] text-muted">
              Encrypted at rest, returned only to you.
            </div>
          </div>
          <Button
            variant="dashed"
            icon={<Icon name="plus" size={14} strokeWidth={2.4} />}
            onClick={() => setAccounts((rows) => [...rows, emptyAccount()])}
          >
            Add account
          </Button>
        </div>

        {draft.accounts.length > 0 && (
          <div className="mt-4 flex flex-col gap-[10px]">
            {draft.accounts.map((account, i) => (
              // eslint-disable-next-line react/no-array-index-key
              <div key={i} className="flex items-start gap-2">
                <div className="grid min-w-0 flex-1 grid-cols-4 gap-2">
                  <Input
                    placeholder="Role"
                    value={account.role}
                    onChange={(e) =>
                      setAccounts((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, role: e.target.value } : r,
                        ),
                      )
                    }
                  />
                  <Input
                    placeholder="Username"
                    value={account.username}
                    onChange={(e) =>
                      setAccounts((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, username: e.target.value } : r,
                        ),
                      )
                    }
                  />
                  <Input
                    type="password"
                    placeholder={account.hasPassword ? "Unchanged" : "Password"}
                    value={account.password}
                    onChange={(e) =>
                      setAccounts((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, password: e.target.value } : r,
                        ),
                      )
                    }
                  />
                  <Input
                    placeholder="Notes"
                    value={account.notes}
                    onChange={(e) =>
                      setAccounts((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, notes: e.target.value } : r,
                        ),
                      )
                    }
                  />
                </div>
                <RemoveRowButton
                  onClick={() =>
                    setAccounts((rows) => rows.filter((_, j) => j !== i))
                  }
                />
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard className="rounded-[20px] p-[22px]">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[15px] font-extrabold tracking-[-.01em]">
            Environments
          </div>
          <Button
            variant="dashed"
            icon={<Icon name="plus" size={14} strokeWidth={2.4} />}
            onClick={() => setEnvironments((rows) => [...rows, emptyEnvironment()])}
          >
            Add environment
          </Button>
        </div>

        {draft.environments.length > 0 && (
          <div className="mt-4 flex flex-col gap-[10px]">
            {draft.environments.map((env, i) => (
              // eslint-disable-next-line react/no-array-index-key
              <div key={i} className="flex items-start gap-2">
                <div className="grid min-w-0 flex-1 grid-cols-3 gap-2">
                  <Input
                    placeholder="Name"
                    value={env.name}
                    onChange={(e) =>
                      setEnvironments((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, name: e.target.value } : r,
                        ),
                      )
                    }
                  />
                  <Input
                    placeholder="https://…"
                    mono
                    value={env.baseUrl}
                    onChange={(e) =>
                      setEnvironments((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, baseUrl: e.target.value } : r,
                        ),
                      )
                    }
                  />
                  <Input
                    placeholder="Notes"
                    value={env.notes}
                    onChange={(e) =>
                      setEnvironments((rows) =>
                        rows.map((r, j) =>
                          j === i ? { ...r, notes: e.target.value } : r,
                        ),
                      )
                    }
                  />
                </div>
                <RemoveRowButton
                  onClick={() =>
                    setEnvironments((rows) => rows.filter((_, j) => j !== i))
                  }
                />
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {error && <Notice tone="danger">{error}</Notice>}

      {/* Room so the fixed save bar cannot cover the last control — sized to
          clear the bar itself plus its bottom padding, as on Settings. */}
      <div className="h-24 shrink-0" aria-hidden />

      <SaveBar
        count={dirtyCount}
        saving={saving}
        onDiscard={() => setDraft(saved)}
        onSave={() => void save()}
      />
    </div>
  );
}
