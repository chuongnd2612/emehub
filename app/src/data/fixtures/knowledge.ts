// Prototype `KNOWLEDGE` + `KN_SECTIONS`, typed.

import type { KnowledgeSection, KnowledgeSource } from "../types";

export const KNOWLEDGE_SOURCES: KnowledgeSource[] = [
  { id: "KB-101", projectId: "PRJ-01", title: "Surveyor Web — architecture overview", type: "Markdown", size: "42 KB", chunks: 186, updated: "2h ago", scope: "Surveyor Web", indexed: true },
  { id: "KB-102", projectId: "PRJ-01", title: "Playwright test conventions", type: "Markdown", size: "18 KB", chunks: 74, updated: "2h ago", scope: "Surveyor Web", indexed: true },
  { id: "KB-103", projectId: "PRJ-01", title: "Inspection domain glossary", type: "Document", size: "310 KB", chunks: 220, updated: "yesterday", scope: "Surveyor Web", indexed: true },
  { id: "KB-104", projectId: "PRJ-01", title: "Design system reference", type: "URL", size: "—", chunks: 96, updated: "3d ago", scope: "Surveyor Web", indexed: true },
  { id: "KB-110", projectId: "PRJ-02", title: "Surveyor Mobile release checklist", type: "Markdown", size: "11 KB", chunks: 38, updated: "5h ago", scope: "Surveyor Mobile", indexed: true },
  { id: "KB-111", projectId: "PRJ-02", title: "Offline sync behaviour notes", type: "Document", size: "96 KB", chunks: 64, updated: "1w ago", scope: "Surveyor Mobile", indexed: true },
  { id: "KB-120", projectId: "PRJ-03", title: "Ledger API — OpenAPI schema", type: "File", size: "640 KB", chunks: 412, updated: "1h ago", scope: "Ledger API", indexed: true },
  { id: "KB-121", projectId: "PRJ-03", title: "Reconciliation runbook", type: "Markdown", size: "26 KB", chunks: 88, updated: "yesterday", scope: "Ledger API", indexed: true },
  { id: "KB-130", projectId: "PRJ-04", title: "Atlas Portal SSO integration guide", type: "URL", size: "—", chunks: 52, updated: "4d ago", scope: "Atlas Portal", indexed: true },
  { id: "KB-140", projectId: "PRJ-05", title: "Ticket Executor prompt library", type: "Markdown", size: "34 KB", chunks: 0, updated: "20m ago", scope: "Ticket Executor", indexed: false },
  { id: "KB-150", projectId: "PRJ-06", title: "Nova Billing VAT rules", type: "Document", size: "188 KB", chunks: 132, updated: "2d ago", scope: "Nova Billing", indexed: true },
];

/** "What the agents learned" — the four accordion sections on the detail page. */
export const KNOWLEDGE_SECTIONS: KnowledgeSection[] = [
  {
    key: "arch",
    label: "Architecture & modules",
    body: "Feature-sliced React app. Routing lives in src/app/routes, shared domain logic in src/entities, and every inspection screen composes primitives from src/shared/ui. API access goes through a single generated client — agents reuse it instead of writing fetch calls.",
  },
  {
    key: "conv",
    label: "Test conventions",
    body: "Specs mirror the route tree under tests/e2e. Each spec opens with a fixture-scoped login, never a UI login. Assertions use web-first expect() with no explicit waits. Data is seeded through the API and torn down in afterEach.",
  },
  {
    key: "po",
    label: "Page objects & selectors",
    body: "All selectors are data-testid based and centralised in page objects — no CSS or text selectors in specs. Q-Agent reuses 22 existing page objects before generating a new one.",
  },
  {
    key: "env",
    label: "Environments & test data",
    body: "Three environments: dev, staging and a nightly ephemeral preview. Staging is the default target for generated runs. Seed users live in fixtures/users.json and are rotated weekly.",
  },
];
