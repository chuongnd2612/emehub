// Functional port of Q-Agent's `ReposManager.tsx`. The handoff's Repository
// tab only ever DISPLAYS `project.config.repos` — there was no way to add,
// discover or remove one anywhere in EmeHub. This is the missing write path,
// requested explicitly to match Q-Agent's behaviour.
//
// Same two ways in, same "nothing persists until Save":
//   • Discover — GET /connections/{id}/repos through the project's bound
//     Repository Provider connection (adapter.list_repos()); each result is a
//     pill that adds a fully-populated row.
//   • Add manually — an empty row for a pasted clone URL, exactly as Q-Agent
//     allows for a repo no connection can see.
// One repo is `default`; picking a new default clears the others (the
// backend's `_normalize_repos` would auto-promote the first if none were
// flagged, but the UI shouldn't rely on a server-side tiebreak it doesn't
// show).

import { useEffect, useState } from "react";

import {
  Button,
  GlassCard,
  Icon,
  Input,
  Notice,
  Spinner,
  toast,
} from "@/components/ui";
import {
  discoverConnectionRepos,
  getConnectionsWithCapability,
  saveProjectConfig,
  type DiscoveredRepo,
  type Project,
  type ProjectRepo,
} from "@/data";
import { ApiError } from "@/lib/api";

const emptyRepo = (): ProjectRepo => ({
  name: "",
  repoUrl: "",
  defaultBranch: "",
  localRepoPath: "",
  default: false,
});

