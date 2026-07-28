// Handoff § 10. Settings › Appearance.
//
// Every control here drives the shared appearance store (`@/store/appearance`)
// — Settings does not keep its own copy. Changes apply immediately and toast
// (Handoff › Async behaviours: "Mode / accent change — applies tokens
// immediately + toast").

import { useEffect, useRef } from "react";

import { GlassCard, Icon, Range, Segmented, toast } from "@/components/ui";
import { cn } from "@/lib/cn";
import { ACCENTS, useAppearance, type Accent, type Mode } from "@/store/appearance";
import { Hairline, ToggleRow } from "./SettingRow";

/**
 * The ONE place a colour literal is allowed in a `.tsx` (CLAUDE.md § Design).
 * Each swatch has to render its own accent's gradient and glow while a
 * *different* accent is active, so `--pg` / `--pglow` (which always resolve to
 * the current accent) cannot express them. Values are verbatim from the
 * handoff's Accent-tokens table.
 */
const ACCENT_SWATCHES: Record<Accent, { gradient: string; glow: string }> = {
  red: {
    gradient: "linear-gradient(135deg,#ff4d5c,#c20d22)",
    glow: "rgba(225,23,43,.5)",
  },
  purple: {
    gradient: "linear-gradient(135deg,#8b5cf6,#6366f1)",
    glow: "rgba(139,92,246,.5)",
  },
  cyan: {
    gradient: "linear-gradient(135deg,#22d3ee,#0ea5b7)",
    glow: "rgba(34,211,238,.45)",
  },
  steel: {
    gradient: "linear-gradient(135deg,#e2e6ec,#8d939e)",
    glow: "rgba(180,190,205,.4)",
  },
};

const MODE_OPTIONS = [
  { value: "dark" as Mode, label: "Dark", icon: <Icon name="moon" size={14} strokeWidth={2.1} /> },
  { value: "light" as Mode, label: "Light", icon: <Icon name="sun" size={14} strokeWidth={2.1} /> },
];

export function AppearanceCard() {
  const { mode, accent, ambient, fx3d, tilt } = useAppearance();
  const setMode = useAppearance((s) => s.setMode);
  const setAccent = useAppearance((s) => s.setAccent);
  const setAmbient = useAppearance((s) => s.setAmbient);
  const setFx3d = useAppearance((s) => s.setFx3d);
  const setTilt = useAppearance((s) => s.setTilt);

  // The bloom slider fires per 5% step; toast once the drag settles.
  const ambientToastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  useEffect(() => () => clearTimeout(ambientToastTimer.current), []);

  const pickMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    toast(
      next === "light" ? "Light mode on" : "Dark mode on",
      next === "light"
        ? "Panels, type and the constellation switched to the paper palette"
        : "Back to the default operating surface",
    );
  };

  const pickAccent = (next: Accent) => {
    setAccent(next);
    const label = ACCENTS.find((a) => a.key === next)?.label ?? "";
    toast("Brand color updated", `${label} is now the primary accent`);
  };

  const changeAmbient = (value: number) => {
    setAmbient(value);
    clearTimeout(ambientToastTimer.current);
    ambientToastTimer.current = setTimeout(
      () => toast("Ambient bloom updated", `Bloom intensity set to ${value}%`),
      450,
    );
  };

  const flipFx3d = (on: boolean) => {
    setFx3d(on);
    if (on) toast("Constellation on", "The ambient WebGL field is running again");
    else
      toast(
        "Constellation off",
        "Ambient WebGL field disabled for this session",
        "warn",
      );
  };

  const flipTilt = (on: boolean) => {
    setTilt(on);
    if (on)
      toast(
        "Depth on hover on",
        "The logo, product cards and tiles tilt as the pointer moves across them",
      );
    else
      toast(
        "Depth on hover off",
        "Pointer tilt disabled across the interface",
        "warn",
      );
  };

  return (
    <GlassCard radius="panel" className="flex flex-col gap-[18px] p-[22px]">
      <div>
        <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
          Appearance
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          Theme, brand colour and the ambient depth behind the interface.
        </div>
      </div>

      {/* Interface mode */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-[220px] flex-1">
          <div className="text-[13.5px] font-bold text-txt2">Interface mode</div>
          <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
            Dark is the default operating surface. Light keeps the same layout on
            a paper background.
          </div>
        </div>
        <Segmented
          options={MODE_OPTIONS}
          value={mode}
          onChange={pickMode}
          variant="solid"
        />
      </div>

      <Hairline />

      {/* Brand colour */}
      <div>
        <div className="text-[13.5px] font-bold text-txt2">Brand colour</div>
        <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
          Drives buttons, highlights, the ambient bloom and the constellation
          behind the app.
        </div>
        <div className="mt-[14px] flex flex-wrap gap-[10px]">
          {ACCENTS.map((a) => {
            const active = a.key === accent;
            const swatch = ACCENT_SWATCHES[a.key];
            return (
              <button
                key={a.key}
                type="button"
                aria-pressed={active}
                onClick={() => pickAccent(a.key)}
                className={cn(
                  "inline-flex cursor-pointer items-center gap-[10px] rounded-button-lg",
                  "border px-[15px] py-[11px]",
                  "transition-[background-color,border-color] duration-200",
                  active ? "border-pb bg-pt" : "border-bd bg-inset hover:bg-card3",
                )}
              >
                <span
                  className="size-[26px] shrink-0 rounded-control"
                  // Computed: this swatch's own gradient + glow.
                  style={{
                    background: swatch.gradient,
                    boxShadow: `0 6px 16px -5px ${swatch.glow}`,
                  }}
                />
                <span className="text-[12.5px] font-bold whitespace-nowrap text-txt2">
                  {a.label}
                </span>
                {active && (
                  <Icon name="check" size={14} strokeWidth={3} className="text-ok" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      <Hairline />

      {/* Ambient bloom */}
      <div className="flex flex-wrap items-center gap-[18px]">
        <div className="min-w-[220px] flex-1">
          <div className="text-[13.5px] font-bold text-txt2">Ambient bloom</div>
          <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
            Intensity of the two blurred light sources behind the panels.
          </div>
        </div>
        <Range
          value={ambient}
          onChange={changeAmbient}
          min={0}
          max={100}
          step={5}
          aria-label="Ambient bloom"
          className="w-[220px]"
        />
        <span className="w-[42px] text-right font-mono text-[13px] text-txt2">
          {ambient}%
        </span>
      </div>

      <ToggleRow
        label="3D constellation field"
        description="Live WebGL particle network that reacts to the cursor. Turn it off on low-power machines."
        checked={fx3d}
        onChange={flipFx3d}
        className="pt-[2px]"
      />

      <ToggleRow
        label="Depth on hover"
        description="3D tilt on the logo, product cards and tiles as the pointer moves across them."
        checked={tilt}
        onChange={flipTilt}
      />
    </GlassCard>
  );
}
