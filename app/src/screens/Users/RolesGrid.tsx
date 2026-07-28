// Handoff § 8 › Roles — "2-up cards, initial badge, member count chip,
// description, permission checklist".

import { useEffect, useState } from "react";
import { GlassCard, Glyph, Icon, Pill, type GlyphFill } from "@/components/ui";
import { getRoles, type Role, type RoleName } from "@/data";

const BADGE_FILL: Record<RoleName, GlyphFill> = {
  Owner: "accent",
  Admin: "qagent",
  Member: "dagent",
  Viewer: "neutral",
};

const countLabel = (count: number) =>
  count === 1 ? "1 person" : `${count} people`;

export function RolesGrid() {
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    let live = true;
    void getRoles().then((rows) => live && setRoles(rows));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="grid grid-cols-2 gap-3.5">
      {roles.map((r) => (
        <GlassCard
          key={r.name}
          className="flex flex-col gap-3.5 p-[22px] transition-colors duration-200 hover:border-bd2"
        >
          <div className="flex items-center gap-3">
            <Glyph size={30} fill={BADGE_FILL[r.name]} label={r.name.charAt(0)} />
            <span className="min-w-0 flex-1 truncate text-[16px] font-extrabold tracking-[-.02em] text-txt">
              {r.name}
            </span>
            <Pill tone="neutral" size="sm" mono>
              {countLabel(r.count)}
            </Pill>
          </div>

          <p className="m-0 text-[12.5px] leading-[1.55] text-pretty text-txt4">
            {r.description}
          </p>

          <div className="flex flex-col gap-2">
            {r.permissions.map((p) => (
              <div
                key={p}
                className="flex items-start gap-[9px] text-[12.5px] text-txt3"
              >
                <Icon
                  name="check"
                  size={14}
                  strokeWidth={2.6}
                  className="mt-[2px] shrink-0 text-ps-text"
                />
                {p}
              </div>
            ))}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
