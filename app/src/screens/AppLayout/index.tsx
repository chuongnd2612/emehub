// PLACEHOLDER (wave 1) — Handoff § 0. App shell.
//
// The real shell is the fixed 268px sidebar + sticky page header + scrolling
// content, over the ambient background stack. Only the background stack and
// the scroll region are wired here so the placeholder screens render; the
// sidebar and header belong to the shell agent. Replace the body of this file;
// do NOT touch src/router.tsx.

import { Outlet } from "react-router-dom";
import { useAppearance } from "@/store/appearance";

export default function AppLayout() {
  const ambient = useAppearance((s) => s.ambient);
  // Ambient bloom opacity is a user setting (0–100) — a computed value, which
  // is the documented exception to the no-inline-styles rule.
  const glow = { opacity: ambient / 100 };

  return (
    <div className="relative min-h-screen w-full">
      {/* Background stack — all position:fixed; inset:0. */}
      <div className="fixed inset-0 z-0 bg-bg" />
      <div
        className="pointer-events-none fixed top-[-16%] left-[-8%] z-[1] size-[660px] animate-glow-pulse rounded-full bg-[radial-gradient(circle,var(--pt),transparent_62%)] blur-[34px]"
        style={glow}
      />
      <div
        className="pointer-events-none fixed right-[-6%] bottom-[-22%] z-[1] size-[740px] animate-glow-pulse rounded-full bg-[radial-gradient(circle,var(--bloom2),transparent_62%)] blur-[34px] [animation-delay:1s] [animation-duration:11s]"
        style={glow}
      />

      <div className="relative z-[2] flex h-screen w-full gap-3.5 p-3.5">
        <main className="flex min-w-0 flex-1 flex-col gap-3.5">
          <div className="min-h-0 flex-1 overflow-y-auto pt-[2px] pr-1 pb-5 pl-[2px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
