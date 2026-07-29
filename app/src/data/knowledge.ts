// Knowledge — per-project and per-repo knowledge METADATA.
//
//   GET /projects/{key}/knowledge              getProjectKnowledge
//   GET /projects/{key}/repos/{repo}/knowledge getRepoKnowledge
//
// Both answer `KnowledgeOut`: the lifecycle row (status, confidence, version,
// framework, lastIndexed) plus the `knowledge` blob the agent reported.
// A project that has never been indexed has no row at all and the hub answers
// **404** — that is the "Not indexed" state, not an error.
//
// ## What the hub will never do, and why two functions here stay stubs
//
// ROADMAP.md Phase 4: the hub owns knowledge *metadata* only; building a
// knowledge base is the agent's job. Building means cloning the repository and
// running `project-bootstrap` through the Claude CLI, which needs a filesystem
// and a credential on disk. The hub has neither, and handing out the repository
// PAT to make it possible is exactly what CLAUDE.md forbids. The agent builds on
// its own host and reports the outcome with
// `PUT /projects/{key}/repos/{repo}/knowledge`.
//
//   • `buildKnowledge` — there is no build endpoint and there is not going to
//     be one. It rejects with the reason; nothing in the UI calls it, and the
//     knowledge tab says who does the building instead of offering a button
//     that cannot work.
//   • `getKnowledgeSources` — there is no knowledge-source resource. Nothing in
//     the hub stores the handoff's source table (icon, title, type, size,
//     chunks, scope, state). It resolves to `[]` and the tab renders a notice
//     rather than a table of fixtures pretending to be live rows.
//
// `getKnowledgeSections` IS real: the blob carries `architecture`, `locator`,
// `pageObjects` / `selectors` / `routes`, `environments` and `businessEntities`,
// so "What the agents learned" renders what an agent actually learned.

import { api, ApiError } from "@/lib/api";
import { relativeTime } from "./humanize";
import type {
  KnowledgeBody,
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

/**
 * STUB (deliberate, not an oversight): the hub does not build knowledge bases.
 *
 * Cloning the repository and running `project-bootstrap` through the Claude CLI
 * happens on the agent host; the hub only records the result via
 * `PUT /projects/{key}/repos/{repo}/knowledge` (ROADMAP.md Phase 4). This
 * rejects with that reason so a future caller cannot mistake it for a no-op —
 * and nothing in the UI calls it today.
 */
export const buildKnowledge = (_projectKey: string): Promise<never> =>
  Promise.reject(
    new Error(
      "EmeHub records knowledge, it does not build it — the agent clones the " +
        "repository on its own host and reports the result back.",
    ),
  );
