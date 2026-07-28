// Handoff › Overlays › Modals — "New project … 520px, var(--pop), radius 20,
// animation:fadeInUp .25s". Fields and copy are the prototype's, verbatim.
//
// Opened from three places (Overview quick action, the Projects header button
// and the dashed "Connect a repository" tile), so it is mounted globally by
// `ModalHost` rather than by any one screen.
//
// STUB: the prototype does not persist a new project and the handoff's *Data
// fetching* list has no create-project endpoint, so this toasts and closes.

import { useEffect, useState } from "react";
import { Button, Icon, Input, Modal, toast } from "@/components/ui";

export interface NewProjectModalProps {
  open: boolean;
  onClose: () => void;
}

export function NewProjectModal({ open, onClose }: NewProjectModalProps) {
  const [name, setName] = useState("");

  // Every visit starts empty.
  useEffect(() => {
    if (open) setName("");
  }, [open]);

  const create = () => {
    const label = name.trim() || "Untitled project";
    onClose();
    toast(
      "Project created",
      `${label} is ready — connect a repository next`,
      "ok",
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New project"
      subtitle="Give it a name — you can connect the repository right after."
      footer={
        <>
          <Button variant="primary" className="flex-1" onClick={create}>
            Create project
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
        onChange={(e) => setName(e.target.value)}
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
    </Modal>
  );
}
