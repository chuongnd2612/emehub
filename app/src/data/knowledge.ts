// Knowledge — per-project and per-repo knowledge METADATA.
//
//   GET  /projects/{key}/knowledge                    getProjectKnowledge
//   GET  /projects/{key}/repos/{repo}/knowledge       getRepoKnowledge
//   POST /projects/{key}/repos/{repo}/knowledge/build buildKnowledge
//
// The reads answer `KnowledgeOut`: the lifecycle row (status, confidence,
// version, framework, lastIndexed) plus the `knowledge` blob. A project that has
// never been indexed has no row at all and the hub answers **404** — that is the
// "Not indexed" state, not an error.
//
// ## Building
//
// ADR 0007 reversed the Phase 4 split: the hub clones the repository, runs
// `project-bootstrap` through the Claude CLI and writes the artefacts itself.
// `buildKnowledge` is therefore a real call now. It returns `202` with the row
// already at `indexing`; the caller polls `getRepoKnowledge` until the status
// leaves `indexing`, then reads `lastError` on `error`. Calling it twice while a
// build is in flight is safe and returns the same `indexing` row.
//
// `getKnowledgeSources` is still a stub: there is no knowledge-source resource.
// Nothing in the hub stores the handoff's source table (icon, title, type, size,
// chunks, scope, state). It resolves to `[]` and the tab renders a notice rather
// than a table of fixtures pretending to be live rows.
//
// `getKnowledgeSections` IS real: the blob carries `architecture`, `locator`,
// `pageObjects` / `selectors` / `routes`, `environments` and `businessEntities`,
// so "What the agents learned" renders what an agent actually learned.

import { api, ApiError } from "@/lib/api";
import { relativeTime } from "./humanize";
import type {
  KnowledgeBody,
  KnowledgeBuildProgress,
  KnowledgeBuildStage,
  KnowledgeMeta,
  KnowledgeSection,
  KnowledgeSource,
  KnowledgeWireStatus,
} from "./types";

/* ── Wire shape ──────────────────────────────────────────────────────────── */

interface KnowledgeWire {
  id: number;
  key: string;
  projectKey?: string;
  name?: string;
  provider?: string;
  repo?: string;
  framework?: string;
  status?: string;
  confidence?: number;
  version?: string;
  needsRefresh?: boolean;
  lastIndexed?: string | null;
  knowledge?: Record<string, unknown>;
  docPath?: string;
  lastError?: string;
  shared?: boolean;
  buildStage?: string;
  buildStep?: number;
  buildTotalSteps?: number;
  buildMessage?: string;
  buildStartedAt?: string | null;
  buildOrphaned?: boolean;
}

const STATUSES: KnowledgeWireStatus[] = [
  "not_indexed",
  "indexing",
  "indexed",
  "stale",
  "error",
];

const toStatus = (raw: string | undefined): KnowledgeWireStatus =>
  STATUSES.find((s) => s === raw) ?? "not_indexed";

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number => (typeof v === "number" ? v : 0);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] =>
  list(v).filter((x): x is string => typeof x === "string");

/**
 * Decode the blob. QAgent writes it camelCased (`pageObjects`), but it is a
 * free-form JSON column and a hand-written row may be snake_cased — both are
 * read, neither is required.
 */
const toBody = (raw: Record<string, unknown> | undefined): KnowledgeBody => {
  const k = raw ?? {};
  return {
    branch: str(k.branch),
    stack: strings(k.stack),
    architecture: str(k.architecture),
    domain: str(k.domain),
    locator: str(k.locator),
    assets: num(k.assets),
    pageObjects: num(k.pageObjects ?? k.page_objects),
    fixtures: num(k.fixtures),
    utilities: strings(k.utilities),
    baseUrl: str(k.baseUrl ?? k.base_url),
    routes: list(k.routes),
    selectors: list(k.selectors),
    environments: list(k.environments) as KnowledgeBody["environments"],
    businessEntities: strings(k.businessEntities ?? k.business_entities),
  };
};

