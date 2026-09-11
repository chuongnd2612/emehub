// ADR 0012 › "WebGL orb". Scene colours and geometry for the landing hero orb.
//
// Same rule as `background/palette.ts`: WebGL cannot read CSS custom
// properties, so these numeric hex literals are the single declared place the
// orb's scene colours live. No component renders a raw hex.

import type { Accent } from "@/store/appearance";

/** Accent hex reused from the constellation — one accent table for both scenes. */
export { ACCENT_HEX } from "../background/palette";

export interface OrbPalette {
  /** Colour of the second, cooler rim layer behind the accent fresnel. */
  halo: number;
  /** Orbiting particle colour. */
  dust: number;
  /** Fresnel rim opacity. */
  rimOpacity: number;
  /** The back-face rim's opacity as a fraction of `rimOpacity`. */
  haloScale: number;
  /** Inner core glow opacity. */
  coreOpacity: number;
  /** Orbiting particle opacity. */
  dustOpacity: number;
  /** Multiplier on the logo plane's brightness. */
  logoOpacity: number;
}

/** Dark → additive glow, the rim reads as emitted light. */
export const DARK_ORB: OrbPalette = {
  halo: 0xdfe4ec,
  dust: 0xc8cedb,
  rimOpacity: 0.85,
  haloScale: 0.45,
  coreOpacity: 0.5,
  dustOpacity: 0.65,
  logoOpacity: 1,
};

/**
 * Light → normal blending. Additive on paper turns the rim white and the orb
 * disappears, which is exactly how the reference's `mix-blend-screen` video
 * fails (ADR 0012). Everything is dialled down and darkened instead.
 */
export const LIGHT_ORB: OrbPalette = {
  halo: 0x8b93a4,
  dust: 0x6b7280,
  rimOpacity: 0.55,
  // Additive turns into paint under normal blending: at the dark scale the back
  // rim washes the whole disc milky white and the brandmark stops reading.
  haloScale: 0.16,
  coreOpacity: 0.14,
  dustOpacity: 0.42,
  logoOpacity: 1,
};

export function orbPalette(mode: "dark" | "light"): OrbPalette {
  return mode === "light" ? LIGHT_ORB : DARK_ORB;
}

/** Geometry + motion constants. */
export const ORB = {
  cameraFov: 42,
  cameraNear: 0.1,
  cameraFar: 100,
  cameraZ: 7.4,

  /** Radius of the glass shell. */
  radius: 2.5,
  /** Icosahedron subdivision — high enough that the rim reads as a smooth edge. */
  detail: 5,
  /** Fresnel falloff exponent; higher = tighter rim. */
  rimPowerOuter: 2.6,
  rimPowerInner: 1.4,
  /** The inner core sphere, as a fraction of `radius`. */
  coreScale: 0.72,

  /** Logo plane width in world units (height follows the 2:1 PNG). */
  logoWidth: 3.3,
  logoAspect: 1774 / 887,
  /** Pushed toward the camera so it sits inside the front hemisphere. */
  logoZ: 1.35,

  dustCount: 900,
  dustCountReduced: 320,
  dustSize: 0.03,
  /** Particles orbit in a shell between these radii. */
  dustInner: 2.75,
  dustOuter: 4.3,

  /** Radians per second. */
  spinY: 0.16,
  dustSpin: 0.07,
  /** Breathing scale: 1 + amplitude · sin(t · speed). */
  breatheAmp: 0.022,
  breatheSpeed: 0.75,
  /** Pointer parallax, in radians at full deflection. */
  tiltX: 0.2,
  tiltY: 0.3,
  /** Lerp toward the pointer target. */
  tiltEase: 0.06,
} as const;
