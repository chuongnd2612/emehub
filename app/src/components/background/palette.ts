// Handoff › Interactions & Behavior › "3D constellation (background)".
//
// These are three.js *scene* colours — numeric hex literals consumed by
// `new THREE.Color(...)`, not CSS. They deliberately do NOT live in the token
// layer: WebGL cannot read CSS custom properties, and the handoff specifies
// these exact values per theme. No component ever renders a raw hex; this
// documented map is the single place scene colours are declared.

import type { Accent } from "@/store/appearance";

/** Handoff › Design Tokens › Accent tokens, "three.js hex" column. */
export const ACCENT_HEX: Record<Accent, number> = {
  red: 0xe1172b,
  purple: 0x8b5cf6,
  cyan: 0x22d3ee,
  steel: 0xb4becd,
};

export interface ScenePalette {
  /** Second colour of the [accent, silver, steel] cycle. */
  silver: number;
  /** Third colour of the cycle. */
  steel: number;
  /** Edge (LineSegments) colour. */
  line: number;
  /** Base opacity of the node PointsMaterial. */
  nodeOpacity: number;
  /** Base opacity of the edge LineBasicMaterial. */
  lineOpacity: number;
  /** Dust twinkle opacity = base + swing · world. */
  dustBase: number;
  dustSwing: number;
}

/** Dark → additive glow on near-black. */
export const DARK_PALETTE: ScenePalette = {
  silver: 0xdfe4ec,
  steel: 0x7a8290,
  line: 0x8d97a8,
  nodeOpacity: 0.9,
  lineOpacity: 0.45,
  dustBase: 0.4,
  dustSwing: 0.32,
};

/** Light → normal blending, darkened greys so the field reads on paper. */
export const LIGHT_PALETTE: ScenePalette = {
  silver: 0x6b7280,
  steel: 0x99a1b2,
  line: 0x5a6472,
  nodeOpacity: 0.72,
  lineOpacity: 0.26,
  dustBase: 0.22,
  dustSwing: 0.18,
};

export function scenePalette(mode: "dark" | "light"): ScenePalette {
  return mode === "light" ? LIGHT_PALETTE : DARK_PALETTE;
}

/** Scene geometry constants, verbatim from the handoff. */
export const SCENE = {
  cameraFov: 60,
  cameraNear: 1,
  cameraFar: 4000,
  cameraZ: 660,
  nodeCount: 62,
  nodeCountReduced: 40,
  nodeSpread: { x: 1060, y: 660, z: 740 },
  nodeSize: 5.6,
  edgeDistance: 250,
  dustCount: 1050,
  dustCountReduced: 500,
  dustSpread: { x: 2600, y: 1700, z: 1400 },
  dustSize: 4,
  /** Easing applied to the per-node cursor activation. */
  actEase: 0.2,
  /** Camera drift lerp toward the cursor. */
  cameraLerp: 0.03,
} as const;
