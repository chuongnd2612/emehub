// Small helpers shared by the ProjectDetail tabs. Nothing here is a design
// decision — it is the handoff's derivation rules, typed against the hub's
// actual knowledge lifecycle.

import type { GlyphFill } from "@/components/ui";
import type { KnowledgeMeta, ProviderKey } from "@/data";
import type { AgentKey } from "@/data";

/**
 * Handoff › 3. Projects — the detail tabs, in order.
 *
 * This table is the SINGLE SOURCE for the tab vocabulary: since #219 the tab is
 * a path segment (`/app/projects/:projectId/<key>`), so the first element of
 * each pair is simultaneously the tab key and the URL segment. The router does
 * not hardcode the slugs — it takes `:tab` and validates it through
 * `isProjectTab` — so adding a tab here adds its route.
 *
 * The route segment for Repository is therefore `repos`, the existing key,
 * rather than the handoff's word "repository": the handoff's copy is final for
 * the *label* (second element, unchanged), and keeping key === segment avoids a
 * second slug↔key map that can drift. ADR 0011's own route table writes `repos`.
 *
 * **Six entries since #221**, not the handoff's five. `tickets` is a real view of
 * the project now — `getTicketPage({ projectId })` against the parameter the API
 * has always had — and containment puts it here, before Settings: it is one of
 * the things a user comes to a project to *read*, not something they come to
 * configure. Adding the row was the whole change — the router validates `:tab`
 * through `isProjectTab`, and the sidebar tree renders its rows straight off this
 * table, so both picked the tab up without a line of their own.
 */
export const PROJECT_TABS = [
  ["overview", "Overview"],
  ["knowledge", "Project knowledge"],
  ["repos", "Repository"],
  ["agents", "Agents"],
  ["tickets", "Tickets"],
  ["settings", "Settings"],
] as const;

export type ProjectTab = (typeof PROJECT_TABS)[number][0];

export const isProjectTab = (v: string | null | undefined): v is ProjectTab =>
  PROJECT_TABS.some(([key]) => key === v);

/** The tab a project opens on when the URL names none. */
export const DEFAULT_PROJECT_TAB: ProjectTab = "overview";

/**
 * The canonical URL of a project, or of one of its tabs.
 *
 * `projectId` is the project's GUID (#150); a key-shaped value still resolves
 * server-side, so older links keep working.
 */
export const projectPath = (
  projectId: string,
  tab: ProjectTab = DEFAULT_PROJECT_TAB,
): string => `/app/projects/${encodeURIComponent(projectId)}/${tab}`;

/**
 * Where a ticket that belongs to no project lives — the Unassigned bucket
 * (#217, ADR 0011 §4). It is not inside any project, so it gets its own
 * address at workspace level rather than a fake project id.
 *
 * `/app/unassigned/tickets` is the list (#221 renders it, backed by
 * `GET /tickets?unassigned=true`); `/app/unassigned/tickets/:externalId` is a
 * ticket's detail and resolves today.
 */
export const UNASSIGNED_TICKETS_PATH = "/app/unassigned/tickets";

/**
 * One work item's detail page, addressed inside the project that owns it (#221).
 *
 * `?source=` is deliberately still here, and this is the one place in the ticket
 * flow that keeps it: ticket identity in the hub is `(providerKind, externalId)`,
 * so an Azure DevOps `1234` and a GitHub `1234` are two different rows and the
 * path alone cannot say which (`router.tsx`, #219). It is a **disambiguator on
 * one row**, not a provider switch on a list — the thing ADR 0011 §3 removed —
 * and the list route itself carries no `?source=` at all.
 */
export const projectTicketPath = (
  projectId: string,
  externalId: string,
  provider: ProviderKey | null,
): string => {
  const path = `${projectPath(projectId, "tickets")}/${encodeURIComponent(externalId)}`;
  return provider ? `${path}?source=${provider}` : path;
};

/** The same, for a work item in the Unassigned bucket. */
export const unassignedTicketPath = (
  externalId: string,
  provider: ProviderKey | null,
): string => {
  const path = `${UNASSIGNED_TICKETS_PATH}/${encodeURIComponent(externalId)}`;
  return provider ? `${path}?source=${provider}` : path;
};

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
): KnowledgeStatusLabel =>
  knowledge
    ? knowledgeStatusLabelFor(knowledge.status, knowledge.needsRefresh)
    : "Not indexed";

/**
 * The same vocabulary, from the raw status string a **list** row carries.
 *
 * `GET /projects` returns `summary.knowledgeStatus` and no `KnowledgeMeta` at
 * all (the list read costs one request, not 3N+1), so the Overview comparison
 * table has only the string. It reads it through here rather than mapping the
 * statuses a second time — a project that says "Build failed" on its own screen
 * must not say "Needs refresh" on Overview.
 */
export const knowledgeStatusLabelFor = (
  status: string | undefined,
  needsRefresh = false,
): KnowledgeStatusLabel => {
  switch (status) {
    case "indexed":
      return needsRefresh ? "Needs refresh" : "Indexed";
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

