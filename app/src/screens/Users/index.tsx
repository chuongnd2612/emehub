// Handoff § 8. User Management (`/app/users`).
//
// A right-aligned `Invite member` primary, plus a secondary `Add user`. The
// modals are mounted globally (`components/modals/ModalHost`) because the
// Overview quick actions raise them too; this screen just re-reads the list
// whenever one of them closes.
//
// ## One tab, because only one of the three had anything behind it
//
// The handoff's Members · Roles · Invitations strip is now Members alone (#191).
// Roles rendered four fabricated roles with invented member counts and
// permission checklists that exist nowhere but the design — the hub stores
// `admin` and `member`. Invitations was seeded from three fabricated people,
// its Revoke spliced a local array without touching the account the hub had
// actually created, and its Resend only raised a toast; `POST
// /auth/users/invite` creates the user immediately, so there is nothing pending
// to list in the first place.
//
// The tab strip stays for its layout and its action slot, and `?tab=` still
// falls back rather than blanking: a bookmarked `?tab=roles` lands on Members.

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Icon } from "@/components/ui";
import { useUi } from "@/store/ui";
import { MembersTable } from "./MembersTable";
import { TabStrip } from "./TabStrip";

const TABS = [{ value: "members", label: "Members" }] as const;

type UsersTab = (typeof TABS)[number]["value"];

const isTab = (value: string | null): value is UsersTab =>
  TABS.some((t) => t.value === value);

export default function UsersScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: UsersTab = isTab(raw) ? raw : "members";

  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);

  // `MembersTable` reads on mount, so a newly created account would not appear
  // until the screen was left and returned to. Tell it to re-read when either
  // account-creating modal closes — both `Add user` and `Invite member` write a
  // real row — which is the only signal available here, because `ModalHost`
  // owns those modals globally. A prop rather than a `key`: remounting the
  // table threw away rows that were already correct (#200).
  const [membersEpoch, setMembersEpoch] = useState(0);
  const wasCreating = useRef(false);
  useEffect(() => {
    if (modal === "addUser" || modal === "invite") {
      wasCreating.current = true;
      return;
    }
    if (wasCreating.current) {
      wasCreating.current = false;
      setMembersEpoch((epoch) => epoch + 1);
    }
  }, [modal]);

  const setTab = (next: UsersTab) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  return (
    <div className="animate-fade-in-up flex flex-col gap-3.5">
      <TabStrip
        tabs={TABS}
        value={tab}
        onChange={setTab}
        action={
          <div className="flex items-center gap-2">
            {/* Secondary to Invite: most accounts should be for a person with a
                mailbox, who sets their own password. */}
            <Button variant="ghost" onClick={() => setModal("addUser")}>
              Add user
            </Button>
            <Button
              variant="primary"
              icon={<Icon name="plus" size={15} strokeWidth={2.4} />}
              onClick={() => setModal("invite")}
            >
              Invite member
            </Button>
          </div>
        }
      />

      <MembersTable reloadSignal={membersEpoch} />
    </div>
  );
}
