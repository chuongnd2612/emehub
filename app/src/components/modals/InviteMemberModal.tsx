// Handoff § 8 › "right-aligned `Invite member` primary" and Overlays › Modals
// ("Invite member — 520px, var(--pop), radius 20, animation:fadeInUp .25s").
//
// Lives here rather than under screens/Users because the Overview quick action
// opens it too — it is mounted once by `ModalHost`.

import { useState } from "react";
import { Button, Input, Modal, toast } from "@/components/ui";
import { invite, type Invitation, type RoleName } from "@/data";

/** Owner is never offered on an invitation — ownership is transferred, not sent. */
const INVITE_ROLES: RoleName[] = ["Admin", "Member", "Viewer"];

export interface InviteMemberModalProps {
  open: boolean;
  onClose: () => void;
  /** Fired once the stub POST resolves, with the created invitation. */
  onInvited?: (invitation: Invitation) => void;
}

export function InviteMemberModal({
  open,
  onClose,
  onInvited,
}: InviteMemberModalProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RoleName>("Member");

  const send = () => {
    const address = email.trim() || "teammate@emesoft.net";
    void invite(address, role).then((inv) => onInvited?.(inv));
    setEmail("");
    onClose();
    toast("Invitation sent", `${address} · ${role}`, "ok");
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite a member"
      subtitle="They will join the EMESOFT workspace and inherit the shared credentials."
      footer={
        <>
          <Button variant="primary" className="flex-1" onClick={send}>
            Send invitation
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <Input
        label="WORK EMAIL"
        placeholder="name@emesoft.net"
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />

      <div className="flex flex-col gap-[7px]">
        <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
          ROLE
        </span>
        <div className="flex gap-2">
          {INVITE_ROLES.map((r) => (
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
    </Modal>
  );
}