/** The stage vocabulary, in the order the hub runs them. */
export const KNOWLEDGE_BUILD_STAGES: KnowledgeBuildStage[] = [
  "queued",
  "resolving",
  "cloning",
  "analyzing",
  "writing",
];

/**
 * Handoff voice — present participle, sentence case. These are the *fallback*
 * lines: the hub sends its own `buildMessage`, which during `analyzing` is
 * whatever Claude is doing at that moment, and that always wins.
 */
export const KNOWLEDGE_BUILD_LABELS: Record<KnowledgeBuildStage, string> = {
  queued: "Waiting for a build slot",
  resolving: "Resolving the project configuration",
  cloning: "Cloning the repository",
  analyzing: "Reading the repository with Claude",
  writing: "Writing the knowledge base",
};

const toStage = (raw: string | undefined): KnowledgeBuildStage | "" =>
  KNOWLEDGE_BUILD_STAGES.find((s) => s === raw) ?? "";

/**
 * Decode the progress half of the row (issue #68).
 *
 * `totalSteps` falls back to the length of the stage list rather than to a
 * literal, so a hub that grows a sixth stage does not silently render "3 of 5".
 */
const toBuild = (wire: KnowledgeWire): KnowledgeBuildProgress => ({
  stage: toStage(wire.buildStage),
  step: num(wire.buildStep),
  totalSteps: num(wire.buildTotalSteps) || KNOWLEDGE_BUILD_STAGES.length,
  message: wire.buildMessage ?? "",
  startedAt: wire.buildStartedAt ?? null,
  orphaned: wire.buildOrphaned === true,
});

const toMeta = (wire: KnowledgeWire): KnowledgeMeta => ({
  id: wire.id,
  key: wire.key,
  projectKey: wire.projectKey ?? "",
  repo: wire.repo ?? "",
  name: wire.name ?? "",
  provider: wire.provider ?? "",
  framework: wire.framework ?? "",
  status: toStatus(wire.status),
  confidence: num(wire.confidence),
  version: wire.version || "v1",
  needsRefresh: wire.needsRefresh === true,
  lastIndexed: wire.lastIndexed ?? null,
  lastIndexedLabel: relativeTime(wire.lastIndexed ?? null),
  docPath: wire.docPath ?? "",
  lastError: wire.lastError ?? "",
  shared: wire.shared === true,
  body: toBody(wire.knowledge),
  build: toBuild(wire),
});

/** 404 means "no knowledge base", which is a state, not a failure. */
const orNull = async (
  promise: Promise<KnowledgeWire>,
): Promise<KnowledgeMeta | null> => {
  try {
    return toMeta(await promise);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
};

/* ── Reads ───────────────────────────────────────────────────────────────── */

/** GET /projects/{key}/knowledge — the project-level row, or null. */
export const getProjectKnowledge = (
  projectKey: string,
): Promise<KnowledgeMeta | null> =>
  orNull(
    api.get<KnowledgeWire>(
      `/projects/${encodeURIComponent(projectKey)}/knowledge`,
    ),
  );

/**
 * GET /projects/{key}/repos/{repo}/knowledge — the per-repo row.
 *
 * The hub falls back to the project-level row when the repo has none of its
 * own, so this is the right read whenever a repository is known.
 */
export const getRepoKnowledge = (
  projectKey: string,
  repo: string,
): Promise<KnowledgeMeta | null> =>
  repo
    ? orNull(
        api.get<KnowledgeWire>(
          `/projects/${encodeURIComponent(
            projectKey,
          )}/repos/${encodeURIComponent(repo)}/knowledge`,
        ),
      )
    : getProjectKnowledge(projectKey);

/* ── "What the agents learned" ───────────────────────────────────────────── */

const environmentLine = (env: {
  name?: string;
  baseUrl?: string;
  notes?: string;
}): string =>
  [env?.name, env?.baseUrl, env?.notes]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" — ");

const plural = (n: number, one: string, many = `${one}s`): string =>
  `${n} ${n === 1 ? one : many}`;

/**
 * Turn the reported blob into the handoff's accordion sections.
 *
 * A section is emitted only when the field behind it carries something, so an
 * agent that reported a thin blob produces a short accordion rather than four
 * headings over four blanks. The first four labels are the handoff's; the fifth
 * exists because the blob does.
 */
