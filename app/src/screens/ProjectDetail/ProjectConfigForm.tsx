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
// Not ported, because it isn't the hub's job: Q-Agent's "Manual Login" capture
// drives a real (headed) browser on the machine running the request. The hub
// does no domain work and owns no workspace filesystem (ROADMAP Phase 4) — a
// "Capture login" button here would have nothing to drive. `manualAuth` is
// still a real, saved column, so the intent is exposed as a plain toggle with
// a note saying the capture itself happens on whichever agent runs the project.

import { useEffect, useState } from "react";

import {
  Button,
  Dropdown,
  GlassCard,
  Icon,
  Input,
  Notice,
  Spinner,
  Toggle,
  toast,
} from "@/components/ui";
import {
  getConnectionsWithCapability,
  saveProjectConfig,
  type Project,
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

  const [workItemConnectionId, setWorkItemConnectionId] = useState<number | null>(
    config?.workItemConnectionId ?? null,
  );
  const [repositoryConnectionId, setRepositoryConnectionId] = useState<
    number | null
  >(config?.repositoryConnectionId ?? null);
  const [baseUrl, setBaseUrl] = useState(config?.baseUrl ?? "");
  const [manualAuth, setManualAuth] = useState(config?.manualAuth ?? false);
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>(
    config?.environments ?? [],
  );
  const [accounts, setAccounts] = useState<EditableAccount[]>(
    (config?.testAccounts ?? []).map(toEditableAccount),
  );

  const [workItemOptions, setWorkItemOptions] = useState<ConnectionOption[]>([]);
  const [repoOptions, setRepoOptions] = useState<ConnectionOption[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // A fresh `project` prop (after a Reload) resets every field — otherwise an
  // unsaved edit would look adopted just because the parent re-fetched.
  useEffect(() => {
    setWorkItemConnectionId(config?.workItemConnectionId ?? null);
    setRepositoryConnectionId(config?.repositoryConnectionId ?? null);
    setBaseUrl(config?.baseUrl ?? "");
    setManualAuth(config?.manualAuth ?? false);
    setEnvironments(config?.environments ?? []);
    setAccounts((config?.testAccounts ?? []).map(toEditableAccount));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, config]);

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
    const patch: ProjectConfigPatch = {
      workItemConnectionId,
      repositoryConnectionId,
      baseUrl: baseUrl.trim(),
      manualAuth,
      environments: environments.filter((e) => e.name.trim() || e.baseUrl.trim()),
      testAccounts: accounts
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
      await saveProjectConfig(project.id, patch);
      toast("Configuration saved");
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "The hub did not respond. Try again in a moment.",
      );
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
                workItemConnectionId !== null ? String(workItemConnectionId) : null
              }
              onSelect={(v) => setWorkItemConnectionId(Number(v))}
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
                    {workItemOptions.find((o) => o.id === workItemConnectionId)
                      ?.label ??
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
                repositoryConnectionId !== null
                  ? String(repositoryConnectionId)
                  : null
              }
              onSelect={(v) => setRepositoryConnectionId(Number(v))}
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
                    {repoOptions.find((o) => o.id === repositoryConnectionId)
                      ?.label ??
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
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>

        <div className="mt-4 border-t border-bd3 pt-4">
          <Toggle
            checked={manualAuth}
            onChange={setManualAuth}
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

        {accounts.length > 0 && (
          <div className="mt-4 flex flex-col gap-[10px]">
            {accounts.map((account, i) => (
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

        {environments.length > 0 && (
          <div className="mt-4 flex flex-col gap-[10px]">
            {environments.map((env, i) => (
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

      <div className="flex justify-end">
        <Button
          variant="primary"
          disabled={saving}
          icon={saving ? <Spinner size={14} speed="run" /> : undefined}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
