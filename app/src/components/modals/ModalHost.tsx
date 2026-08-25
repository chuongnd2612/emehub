// The three 520px modals from Handoff › Overlays, mounted once inside the app
// shell so every `setModal(…)` in the app has a renderer no matter which screen
// fired it — "New project" is raised from the Overview quick actions AND from
// its own screen, and "Invite member" from Overview as well as User Management.
//
// The Import dialog is deliberately NOT here: it is provider-scoped and its
// 1500 ms spinner belongs to the button that opened it, so each caller mounts
// its own (Handoff § 5 + `components/import/useImportRun`).

import { useNavigate } from "react-router-dom";

import { useUi } from "@/store/ui";
import { AddUserModal } from "./AddUserModal";
import { InviteMemberModal } from "./InviteMemberModal";
import { NewProjectModal } from "./NewProjectModal";

export function ModalHost() {
  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);
  const navigate = useNavigate();
  const close = () => setModal(null);

  return (
    <>
      <NewProjectModal open={modal === "project"} onClose={close} />
      <InviteMemberModal
        open={modal === "invite"}
        onClose={close}
        // An invitation creates the account immediately, so it lands on the
        // Members list — wherever the modal was opened from. There is no
        // pending-invitation list to send anyone to (#191).
        onInvited={() => navigate("/app/users?tab=members")}
      />
      <AddUserModal
        open={modal === "addUser"}
        onClose={close}
        // A created account is a member, not an invitation — it lands on the
        // Members tab, which is where the list that must re-read lives.
        onCreated={() => navigate("/app/users?tab=members")}
      />
    </>
  );
}
