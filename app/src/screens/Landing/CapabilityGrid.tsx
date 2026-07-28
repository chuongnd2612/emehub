// Handoff § 1. Landing — capability grid (3-up). Icon + title + one-line
// description; each card navigates to the page that owns that capability.

import { useNavigate } from "react-router-dom";

import { Icon, type IconName } from "@/components/ui";
import { SectionLabel } from "./SectionLabel";

interface Capability {
  icon: IconName;
  title: string;
  desc: string;
  to: string;
}

const CAPABILITIES: Capability[] = [
  {
    icon: "users",
    title: "User management",
    desc: "Owners, admins, members and viewers with one shared directory.",
    to: "/app/users",
  },
  {
    icon: "cpu",
    title: "Claude credentials",
    desc: "One key, one model policy, inherited by every agent you launch.",
    to: "/app/claude",
  },
  {
    icon: "shield",
    title: "Authentication",
    desc: "SSO, sessions, API keys and login providers in a single place.",
    to: "/app/auth",
  },
  {
    icon: "plug",
    title: "Integrations",
    desc: "Azure DevOps, Jira and GitHub connected once, synced always.",
    to: "/app/integrations",
  },
  {
    icon: "book",
    title: "Project knowledge",
    desc: "Indexed per project, inherited by every agent that touches it.",
    to: "/app/projects",
  },
  {
    icon: "ticket",
    title: "Synced tickets",
    desc: "A read-only mirror of the work your providers already track.",
    to: "/app/tickets",
  },
];

export function CapabilityGrid() {
  const navigate = useNavigate();

  return (
    <section
      id="platform"
      className="mx-auto w-full max-w-[1400px] animate-fade-in-up px-11 pt-[52px] pb-5"
    >
      <SectionLabel>THE PLATFORM UNDERNEATH</SectionLabel>
      <div className="grid grid-cols-3 gap-3.5">
        {CAPABILITIES.map((c) => (
          <button
            key={c.title}
            type="button"
            onClick={() => navigate(c.to)}
            className="glass flex cursor-pointer flex-col gap-[9px] rounded-card p-5 text-left transition-[background-color,transform,border-color] duration-200 hover:-translate-y-[3px] hover:border-pb hover:bg-bd3"
          >
            <span className="flex size-[34px] items-center justify-center rounded-control-lg border border-bd2 bg-bd3 text-ps-text">
              <Icon name={c.icon} size={17} />
            </span>
            <span className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
              {c.title}
            </span>
            <span className="text-[12.5px] leading-[1.5] text-muted [text-wrap:pretty]">
              {c.desc}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
