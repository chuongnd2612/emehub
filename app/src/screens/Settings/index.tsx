// Handoff § 10. Settings — max-width 1080px, three glass cards:
// Appearance · Workspace defaults · Notifications.
//
// Appearance drives the shared `@/store/appearance` store directly, so mode,
// accent, ambient bloom, the constellation flag and pointer tilt take effect
// across the whole app the moment they change.

import { AppearanceCard } from "./AppearanceCard";
import { NotificationsCard } from "./NotificationsCard";
import { WorkspaceDefaultsCard } from "./WorkspaceDefaultsCard";

export default function SettingsScreen() {
  return (
    <div className="animate-fade-in-up flex max-w-[1080px] flex-col gap-[14px]">
      <AppearanceCard />
      <WorkspaceDefaultsCard />
      <NotificationsCard />
    </div>
  );
}
