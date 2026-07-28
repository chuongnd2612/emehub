// Handoff › Screens › "App shell" background stack, layer z-index:1, and
// Handoff › Interactions & Behavior › "3D constellation (background)".
//
// Owns nothing but lifecycle: the scene itself lives in `./scene`. Renders no
// React DOM — it appends its OWN fixed container to `document.body` and keeps
// it for as long as the field is on.
//
// Why it owns the container rather than borrowing one from a screen: the field
// is global (the landing view and the app shell both sit over it), so parenting
// the canvas to a screen-owned div would strand it the moment that screen
// unmounted. Mount this component ONCE, above the router.

import { useEffect, useRef } from "react";

import { useAppearance } from "@/store/appearance";
import { createConstellation, type ConstellationHandle } from "./scene";

const CONTAINER_ID = "constellation-root";

/**
 * The fixed, pointer-transparent layer the renderer draws into.
 *
 * Prepended to `<body>` so it precedes `#root` in DOM order: the two ambient
 * blooms are also `z-index:1`, and the handoff stacks them ABOVE the canvas
 * (§ 0 background stack, layers 2 → 3 → 4). Equal z-index means DOM order
 * decides, so the canvas has to come first.
 */
function createContainer(): HTMLElement {
  const el = document.createElement("div");
  el.id = CONTAINER_ID;
  el.setAttribute("aria-hidden", "true");
  el.style.position = "fixed";
  el.style.inset = "0";
  el.style.zIndex = "1";
  el.style.pointerEvents = "none";
  document.body.prepend(el);
  return el;
}

/**
 * The ambient WebGL constellation field.
 *
 * No props: everything it needs (`fx3d`, `accent`, `mode`) comes from the
 * appearance store. Mount it once, above the router.
 */
export function Constellation(): null {
  const fx3d = useAppearance((s) => s.fx3d);
  const accent = useAppearance((s) => s.accent);
  const mode = useAppearance((s) => s.mode);

  const handleRef = useRef<ConstellationHandle | null>(null);
  // Read inside the create effect without making it a dependency — accent and
  // mode are applied live by the two effects below, never by re-creating.
  const accentRef = useRef(accent);
  const modeRef = useRef(mode);
  accentRef.current = accent;
  modeRef.current = mode;

  // Create / tear down. `fx3d` is the only trigger — Handoff § 10: "the
  // Settings toggle disposes the renderer and clears the container, and
  // re-creates it when switched back."
  useEffect(() => {
    if (!fx3d) return;

    const container = createContainer();
    let handle: ConstellationHandle | null = null;
    try {
      handle = createConstellation(container, {
        accent: accentRef.current,
        mode: modeRef.current,
      });
    } catch (err) {
      // No WebGL context (headless, blocklisted GPU) — degrade to no field.
      console.error("constellation init failed", err);
    }
    handleRef.current = handle;

    return () => {
      handle?.dispose();
      handleRef.current = null;
      container.remove();
    };
  }, [fx3d]);

  // Live accent swap — no teardown.
  useEffect(() => {
    handleRef.current?.setAccent(accent);
  }, [accent]);

  // Live mode swap — blending + palette.
  useEffect(() => {
    handleRef.current?.setMode(mode);
  }, [mode]);

  return null;
}

export default Constellation;
