// Handoff § 0. App shell › Sidebar — 268px glass panel, top→bottom:
//   1. 3D logo button (tilt) → the landing view
//   2. product lockup (accent tile + Eme/Hub + AI OPERATING CENTER)
//   3. nav, one flat list under WORKSPACE / PLATFORM headings
//   4. footer: status card + user chip
//
// Nav uses <NavLink>: the URL is the source of truth (CLAUDE.md).

import { NavLink, useNavigate } from "react-router-dom";

import { Icon } from "@/components/ui";
import { useLogoTilt } from "@/hooks/useTilt";
import { cn } from "@/lib/cn";
import { displayName, useAuth, userInitials, userRole } from "@/store/auth";
import { NAV_GROUPS } from "./nav";
import { useSidebarStats } from "./useSidebarStats";

export interface SidebarProps {
  /** Called on every nav click so the shell can reset scrollTop to 0. */
  onNavigate: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const navigate = useNavigate();
  const logo = useLogoTilt<HTMLDivElement>();
  const user = useAuth((s) => s.user);
  const role = userRole(user);
  const stats = useSidebarStats();
  const badgeFor: Record<string, number | null> = {
    "/app/projects": stats.projectCount,
    "/app/tickets": stats.ticketCount,
    "/app/integrations": stats.connectionCount,
  };

  return (
    <aside
      className={cn(
        "flex w-[268px] shrink-0 flex-col overflow-y-auto",
        "glass-panel rounded-[22px] px-3.5 py-[18px] shadow-panel",
      )}
    >
      {/* 1. Logo — returns to the landing view. */}
      <button
        type="button"
        aria-label="EMESOFT — back to the landing view"
        onClick={() => navigate("/")}
        onMouseMove={logo.onMouseMove}
        onMouseLeave={logo.onMouseLeave}
        className="block w-full cursor-pointer px-1 pt-0.5 pb-3.5 [perspective:820px]"
      >
        <div
          ref={logo.ref}
          className={cn(
            "relative rounded-lg [transform-style:preserve-3d] will-change-transform",
            "[filter:drop-shadow(0_12px_20px_var(--shadow))]",
          )}
        >
          {/* The handoff's diagonal `metalFlash` sheen was removed here and on
              the landing header — it read as an animation glitch, not a shine. */}
          <img
            src="/assets/eme-3d-logo-cut.png"
            alt="EMESOFT"
            className="pointer-events-none block h-auto w-full"
          />
        </div>
      </button>

      {/* 2. Product lockup. */}
      <div className="flex items-center gap-[11px] px-2 pt-1 pb-4">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-[12px]",
            "bg-accent-grad shadow-[0_6px_18px_-4px_var(--pglow)]",
          )}
        >
          <Icon
            name="spark"
            size={19}
            strokeWidth={2.2}
            className="text-white"
          />
        </span>
        <div className="min-w-0">
          <div className="text-[17px] leading-none font-black tracking-[-.03em] text-txt">
            Eme<span className="text-silver">Hub</span>
          </div>
          <div className="mt-[3px] text-[9px] font-bold tracking-[.12em] text-muted">
            AI OPERATING CENTER
          </div>
        </div>
      </div>

      {/* 3. Nav. */}
      <nav className="-mx-1 mb-0.5 flex flex-col gap-0.5 px-1">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="contents">
            <div className="px-1.5 pt-3 pb-[7px] text-[10px] font-bold tracking-[.12em] text-label">
              {group.label}
            </div>
            {group.items.map((item) => {
              // Badges are live counts (useSidebarStats), never the
              // hardcoded fixture values the handoff shipped. A count that
              // hasn't loaded yet (or failed) renders no badge at all rather
              // than a stale or invented number.
              const liveCount = badgeFor[item.to];
              const badge =
                liveCount !== undefined && liveCount !== null
                  ? String(liveCount)
                  : undefined;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  data-surface
                  className={({ isActive }) =>
                    cn(
                      "flex w-full items-center gap-2.5 rounded-[11px] border px-2.5 py-[9px]",
                      "text-left text-[13px] font-semibold",
                      isActive
                        ? "border-pb bg-pt text-p-on"
                        : "border-transparent bg-transparent text-muted hover:bg-bd3",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span className="flex w-[18px] shrink-0 justify-center">
                        <Icon name={item.icon} size={16} strokeWidth={2.1} />
                      </span>
                      <span className="min-w-0 flex-1 truncate text-left">
                        {item.label}
                      </span>
                      {badge && (
                        <span
                          className={cn(
                            "rounded-pill px-[7px] py-0.5 font-mono text-[10px] font-bold",
                            isActive
                              ? "bg-accent-grad text-white"
                              : "bg-bd text-muted",
                          )}
                        >
                          {badge}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      {/* 4. Footer.
          The handoff's status card said "ALL SYSTEMS NOMINAL" and "2 agents
          online" unconditionally — there is no agent-heartbeat concept on
          the hub to back that, and it would be a false claim. This reports
          only what the hub actually knows: the live connection count. */}
      <div className="mt-auto pt-3.5">
        <div className="flex flex-col gap-[9px] rounded-card border border-bd bg-card p-3.5">
          <div className="flex items-center gap-2">
            <span className="size-[7px] shrink-0 animate-pulse-dot rounded-full bg-ok shadow-[0_0_8px_var(--ok)]" />
            <span className="text-[11px] font-bold tracking-[.06em] text-txt3">
              HUB CONNECTED
            </span>
          </div>
          <div className="text-[11.5px] leading-[1.45] text-faint">
            {stats.connectionCount === null
              ? "Checking integrations…"
              : stats.connectionCount === 1
                ? "1 integration connected"
                : `${stats.connectionCount} integrations connected`}
          </div>
        </div>

        {/* The signed-in principal, from `store/auth.ts` (i.e. what /auth/me
            returned) — never a fixture. The prototype's chip only fired a
            toast; it now opens the account screen. */}
        <button
          type="button"
          data-surface
          aria-label="Open your account"
          onClick={() => {
            onNavigate();
            navigate("/app/profile");
          }}
          className={cn(
            "mt-2.5 flex w-full cursor-pointer items-center gap-2.5 rounded-[13px]",
            "border border-bd bg-card px-2.5 py-[9px] hover:bg-bd3",
          )}
        >
          <span className="flex size-[30px] shrink-0 items-center justify-center rounded-[10px] bg-accent-grad text-[12px] font-extrabold text-white">
            {userInitials(user)}
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-[12.5px] font-bold text-txt2">
              {displayName(user) || "Your account"}
            </span>
            <span className="block truncate text-[10.5px] text-faint">
              {role ? `${role} · EMESOFT` : "EMESOFT"}
            </span>
          </span>
          <Icon
            name="chevronUpDown"
            size={14}
            strokeWidth={2.2}
            className="shrink-0 text-faint"
          />
        </button>
      </div>
    </aside>
  );
}
