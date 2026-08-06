// Handoff › Overlays › Modals — "New project … 520px, var(--pop), radius 20,
// animation:fadeInUp .25s". Copy is the prototype's.
//
// Opened from three places (Overview quick action, the Projects header button
// and the dashed "Connect a repository" tile), so it is mounted globally by
// `ModalHost` rather than by any one screen.
//
// LIVE: `POST /projects` (`data/projects.ts › createProject`). The endpoint
// requires a `key` — it is the path parameter every later project call is built
// from — so the modal shows one, slugged from the name and editable, rather
// than inventing it behind the user's back. A failure keeps the dialog open
// with the hub's own message; it never closes on a toast that did not happen.

import { useEffect, useState } from "react";
import { createProject, projectKeyFrom } from "@/data";
import { Button, Icon, Input, Notice, Modal, Spinner, toast } from "@/components/ui";
import { ApiError } from "@/lib/api";

export interface NewProjectModalProps {
  open: boolean;
  onClose: () => void;
}

export function NewProjectModal({ open, onClose }: NewProjectModalProps) {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  /** True once the key has been edited by hand — stop following the name. */
  const [keyEdited, setKeyEdited] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Every visit starts empty.
  useEffect(() => {
    if (!open) return;
    setName("");
    setKey("");
    setKeyEdited(false);
    setSaving(false);
    setError("");
  }, [open]);

  const changeName = (value: string) => {
    setName(value);
    if (!keyEdited) setKey(projectKeyFrom(value));
  };

  const resolvedKey = keyEdited ? projectKeyFrom(key) : key;

  const create = async () => {
    if (!resolvedKey) {
      setError("A project key is required — it is what every agent asks for.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const project = await createProject({ key: resolvedKey, name: name.trim() });
      onClose();
      toast(`${project.name} created`);
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
    <Modal
      open={open}
      onClose={onClose}
      title="New project"
      subtitle="Give it a name — you can connect the repository right after."
      footer={
        <>
          <Button
            variant="primary"
            className="flex-1"
            disabled={saving}
            icon={saving ? <Spinner size={14} speed="run" /> : undefined}
            onClick={() => void create()}
          >
            {saving ? "Creating…" : "Create project"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <Input
        label="PROJECT NAME"
        placeholder="e.g. Atlas Reporting"
        autoFocus
        value={name}
        onChange={(e) => changeName(e.target.value)}
      />

      <Input
        label="PROJECT KEY"
        placeholder="atlas-reporting"
        mono
        value={resolvedKey}
        onChange={(e) => {
          setKeyEdited(true);
          setKey(e.target.value);
        }}
      />

      <div className="flex flex-col gap-[7px]">
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          REPOSITORY
        </span>
        <div className="flex items-center gap-[10px] rounded-control-lg border border-dashed border-bd2 bg-inset px-[14px] py-3">
          <span className="flex text-muted">
            <Icon name="git" size={15} strokeWidth={2.2} />
          </span>
          <span className="flex-1 text-[12.5px] text-muted">
            Connect after creation
          </span>
        </div>
      </div>

      {error && <Notice tone="danger">{error}</Notice>}
    </Modal>
  );
}
