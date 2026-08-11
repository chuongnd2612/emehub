// The destructive half of the Members row actions (#142).
//
// `DELETE /auth/users/{id}` is a hard delete with no soft-delete to fall back on:
// the row goes and its sessions go with it. The `identity` audit record keeps the
// email, so the trail outlives the account, but the account does not come back.
//
// ## Why this asks you to type the email
//
// The action fires from a row in a list, where the cost of a mis-aimed click is
// somebody else's account rather than your own. A yes/no dialog is answered by
// the same reflex that produced the misclick, and confirms nothing about *which*
// row you were on. Typing the email is the cheapest gate that makes the target
// explicit — it cannot be satisfied without reading the name of what you are
// about to destroy.
//
// The menu offers Deactivate above this for the same reason: deactivation ends
// their access immediately (the hub revokes the sessions) and is reversible, so
// it is the right answer to almost every reason someone reaches for Remove.

import { useEffect, useState } from "react";

import { Button, Input, Modal, Notice, toast } from "@/components/ui";
import { removeMember, type Member } from "@/data";
import { ApiError } from "@/lib/api";

export interface RemoveMemberModalProps {
  /** The row being removed, or null when the modal is closed. */
  member: Member | null;
  onClose: () => void;
  /** Fired with the removed id once the hub confirms. */
  onRemoved: (userId: number) => void;
}

export function RemoveMemberModal({
  member,
  onClose,
  onRemoved,
}: RemoveMemberModalProps) {
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The modal instance is reused across rows, so clear the box whenever the
  // target changes — otherwise a value typed for one account would still be
  // sitting there, matching nothing, or worse, matching the wrong row.
  useEffect(() => {
    setTyped("");
    setError(null);
  }, [member]);

  // Exact match, case-insensitive only because the hub lowercases emails on the
  // way in and the displayed value is already the stored one.
  const confirmed =
    member !== null &&
    typed.trim().toLowerCase() === member.email.trim().toLowerCase();

  const close = () => {
    if (pending) return;
    onClose();
  };

  const remove = async () => {
    if (!member || !confirmed || pending) return;
    setPending(true);
    setError(null);
    try {
      await removeMember(member.id);
      onRemoved(member.id);
      toast(`${member.email} removed`);
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
      title="Remove member"
      subtitle={member?.email}
      footer={
        <>
          <Button
            variant="destructive"
            className="flex-1"
            disabled={!confirmed || pending}
            onClick={() => void remove()}
          >
            {pending ? "Removing…" : "Remove permanently"}
          </Button>
          <Button variant="ghost" disabled={pending} onClick={close}>
            Cancel
          </Button>
        </>
      }
    >
      <Notice tone="danger">
        This is permanent. Their sessions end immediately and the account cannot
        be restored. To take access away reversibly, use{" "}
        <strong>Deactivate</strong> instead — it also ends their sessions at
        once.
      </Notice>

      <Input
        label="TYPE THE EMAIL TO CONFIRM"
        placeholder={member?.email}
        autoFocus
        autoComplete="off"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
      />

      {error && <Notice tone="danger">{error}</Notice>}
    </Modal>
  );
}
