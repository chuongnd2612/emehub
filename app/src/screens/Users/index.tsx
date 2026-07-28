// Handoff § 8. User Management (`/app/users`).
//
// Tabs: Members · Roles · Invitations, with a right-aligned `Invite member`
// primary. The active tab is intra-screen SELECTION, so it lives in the URL as
// `?tab=` — not in Zustand (CLAUDE.md › Frontend conventions). The modal is
// UI-only state and does live in the store.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Icon } from "@/components/ui";
import { getInvitations, type Invitation } from "@/data";
import { useUi } from "@/store/ui";
import { InvitationsList } from "./InvitationsList";
import { InviteMemberModal } from "./InviteMemberModal";
import { MembersTable } from "./MembersTable";
import { RolesGrid } from "./RolesGrid";
import { TabStrip } from "./TabStrip";

const TABS = [
  { value: "members", label: "Members" },
  { value: "roles", label: "Roles" },
  { value: "invitations", label: "Invitations" },
] as const;

type UsersTab = (typeof TABS)[number]["value"];

const isTab = (value: string | null): value is UsersTab =>
  TABS.some((t) => t.value === value);

export default function UsersScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: UsersTab = isTab(raw) ? raw : "members";

  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);

  const [invitations, setInvitations] = useState<Invitation[]>([]);

  useEffect(() => {
    let live = true;
    void getInvitations().then((rows) => live && setInvitations(rows));
    return () => {
      live = false;
    };
  }, []);

  const setTab = (next: UsersTab) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  const openInvite = () => setModal("invite");

  return (
    <div className="animate-fade-in-up flex flex-col gap-3.5">
      <TabStrip
        tabs={TABS}
        value={tab}
        onChange={setTab}
        action={
          <Button
            variant="primary"
            icon={<Icon name="plus" size={15} strokeWidth={2.4} />}
            onClick={openInvite}
          >
            Invite member
          </Button>
        }
      />

      {tab === "members" && <MembersTable />}
      {tab === "roles" && <RolesGrid />}
      {tab === "invitations" && (
        <InvitationsList
          invitations={invitations}
          onInvite={openInvite}
          onRevoke={(inv) =>
            setInvitations((prev) => prev.filter((i) => i.email !== inv.email))
          }
        />
      )}

      <InviteMemberModal
        open={modal === "invite"}
        onClose={() => setModal(null)}
        onInvited={(inv) => {
          setInvitations((prev) => [inv, ...prev]);
          setTab("invitations");
        }}
      />
    </div>
  );
}
