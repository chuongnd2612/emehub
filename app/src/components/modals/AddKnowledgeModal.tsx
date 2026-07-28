// Handoff › Overlays › Modals — "Add knowledge … 520px, var(--pop), radius 20,
// animation:fadeInUp .25s". Fields and copy are the prototype's, verbatim.
//
// Opened from the Overview quick action and from "Add source" on a project's
// knowledge tab, so it is mounted globally by `ModalHost`.
//
// STUB: the prototype only toasts ("Queued for indexing") — the handoff's *Data
// fetching* list has a build/re-index endpoint but none for adding a single
// source, so nothing is posted here.

import { useEffect, useState } from "react";
import { Button, Icon, Input, Modal, toast } from "@/components/ui";
import type { KnowledgeSourceType } from "@/data";
import { cn } from "@/lib/cn";

/** Handoff § 3 › Project knowledge — the source type chips. */
const SOURCE_TYPES: KnowledgeSourceType[] = [
  "Markdown",
  "Document",
  "URL",
  "File",
];

export interface AddKnowledgeModalProps {
  open: boolean;
  onClose: () => void;
}

export function AddKnowledgeModal({ open, onClose }: AddKnowledgeModalProps) {
  const [type, setType] = useState<KnowledgeSourceType>("Markdown");
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (!open) return;
    setType("Markdown");
    setTitle("");
  }, [open]);

  const add = () => {
    const label = title.trim() || "New source";
    onClose();
    toast(
      "Queued for indexing",
      `${label} will be available to both agents shortly`,
      "ok",
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add knowledge"
      subtitle="Indexed once, then available to Q-Agent and D-Agent on every run."
      footer={
        <>
          <Button variant="primary" className="flex-1" onClick={add}>
            Add and index
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-[7px]">
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          SOURCE TYPE
        </span>
        <div className="flex flex-wrap gap-2">
          {SOURCE_TYPES.map((t) => (
            <Button
              key={t}
              size="sm"
              variant={t === type ? "tinted" : "ghost"}
              onClick={() => setType(t)}
            >
              {t}
            </Button>
          ))}
        </div>
      </div>

      <Input
        label="TITLE OR URL"
        placeholder="e.g. Payment domain glossary"
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />

      <div
        className={cn(
          "flex flex-col items-center justify-center gap-[9px] rounded-glyph-lg",
          "border border-dashed border-bd2 bg-inset p-[26px] text-center",
        )}
      >
        <span className="flex text-ps-text">
          <Icon name="upload" size={20} strokeWidth={2.2} />
        </span>
        <span className="text-[12.5px] font-semibold text-txt3">
          Drop a file or paste markdown
        </span>
        <span className="text-[11px] text-label">
          PDF, DOCX, MD, TXT, XLSX · up to 50 MB
        </span>
      </div>
    </Modal>
  );
}
