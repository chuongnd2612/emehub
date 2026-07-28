// Handoff › Overlays › Modals — "New API key … 520px, var(--pop), radius 20,
// animation:fadeInUp .25s". Fields and copy are the prototype's, verbatim
// (the prototype titles it "Create API key").
//
// SECURITY (CLAUDE.md › "Never log or return a secret"): nothing here holds a
// key. The prototype only toasts; the real POST /api/auth/api-keys will return
// the secret exactly once, which is what the amber note warns about.

import { useEffect, useState } from "react";
import { Button, Icon, Input, Modal, toast } from "@/components/ui";

export interface NewApiKeyModalProps {
  open: boolean;
  onClose: () => void;
}

export function NewApiKeyModal({ open, onClose }: NewApiKeyModalProps) {
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (open) setLabel("");
  }, [open]);

  const create = () => {
    onClose();
    toast("API key created", "Copy it now — it will not be shown again", "ok");
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create API key"
      subtitle="Machine access for pipelines and agent runners."
      footer={
        <>
          <Button variant="primary" className="flex-1" onClick={create}>
            Create key
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <Input
        label="LABEL"
        placeholder="e.g. Nightly regression runner"
        autoFocus
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />

      <div className="flex items-start gap-[10px] rounded-button border border-warn/25 bg-warn-tint px-[15px] py-[13px]">
        <span className="mt-[1px] flex shrink-0 text-warn">
          <Icon name="alert" size={15} strokeWidth={2.2} />
        </span>
        <span className="text-[12px] leading-[1.5] text-warn">
          The key is shown once. Store it in your secret manager before closing
          this dialog.
        </span>
      </div>
    </Modal>
  );
}
