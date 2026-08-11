// The rename half of the Members row actions (#141).
//
// Row-scoped, so it lives here rather than in `components/modals/ModalHost`:
// that host exists for the modals more than one screen raises, and this one is
// meaningless without a target row. It takes the member as a prop and mounts
// only while one is selected.
//
// Live against `PATCH /auth/users/{id}` with `firstName` / `lastName`.
//
// Both fields may be cleared. That is not a validation hole: `displayNameFrom`
// falls back to the email, so a nameless account still reads as itself in the
// table — and the hub's own `/auth/users` create path defaults both to empty, so
// rejecting it here would be stricter than the API it is talking to.

import { useEffect, useState } from "react";

import { Button, Input, Modal, Notice, toast } from "@/components/ui";
import { updateMember, type Member } from "@/data";
import { ApiError } from "@/lib/api";

export interface RenameMemberModalProps {
  /** The row being renamed, or null when the modal is closed. */
  member: Member | null;
  onClose: () => void;
  /** Fired with the updated row once the hub confirms. */
  onRenamed: (member: Member) => void;
}

export function RenameMemberModal({
  member,
  onClose,
  onRenamed,
}: RenameMemberModalProps) {
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // `Member` carries the joined display name, not the two stored fields, so seed
  // from a split of it — and re-seed whenever the target row changes, because
  // the modal instance is reused across rows.
  useEffect(() => {
    if (!member) return;
    const parts = member.name.trim().split(/\s+/);
    // A single token is a first name; the email fallback has no space either, in
    // which case both fields start empty rather than seeding a name from an
    // address the user never typed.
    const seeded = member.name === member.email ? [] : parts;
    setFirst(seeded[0] ?? "");
    setLast(seeded.slice(1).join(" "));
    setError(null);
  }, [member]);

  const close = () => {
    if (pending) return;
    setError(null);
    onClose();
  };

  const save = async () => {
    if (!member || pending) return;
    setPending(true);
    setError(null);
    try {
      const updated = await updateMember(member, {
        firstName: first.trim(),
        lastName: last.trim(),
      });
      onRenamed(updated);
      toast("Name updated");
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "The hub did not respond.",
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal
      open={member !== null}
      onClose={close}
      title="Rename member"
      subtitle={member?.email}
      footer={
        <>
          <Button
            variant="primary"
            className="flex-1"
            disabled={pending}
            onClick={() => void save()}
          >
            {pending ? "Saving…" : "Save name"}
          </Button>
          <Button variant="ghost" disabled={pending} onClick={close}>
            Cancel
          </Button>
        </>
      }
    >
      <Input
        label="FIRST NAME"
        placeholder="Duna"
        autoFocus
        value={first}
        onChange={(e) => setFirst(e.target.value)}
      />
      <Input
        label="LAST NAME"
        placeholder="Nguyen"
        value={last}
        onChange={(e) => setLast(e.target.value)}
      />

      {error && <Notice tone="danger">{error}</Notice>}
    </Modal>
  );
}
