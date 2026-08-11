// Direct account creation (#143) — `POST /auth/users`, the one admin endpoint
// that had no caller anywhere in the app.
//
// ## Why this sits next to Invite rather than replacing it
//
// The two differ in exactly one way that matters to an admin: an invitation is
// unusable until the invitee redeems a reset token, and on a deployment where
// email delivery is not wired that token has to be carried over by hand. A
// directly created account works the moment it exists, because the admin sets the
// password.
//
// So Invite is right for a colleague with a mailbox, and this is right for a
// shared or service account — or for handing someone working credentials in the
// room. Invite stays the primary action; this is secondary.
//
// Lives here with the other 520px modals for consistency with `ModalHost`, even
// though only User Management raises it today.

import { useState } from "react";

import { Button, Input, Modal, Notice, toast } from "@/components/ui";
import {
  ASSIGNABLE_ROLES,
  createUser,
  type Member,
  type RoleName,
} from "@/data";
import { ApiError } from "@/lib/api";

export interface AddUserModalProps {
  open: boolean;
  onClose: () => void;
  /** Fired with the created member once the hub confirms. */
  onCreated?: (member: Member) => void;
}

export function AddUserModal({ open, onClose, onCreated }: AddUserModalProps) {
  const [email, setEmail] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [role, setRole] = useState<RoleName>("Member");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The hub requires an email and a password, and defaults both names to "". Any
  // stricter rule here would be this form inventing policy the API does not have.
  const ready = email.trim().length > 0 && password.length > 0;

  const close = () => {
    if (pending) return;
    setEmail("");
    setFirst("");
    setLast("");
    setPassword("");
    setRole("Member");
    setError(null);
    onClose();
  };

  const create = async () => {
    if (!ready || pending) return;
    setPending(true);
    setError(null);
    try {
      const member = await createUser({
        email: email.trim(),
        firstName: first.trim(),
        lastName: last.trim(),
        role,
        password,
      });
      onCreated?.(member);
      toast(`${member.email} can sign in now`);
      close();
    } catch (err) {
      // 409 on a duplicate email, 400 on a bad role, 403 if you are not an admin
      // — all worth reading, so pass the hub's wording through.
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
      title="Add a user"
      subtitle="Sets the password yourself, so the account works immediately."
      footer={
        <>
          <Button
            variant="primary"
            className="flex-1"
            disabled={!ready || pending}
            onClick={() => void create()}
          >
            {pending ? "Creating…" : "Create account"}
          </Button>
          <Button variant="ghost" disabled={pending} onClick={close}>
            Cancel
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

      <div className="flex gap-2.5">
        <Input
          label="FIRST NAME"
          placeholder="Duna"
          className="flex-1"
          value={first}
          onChange={(e) => setFirst(e.target.value)}
        />
        <Input
          label="LAST NAME"
          placeholder="Nguyen"
          className="flex-1"
          value={last}
          onChange={(e) => setLast(e.target.value)}
        />
      </div>

      <Input
        label="PASSWORD"
        placeholder="••••••••••••"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
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

      <Notice tone="info">
        They can sign in as soon as this is created — pass the password on
        through a channel you trust, and have them change it. To let someone set
        their own instead, use <strong>Invite member</strong>.
      </Notice>

      {error && <Notice tone="danger">{error}</Notice>}
    </Modal>
  );
}
