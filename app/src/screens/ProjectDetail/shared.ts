// Small helpers shared by the ProjectDetail tabs. Nothing here is a design
// decision — it is the handoff's derivation rules, typed.

import type { GlyphFill } from "@/components/ui";
import type { AgentKey, KnowledgeSourceType, Project, ProviderKey } from "@/data";

/** Handoff › 3. Projects — the five detail tabs, in order. */
export const PROJECT_TABS = [
  ["overview", "Overview"],
  ["knowledge", "Project knowledge"],
  ["repos", "Repository"],
  ["agents", "Agents"],
  ["settings", "Settings"],
] as const;

export type ProjectTab = (typeof PROJECT_TABS)[number][0];

export const isProjectTab = (v: string | null): v is ProjectTab =>
  PROJECT_TABS.some(([key]) => key === v);

/** Handoff › "Agent tag pills (Q-Agent, D-Agent)". */
export const AGENT_LABEL: Record<AgentKey, string> = {
  q: "Q-Agent",
  d: "D-Agent",
};

export const agentTone = (agent: AgentKey): "qagent" | "dagent" =>
  agent === "q" ? "qagent" : "dagent";

/**
 * Handoff › 3. Projects — "knowledge status pill (Indexed green / Needs
 * refresh amber / Not indexed neutral)". `built` folds in a knowledge base
 * created during this session by the empty-state CTA.
 */
export type KnowledgeStatusLabel = "Indexed" | "Needs refresh" | "Not indexed";

export const knowledgeStatus = (
  project: Project,
  built: boolean,
): KnowledgeStatusLabel =>
  built ? (project.needsRefresh ? "Needs refresh" : "Indexed") : "Not indexed";

/**
 * Handoff › 3. Projects › Overview — the confidence figure switches colour at
 * 85 (green) and 70 (amber); below that it is the danger hue.
 */
export const confidenceToneClass = (confidence: number): string =>
  confidence >= 85 ? "text-ok" : confidence >= 70 ? "text-warn" : "text-danger";

/** Provider glyph fill — Azure "A", Jira "J", GitHub "G" on --githubGlyph. */
export const PROVIDER_GLYPH: Record<ProviderKey, { fill: GlyphFill; letter: string }> = {
  ado: { fill: "azure", letter: "A" },
  jira: { fill: "jira", letter: "J" },
  gh: { fill: "github", letter: "G" },
};

/**
 * Knowledge source type → icon + tinted chip classes. The prototype's per-type
 * hexes map onto existing tokens: Markdown purple, Document amber, URL cyan,
 * File neutral.
 */
export const SOURCE_TYPE_CHIP: Record<
  KnowledgeSourceType,
  { icon: "doc" | "link" | "upload"; className: string }
> = {
  Markdown: { icon: "doc", className: "bg-qagent-tint text-brand-soft" },
  Document: { icon: "doc", className: "bg-warn-tint text-warn" },
  URL: { icon: "link", className: "bg-info-tint text-cyan-soft" },
  File: { icon: "upload", className: "bg-neutral-tint text-neutral" },
};

export const SOURCE_TYPES: (KnowledgeSourceType | "All")[] = [
  "All",
  "Markdown",
  "Document",
  "URL",
  "File",
];

/** Handoff table cell — "186 chunks" / "not chunked". */
export const chunkLabel = (chunks: number): string =>
  chunks ? `${chunks} chunks` : "not chunked";
