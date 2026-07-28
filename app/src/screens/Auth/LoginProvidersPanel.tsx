// Handoff § 7 › Login providers — "provider rows with toggles".

import { useState } from "react";
import { GlassCard, Glyph, Icon, Pill, Toggle, toast } from "@/components/ui";
import type { GlyphFill, IconName } from "@/components/ui";

interface LoginProvider {
  id: string;
  name: string;
  meta: string;
  icon: IconName;
  fill: GlyphFill;
  enabled: boolean;
}

/**
 * Static provider list from the prototype. There is no
 * `GET /api/auth/login-providers` in the data layer yet, so it lives here
 * rather than behind an invented endpoint.
 */
const LOGIN_PROVIDERS: LoginProvider[] = [
  {
    id: "entra",
    name: "Microsoft Entra ID",
    meta: "Primary provider · 6 of 6 members",
    icon: "azure",
    fill: "azure",
    enabled: true,
  },
  {
    id: "google",
    name: "Google Workspace",
    meta: "Available · not enforced",
    icon: "globe",
    fill: "neutral",
    enabled: true,
  },
  {
    id: "github",
    name: "GitHub",
    meta: "Developers only · 2 members",
    icon: "git",
    fill: "github",
    enabled: false,
  },
  {
    id: "password",
    name: "Email and password",
    meta: "Disabled by workspace policy",
    icon: "key",
    fill: "neutral",
    enabled: false,
  },
];

export function LoginProvidersPanel() {
  const [providers, setProviders] = useState(LOGIN_PROVIDERS);

  const flip = (id: string, enabled: boolean) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === id ? { ...p, enabled } : p)),
    );
    const provider = providers.find((p) => p.id === id);
    if (provider) {
      toast(
        provider.name,
        `${enabled ? "Enabled" : "Disabled"} as a login provider`,
        "ok",
      );
    }
  };

  return (
    <div className="grid grid-cols-2 gap-3.5">
      {providers.map((p) => (
        <GlassCard
          key={p.id}
          className="flex items-center gap-3.5 p-5 transition-colors duration-200 hover:border-bd2"
        >
          <Glyph
            size={34}
            fill={p.fill}
            icon={<Icon name={p.icon} size={16} strokeWidth={2.2} />}
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-extrabold tracking-[-.01em] text-txt">
              {p.name}
            </div>
            <div className="mt-[3px] truncate text-[12px] text-muted">
              {p.meta}
            </div>
          </div>
          <Pill tone={p.enabled ? "ok" : "neutral"} size="sm">
            {p.enabled ? "Enabled" : "Disabled"}
          </Pill>
          <Toggle
            checked={p.enabled}
            onChange={(next) => flip(p.id, next)}
            aria-label={p.name}
          />
        </GlassCard>
      ))}
    </div>
  );
}
