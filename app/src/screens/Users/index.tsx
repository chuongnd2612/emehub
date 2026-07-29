// Handoff § 8. User Management (`/app/users`).
//
// Tabs: Members · Roles · Invitations, with a right-aligned `Invite member`
// primary. The active tab is intra-screen SELECTION, so it lives in the URL as
// `?tab=` — not in Zustand (CLAUDE.md › Frontend conventions). The modal is
// UI-only state and does live in the store.
//
// The Invite modal itself is mounted globally (`components/modals/ModalHost`)
// because the Overview quick action raises it too; this screen just re-reads
// the list whenever that modal closes.
//
// Members is live (`GET /auth/users`). Roles and Invitations are NOT: the hub
// has no roles resource and no invitation resource, so those two tabs still
// render fixtures and each says so up front. Rendering fixture data without a
// label would be presenting it as real, which the design rules forbid.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Icon, Notice } from "@/components/ui";
import { getInvitations, revokeInvitation, type Invitation } from "@/data";
import { useUi } from "@/store/ui";
import { InvitationsList } from "./InvitationsList";
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

  // STUB: GET /api/invitations. Re-reads on mount and every time the global
  // Invite modal closes, which is when a new invitation may have been created.
  useEffect(() => {
    if (modal === "invite") return;
    let live = true;
    void getInvitations().then((rows) => live && setInvitations(rows));
    return () => {
      live = false;
    };
  }, [modal]);

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

      {tab === "roles" && (
        <>
          <Notice tone="warn">
            Preview data. The hub stores two roles — Admin and Member — and has
            no permissions resource, so these cards and their checklists are the
            design, not live configuration.
          </Notice>
          <RolesGrid />
        </>
      )}

      {tab === "invitations" && (
        <>
          <Notice tone="warn">
            Preview data. An invitation creates the account straight away, so
            the hub has nothing pending to list. This shows what this browser
            has sent plus the seeded examples, and clears on reload — revoking
            here does not delete the account.
          </Notice>
          <InvitationsList
            invitations={invitations}
            onInvite={openInvite}
            onRevoke={(inv) => {
              void revokeInvitation(inv.email);
              setInvitations((prev) =>
                prev.filter((i) => i.email !== inv.email),
              );
            }}
          />
        </>
      )}
    </div>
  );
}
