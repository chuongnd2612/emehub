// Small helpers shared by the ProjectDetail tabs. Nothing here is a design
// decision — it is the handoff's derivation rules, typed against the hub's
// actual knowledge lifecycle.

import type { GlyphFill } from "@/components/ui";
import type { KnowledgeMeta, ProviderKey } from "@/data";
import type { AgentKey } from "@/data";

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
 * refresh amber / Not indexed neutral)".
 *
 * The hub's lifecycle has two states the handoff never drew — `indexing` (an
 * agent is mid-build) and `error` (a build failed). Neither is flattened into
 * one of the three, because showing "Not indexed" for a failed build hides the
 * failure; both get their own label and tone.
 */
export type KnowledgeStatusLabel =
  | "Indexed"
  | "Needs refresh"
  | "Not indexed"
  | "Indexing"
  | "Build failed";

export const knowledgeStatus = (
  knowledge: KnowledgeMeta | null,
): KnowledgeStatusLabel => {
  if (!knowledge) return "Not indexed";
  switch (knowledge.status) {
    case "indexed":
      return knowledge.needsRefresh ? "Needs refresh" : "Indexed";
    case "stale":
      return "Needs refresh";
    case "indexing":
      return "Indexing";
    case "error":
      return "Build failed";
    default:
      return "Not indexed";
  }
};

/** Tone for the labels above. `statusTone` knows the first three already. */
export const knowledgeStatusTone = (
  label: KnowledgeStatusLabel,
): "ok" | "warn" | "danger" | "neutral" => {
  if (label === "Indexed") return "ok";
  if (label === "Needs refresh" || label === "Indexing") return "warn";
  if (label === "Build failed") return "danger";
  return "neutral";
};

/** A knowledge base exists and carries something worth rendering. */
export const isBuilt = (knowledge: KnowledgeMeta | null): boolean =>
  knowledge != null && knowledge.status === "indexed";

/**
 * Handoff › 3. Projects › Overview — the confidence figure switches colour at
 * 85 (green) and 70 (amber); below that it is the danger hue.
 */
export const confidenceToneClass = (confidence: number): string =>
  confidence >= 85 ? "text-ok" : confidence >= 70 ? "text-warn" : "text-danger";

/** Provider glyph fill — Azure "A", Jira "J", GitHub "G" on --githubGlyph. */
export const PROVIDER_GLYPH: Record<
  ProviderKey,
  { fill: GlyphFill; letter: string }
> = {
  ado: { fill: "azure", letter: "A" },
  jira: { fill: "jira", letter: "J" },
  gh: { fill: "github", letter: "G" },
};

/** No connected provider — a neutral tile rather than a guessed brand. */
export const UNKNOWN_GLYPH: { fill: GlyphFill; letter: string } = {
  fill: "neutral",
  letter: "?",
};