export function RepositoryEditor({
  project,
  onReload,
  onOpenSettings,
}: {
  project: Project;
  onReload: () => void;
  onOpenSettings: () => void;
}) {
  const config = project.config;
  const [repos, setRepos] = useState<ProjectRepo[]>(config?.repos ?? []);
  const [connectionLabel, setConnectionLabel] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredRepo[] | null>(null);
  const [discoverError, setDiscoverError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setRepos(config?.repos ?? []);
    setDiscovered(null);
    setDiscoverError("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, config]);

  const repositoryConnectionId = config?.repositoryConnectionId ?? null;

  useEffect(() => {
    let live = true;
    if (repositoryConnectionId === null) {
      setConnectionLabel(null);
      return;
    }
    void getConnectionsWithCapability("repository").then((options) => {
      if (!live) return;
      setConnectionLabel(
        options.find((o) => o.id === repositoryConnectionId)?.label ?? null,
      );
    });
    return () => {
      live = false;
    };
  }, [repositoryConnectionId]);

  const discover = async () => {
    if (repositoryConnectionId === null) return;
    setDiscovering(true);
    setDiscoverError("");
    try {
      const result = await discoverConnectionRepos(repositoryConnectionId);
      if (result.error) {
        setDiscoverError(result.error);
        setDiscovered([]);
      } else {
        setDiscovered(result.repos);
      }
    } catch (err) {
      setDiscoverError(
        err instanceof ApiError ? err.message : "The hub did not respond.",
      );
      setDiscovered([]);
    } finally {
      setDiscovering(false);
    }
  };

  const addDiscovered = (repo: DiscoveredRepo) => {
    if (repos.some((r) => r.name === repo.name)) return;
    setRepos((rows) => [
      ...rows,
      {
        name: repo.name,
        repoUrl: repo.cloneUrl,
        defaultBranch: repo.defaultBranch,
        localRepoPath: "",
        default: rows.length === 0,
      },
    ]);
  };

  const setDefault = (index: number) =>
    setRepos((rows) => rows.map((r, i) => ({ ...r, default: i === index })));

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await saveProjectConfig(project.id, {
        repos: repos.filter((r) => r.name.trim() || r.repoUrl.trim()),
      });
      toast("Repositories saved", "Every agent clones from this list", "ok");
      onReload();
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
    <GlassCard className="rounded-[20px] p-[22px]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[15px] font-extrabold tracking-[-.01em]">
            Configured repositories
          </div>
          <div className="mt-1 text-[12.5px] text-muted">
            Every agent clones from this list. The hub stores the address,
            never a checkout.
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            disabled={repositoryConnectionId === null || discovering}
            icon={
              discovering ? (
                <Spinner size={14} speed="run" />
              ) : (
                <Icon name="search" size={14} strokeWidth={2.3} />
              )
            }
            title={
              repositoryConnectionId === null
                ? "Bind a Repository Provider connection first"
                : undefined
            }
            onClick={() => void discover()}
          >
            {connectionLabel
              ? `Discover from ${connectionLabel}`
              : "Discover from connection"}
          </Button>
          <Button
            variant="dashed"
            icon={<Icon name="plus" size={14} strokeWidth={2.4} />}
            onClick={() => setRepos((rows) => [...rows, emptyRepo()])}
          >
            Add manually
          </Button>
        </div>
      </div>

      {/* Q-Agent disables Discover the same way — until a Repository
          Provider connection is bound, there is nothing to discover from.
          A disabled button with only a hover title is easy to miss, so the
          reason and the fix are also spelled out inline. */}
      {repositoryConnectionId === null && (
        <Notice tone="info" className="mt-3">
          <span className="flex flex-wrap items-center gap-x-1">
            Discover is disabled until a Repository Provider connection is
            bound.
            <button
              type="button"
              data-surface
              onClick={onOpenSettings}
              className="cursor-pointer font-bold text-ps-text underline decoration-dotted underline-offset-2"
            >
              Bind one in Settings →
            </button>
          </span>
        </Notice>
      )}

      {discoverError && (
        <Notice tone="warn" className="mt-3">
          {discoverError}
        </Notice>
      )}

      {discovered && discovered.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {discovered
            .filter((d) => !repos.some((r) => r.name === d.name))
            .map((d) => (
              <button
                key={d.name}
                type="button"
                data-surface
                onClick={() => addDiscovered(d)}
                className="rounded-pill border border-dashed border-bd2 bg-inset px-3 py-[6px] font-mono text-[11.5px] font-semibold text-ps-text transition-colors duration-200 hover:border-pb"
              >
                + {d.name}
              </button>
            ))}
        </div>
      )}

      {repos.length === 0 ? (
        <div className="mt-4 rounded-card border border-dashed border-bd2 bg-inset px-4 py-6 text-center text-[12.5px] text-muted">
          No repository connected. Discover one from the bound connection, or
          add a clone URL manually.
        </div>
      ) : (
        <div className="mt-4 flex flex-col gap-2">
          {repos.map((repo, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <div key={i} className="flex items-start gap-2">
              <button
                type="button"
                data-surface
                aria-label={repo.default ? "Default repository" : "Set as default"}
                title={repo.default ? "Default repository" : "Set as default"}
                onClick={() => setDefault(i)}
                className={`mt-[3px] flex size-8 shrink-0 items-center justify-center rounded-control border transition-colors duration-200 ${
                  repo.default
                    ? "border-pb bg-pt text-ps-text"
                    : "border-bd2 text-faint hover:border-pb"
                }`}
              >
                <Icon
                  name="check"
                  size={14}
                  strokeWidth={2.4}
                />
              </button>
              <div className="grid min-w-0 flex-1 grid-cols-3 gap-2">
                <Input
                  placeholder="Name"
                  mono
                  value={repo.name}
                  onChange={(e) =>
                    setRepos((rows) =>
                      rows.map((r, j) =>
                        j === i ? { ...r, name: e.target.value } : r,
                      ),
                    )
                  }
                />
                <Input
                  placeholder="Clone URL"
                  mono
                  value={repo.repoUrl}
                  onChange={(e) =>
                    setRepos((rows) =>
                      rows.map((r, j) =>
                        j === i ? { ...r, repoUrl: e.target.value } : r,
                      ),
                    )
                  }
                />
                <Input
                  placeholder="Local path (agent host, optional)"
                  mono
                  value={repo.localRepoPath}
                  onChange={(e) =>
                    setRepos((rows) =>
                      rows.map((r, j) =>
                        j === i ? { ...r, localRepoPath: e.target.value } : r,
                      ),
                    )
                  }
                />
              </div>
              <button
                type="button"
                data-surface
                aria-label="Remove"
                onClick={() => setRepos((rows) => rows.filter((_, j) => j !== i))}
                className="mt-[3px] flex size-8 shrink-0 items-center justify-center rounded-control border border-bd2 text-faint transition-colors duration-200 hover:border-danger hover:text-danger"
              >
                <Icon name="trash" size={13} strokeWidth={2.2} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 text-[11.5px] text-faint">
        No local path? Agents clone into their own workspace, keyed by project
        and repository name.
      </div>

      {error && (
        <Notice tone="danger" className="mt-3">
          {error}
        </Notice>
      )}

      <div className="mt-4 flex justify-end">
        <Button
          variant="primary"
          disabled={saving}
          icon={saving ? <Spinner size={14} speed="run" /> : undefined}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save repositories"}
        </Button>
      </div>
    </GlassCard>
  );
}