export const knowledgeSections = (
  knowledge: KnowledgeMeta | null,
): KnowledgeSection[] => {
  if (!knowledge) return [];
  const b = knowledge.body;
  const sections: KnowledgeSection[] = [];

  if (b.architecture || b.stack.length) {
    const stack = b.stack.length ? `Stack: ${b.stack.join(", ")}.` : "";
    sections.push({
      key: "arch",
      label: "Architecture & modules",
      body: [b.architecture, stack].filter(Boolean).join(" "),
    });
  }

  if (b.locator || knowledge.framework) {
    const framework = knowledge.framework
      ? `Framework: ${knowledge.framework}.`
      : "";
    sections.push({
      key: "conv",
      label: "Test conventions",
      body: [b.locator, framework].filter(Boolean).join(" "),
    });
  }

  if (b.pageObjects || b.selectors.length || b.routes.length) {
    sections.push({
      key: "po",
      label: "Page objects & selectors",
      body:
        `${plural(b.pageObjects, "page object")}, ` +
        `${plural(b.selectors.length, "recorded selector")} and ` +
        `${plural(b.routes.length, "route")} are indexed. ` +
        "Agents reuse these before generating anything new.",
    });
  }

  const envs = b.environments.map(environmentLine).filter(Boolean);
  if (envs.length || b.baseUrl || b.fixtures) {
    const base = b.baseUrl ? `Base URL: ${b.baseUrl}.` : "";
    const fixtures = b.fixtures
      ? `${plural(b.fixtures, "fixture")} indexed.`
      : "";
    sections.push({
      key: "env",
      label: "Environments & test data",
      body: [envs.join(" · "), base, fixtures].filter(Boolean).join(" "),
    });
  }

  if (b.domain || b.businessEntities.length) {
    const entities = b.businessEntities.length
      ? `Entities: ${b.businessEntities.join(", ")}.`
      : "";
    sections.push({
      key: "domain",
      label: "Domain",
      body: [b.domain, entities].filter(Boolean).join(" "),
    });
  }

  return sections;
};

/**
 * The accordion, fetched. A screen that already holds the `KnowledgeMeta`
 * should call {@link knowledgeSections} directly instead of re-reading.
 */
export const getKnowledgeSections = async (
  projectKey: string,
  repo = "",
): Promise<KnowledgeSection[]> =>
  knowledgeSections(await getRepoKnowledge(projectKey, repo));

/* ── Building ────────────────────────────────────────────────────────────── */

/**
 * POST /projects/{key}/repos/{repo}/knowledge/build — start a build on the hub.
 *
 * Resolves as soon as the row is `indexing` (HTTP 202), not when the build
 * finishes: a build clones the repository and runs the Claude CLI against it,
 * which is minutes of work. Poll {@link getRepoKnowledge} until `status` leaves
 * `indexing` — `indexed` carries the new blob, `error` carries `lastError`,
 * written for a human and safe to display verbatim.
 *
 * Requesting a build that is already running is safe: the hub returns the same
 * `indexing` row without starting a second one.
 */
export const buildKnowledge = (
  projectKey: string,
  repo: string,
): Promise<KnowledgeMeta> =>
  api
    .post<KnowledgeWire>(
      `/projects/${encodeURIComponent(projectKey)}/repos/${encodeURIComponent(
        repo,
      )}/knowledge/build`,
      {},
    )
    .then(toMeta);

/* ── Stubs the hub cannot honour ─────────────────────────────────────────── */

/**
 * STUB (no resource, by design): the hub has no knowledge-source registry.
 *
 * The handoff's source table — icon, title, type, size, chunks, scope, state —
 * describes a document store nothing in the API models. Resolving to `[]` keeps
 * the call site honest: the knowledge tab explains the gap with a notice
 * instead of rendering fixtures as if they were live rows.
 */
export const getKnowledgeSources = (
  _projectKey: string,
): Promise<KnowledgeSource[]> => Promise.resolve([]);
