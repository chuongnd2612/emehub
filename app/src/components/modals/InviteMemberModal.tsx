// Handoff § 8 › "right-aligned `Invite member` primary" and Overlays › Modals
// ("Invite member — 520px, var(--pop), radius 20, animation:fadeInUp .25s").
//
// Lives here rather than under screens/Users because the Overview quick action
// opens it too — it is mounted once by `ModalHost`.
//
// Live against `POST /auth/users/invite`, which creates the account with an
// unusable password and returns a one-shot reset token. Two consequences the
// prototype does not model:
//   • It can fail — 409 on a duplicate email, 403 if you are not an admin — so
//     the modal no longer closes optimistically on submit.
//   • Only Admin and Member are offered. The hub stores no other role
//     (`data/people.ts`), and Owner was already excluded by the design.

import { useState } from "react";

import { Button, Input, Modal, Notice, toast } from "@/components/ui";
import {
  ASSIGNABLE_ROLES,
  invite,
  type Invitation,
  type RoleName,
} from "@/data";
import { ApiError } from "@/lib/api";
import { displayName, useAuth } from "@/store/auth";

export interface InviteMemberModalProps {
  open: boolean;
  onClose: () => void;
  /** Fired once the hub confirms, with the created invitation. */
  onInvited?: (invitation: Invitation) => void;
}

export function InviteMemberModal({
  open,
  onClose,
  onInvited,
}: InviteMemberModalProps) {
  const me = useAuth((s) => s.user);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RoleName>("Member");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Dev-only: the hub echoes the redemption link outside production. */
  const [resetPath, setResetPath] = useState<string | null>(null);

  const close = () => {
    if (pending) return;
    setEmail("");
    setError(null);
    setResetPath(null);
    onClose();
  };

  const send = async () => {
    const address = email.trim();
    if (pending || !address) return;
    setPending(true);
    setError(null);
    try {
      const result = await invite(address, role, displayName(me) || "an admin");
      onInvited?.(result.invitation);
      toast(`Invitation sent to ${result.invitation.email}`);
      if (result.resetPath) {
        // Email delivery is a stub on this environment, so keep the modal open
        // — the link has to be handed over by hand.
        setResetPath(result.resetPath);
        setEmail("");
      } else {
        close();
      }
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
      open={open}
      onClose={close}
      title="Invite a member"
      subtitle="They will join the EMESOFT workspace and inherit the shared credentials."
      footer={
        <>
          <Button
            variant="primary"
            className="flex-1"
            disabled={pending || !email.trim()}
            onClick={() => void send()}
          >
            {pending ? "Sending…" : "Send invitation"}
          </Button>
          <Button variant="ghost" disabled={pending} onClick={close}>
            {resetPath ? "Done" : "Cancel"}
          </Button>
        </>
      }
    >
      <Input
        label="WORK EMAIL"
        placeholder="name@emesoft.net"
        type="email"
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />

      <div className="flex flex-col gap-[7px]">
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          ROLE
        </span>
        <div className="flex gap-2">
          {ASSIGNABLE_ROLES.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={r === role ? "tinted" : "ghost"}
              onClick={() => setRole(r)}
            >
              {r}
            </Button>
          ))}
        </div>
      </div>

      {error && <Notice tone="danger">{error}</Notice>}

      {resetPath && (
        <Notice tone="info">
          Email delivery is not wired up on this environment, so the hub returned
          the invitation link directly. Send it to them:{" "}
          <code className="font-mono text-[11.5px] break-all">{resetPath}</code>
        </Notice>
      )}
    </Modal>
  );
}
