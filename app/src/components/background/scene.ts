// The WebGL constellation field — framework-free so the React layer only has to
// own lifecycle. Maths is verbatim from the handoff / prototype.
//
// Handoff › Interactions & Behavior › "3D constellation (background)".

import {
  AdditiveBlending,
  BufferGeometry,
  Clock,
  Color,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
  NormalBlending,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";

import type { Accent, Mode } from "@/store/appearance";
import { ACCENT_HEX, SCENE, scenePalette } from "./palette";

export interface ConstellationHandle {
  /** Swap the accent colour live — no teardown. */
  setAccent: (accent: Accent) => void;
  /** Swap blending + palette live — no teardown. */
  setMode: (mode: Mode) => void;
  /** Cancel the frame, drop listeners, dispose every GPU resource, empty the container. */
  dispose: () => void;
}

export interface ConstellationOptions {
  accent: Accent;
  mode: Mode;
  /** Halves the particle counts. Defaults to the `prefers-reduced-motion` query. */
  reducedMotion?: boolean;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function createConstellation(
  container: HTMLElement,
  options: ConstellationOptions,
): ConstellationHandle {
  const reduce = options.reducedMotion ?? prefersReducedMotion();
  const width = () => window.innerWidth;
  const height = () => window.innerHeight;

  const scene = new Scene();
  const camera = new PerspectiveCamera(
    SCENE.cameraFov,
    width() / height(),
    SCENE.cameraNear,
    SCENE.cameraFar,
  );
  camera.position.z = SCENE.cameraZ;

  const renderer = new WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width(), height());
  const canvas = renderer.domElement;
  canvas.style.display = "block";
  // Never intercept clicks — the field sits under the whole app.
  canvas.style.pointerEvents = "none";
  container.appendChild(canvas);

  let palette = scenePalette(options.mode);
  let lightMode = options.mode === "light";

  // ── Nodes ────────────────────────────────────────────────────────────────
  const nodeCount = reduce ? SCENE.nodeCountReduced : SCENE.nodeCount;
  const points: Vector3[] = [];
  const base = new Float32Array(nodeCount);
  for (let i = 0; i < nodeCount; i++) {
    points.push(
      new Vector3(
        (Math.random() - 0.5) * SCENE.nodeSpread.x,
        (Math.random() - 0.5) * SCENE.nodeSpread.y,
        (Math.random() - 0.5) * SCENE.nodeSpread.z,
      ),
    );
    base[i] = 0.42 + Math.random() * 0.4;
  }

  const accentCol = new Color(ACCENT_HEX[options.accent]);
  const silver = new Color(palette.silver);
  const steel = new Color(palette.steel);
  const lineCol = new Color(palette.line);
  /** Colour cycle: [accent, silver, steel]. */
  const pick = (i: number): Color =>
    i % 3 === 0 ? accentCol : i % 3 === 1 ? silver : steel;

  const nodeIdx = new Uint8Array(nodeCount);
  for (let i = 0; i < nodeCount; i++) nodeIdx[i] = (Math.random() * 3) | 0;

  const nodePos = new Float32Array(nodeCount * 3);
  const nodeColArr = new Float32Array(nodeCount * 3);
  for (let i = 0; i < nodeCount; i++) {
    nodePos[i * 3] = points[i].x;
    nodePos[i * 3 + 1] = points[i].y;
    nodePos[i * 3 + 2] = points[i].z;
  }
  const nodeGeom = new BufferGeometry();
  nodeGeom.setAttribute("position", new Float32BufferAttribute(nodePos, 3));
  const nodeColAttr = new Float32BufferAttribute(nodeColArr, 3);
  nodeGeom.setAttribute("color", nodeColAttr);
  const nodeMat = new PointsMaterial({
    size: SCENE.nodeSize,
    transparent: true,
    opacity: palette.nodeOpacity,
    vertexColors: true,
    blending: lightMode ? NormalBlending : AdditiveBlending,
    depthWrite: false,
  });
  const nodes = new Points(nodeGeom, nodeMat);

  // ── Edges: every pair closer than 250 units ──────────────────────────────
  const edges: [number, number][] = [];
  const linePos: number[] = [];
  const lineColArr: number[] = [];
  for (let i = 0; i < nodeCount; i++) {
    for (let j = i + 1; j < nodeCount; j++) {
      if (points[i].distanceTo(points[j]) < SCENE.edgeDistance) {
        edges.push([i, j]);
        linePos.push(
          points[i].x,
          points[i].y,
          points[i].z,
          points[j].x,
          points[j].y,
          points[j].z,
        );
        lineColArr.push(0, 0, 0, 0, 0, 0);
      }
    }
  }
  const lineGeom = new BufferGeometry();
  lineGeom.setAttribute("position", new Float32BufferAttribute(linePos, 3));
  const lineColAttr = new Float32BufferAttribute(lineColArr, 3);
  lineGeom.setAttribute("color", lineColAttr);
  const lineMat = new LineBasicMaterial({
    transparent: true,
    opacity: palette.lineOpacity,
    vertexColors: true,
    blending: lightMode ? NormalBlending : AdditiveBlending,
  });
  const lines = new LineSegments(lineGeom, lineMat);

  const group = new Group();
  group.add(lines);
  group.add(nodes);
  scene.add(group);

  // ── Dust ─────────────────────────────────────────────────────────────────
  const dustCount = reduce ? SCENE.dustCountReduced : SCENE.dustCount;
  const dustPos = new Float32Array(dustCount * 3);
  const dustColArr = new Float32Array(dustCount * 3);
  const dustPhase = new Float32Array(dustCount);
  const dustIdx = new Uint8Array(dustCount);
  for (let i = 0; i < dustCount; i++) {
    dustPos[i * 3] = (Math.random() - 0.5) * SCENE.dustSpread.x;
    dustPos[i * 3 + 1] = (Math.random() - 0.5) * SCENE.dustSpread.y;
    dustPos[i * 3 + 2] = (Math.random() - 0.5) * SCENE.dustSpread.z;
    dustPhase[i] = Math.random() * Math.PI * 2;
    dustIdx[i] = (Math.random() * 3) | 0;
  }
  const dustGeom = new BufferGeometry();
  dustGeom.setAttribute("position", new Float32BufferAttribute(dustPos, 3));
  const dustColAttr = new Float32BufferAttribute(dustColArr, 3);
  dustGeom.setAttribute("color", dustColAttr);
  const dustMat = new PointsMaterial({
    size: SCENE.dustSize,
    transparent: true,
    opacity: 0.7,
    vertexColors: true,
    blending: lightMode ? NormalBlending : AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const dust = new Points(dustGeom, dustMat);
  const dustGroup = new Group();
  dustGroup.add(dust);
  scene.add(dustGroup);

  // Float32BufferAttribute copies its input, so write through the attribute's
  // own buffer — never the local arrays used to seed it.
  const nodeColors = nodeColAttr.array as Float32Array;
  const lineColors = lineColAttr.array as Float32Array;
  const dustColors = dustColAttr.array as Float32Array;

  // ── Live setters ─────────────────────────────────────────────────────────
  const setAccent = (accent: Accent): void => {
    accentCol.setHex(ACCENT_HEX[accent]);
  };

  const setMode = (mode: Mode): void => {
    lightMode = mode === "light";
    palette = scenePalette(mode);
    silver.setHex(palette.silver);
    steel.setHex(palette.steel);
    lineCol.setHex(palette.line);
    const blending = lightMode ? NormalBlending : AdditiveBlending;
    nodeMat.blending = blending;
    lineMat.blending = blending;
    dustMat.blending = blending;
    nodeMat.opacity = palette.nodeOpacity;
    lineMat.opacity = palette.lineOpacity;
    nodeMat.needsUpdate = true;
    lineMat.needsUpdate = true;
    dustMat.needsUpdate = true;
  };

  // ── Pointer + resize ─────────────────────────────────────────────────────
  let mx = 0;
  let my = 0;
  let haveMouse = false;
  const onMove = (e: MouseEvent): void => {
    mx = e.clientX / window.innerWidth - 0.5;
    my = e.clientY / window.innerHeight - 0.5;
    haveMouse = true;
  };
  const onResize = (): void => {
    camera.aspect = width() / height();
    camera.updateProjectionMatrix();
    renderer.setSize(width(), height());
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("resize", onResize);

  // ── Loop ─────────────────────────────────────────────────────────────────
  const clock = new Clock();
  const tmp = new Vector3();
  const act = new Float32Array(nodeCount);
  let raf = 0;
  let disposed = false;

  const animate = (): void => {
    raf = requestAnimationFrame(animate);
    if (document.hidden) return;

    const t = clock.getElapsedTime();
    const world = 0.5 + 0.5 * Math.sin(t * 0.25);
    const breathe = 0.5 + 0.5 * Math.sin(t * 0.6);

    group.rotation.y = t * 0.028 + mx * 0.36;
    group.rotation.x = my * 0.24 + Math.sin(t * 0.1) * 0.05;
    dustGroup.rotation.y = t * 0.011 - mx * 0.24;
    dustGroup.rotation.x = Math.sin(t * 0.07) * 0.03 - my * 0.15;
    dustGroup.position.x += (-mx * 80 - dustGroup.position.x) * 0.04;
    dustGroup.position.y += (my * 54 - dustGroup.position.y) * 0.04;
    camera.position.x += (mx * 120 - camera.position.x) * SCENE.cameraLerp;
    camera.position.y += (-my * 80 - camera.position.y) * SCENE.cameraLerp;
    camera.lookAt(scene.position);
    group.updateMatrixWorld();

    // Dust twinkle.
    for (let i = 0; i < dustCount; i++) {
      const tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 1.05 + dustPhase[i]));
      const b = tw * (0.4 + 0.5 * world);
      const c = pick(dustIdx[i]);
      dustColors[i * 3] = c.r * b;
      dustColors[i * 3 + 1] = c.g * b;
      dustColors[i * 3 + 2] = c.b * b;
    }
    dustColAttr.needsUpdate = true;
    dustMat.opacity = palette.dustBase + palette.dustSwing * world;

    // Nodes brighten toward the cursor.
    for (let i = 0; i < nodeCount; i++) {
      tmp.copy(points[i]).applyMatrix4(group.matrixWorld).project(camera);
      let a = 0;
      if (haveMouse) {
        const dx = tmp.x - mx * 2;
        const dy = tmp.y + my * 2;
        const d = Math.sqrt(dx * dx + dy * dy);
        a = Math.max(0, 1 - d / 0.4);
        a *= a;
      }
      act[i] += (a - act[i]) * SCENE.actEase;
      const glow = Math.min(
        1,
        base[i] * (0.5 + 0.18 * world + 0.2 * breathe) + act[i] * 0.9,
      );
      const c = pick(nodeIdx[i]);
      nodeColors[i * 3] = Math.min(1, c.r * glow + act[i] * 0.3);
      nodeColors[i * 3 + 1] = Math.min(1, c.g * glow + act[i] * 0.3);
      nodeColors[i * 3 + 2] = Math.min(1, c.b * glow + act[i] * 0.3);
    }
    nodeColAttr.needsUpdate = true;
    nodeMat.size = SCENE.nodeSize + breathe * 0.7;

    // Edges glow with the mean activation of their endpoints.
    for (let k = 0; k < edges.length; k++) {
      const [a0, a1] = edges[k];
      const em = (act[a0] + act[a1]) * 0.5;
      const b = 0.14 * (0.5 + 0.3 * world + 0.35 * breathe) + em * 0.6;
      const bi = k * 6;
      lineColors[bi] = lineCol.r * b;
      lineColors[bi + 1] = lineCol.g * b;
      lineColors[bi + 2] = lineCol.b * b;
      lineColors[bi + 3] = lineCol.r * b;
      lineColors[bi + 4] = lineCol.g * b;
      lineColors[bi + 5] = lineCol.b * b;
    }
    lineColAttr.needsUpdate = true;

    renderer.render(scene, camera);
  };
  animate();

  const dispose = (): void => {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(raf);
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("resize", onResize);
    scene.remove(group, dustGroup);
    group.clear();
    dustGroup.clear();
    nodeGeom.dispose();
    lineGeom.dispose();
    dustGeom.dispose();
    nodeMat.dispose();
    lineMat.dispose();
    dustMat.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };

  return { setAccent, setMode, dispose };
}
