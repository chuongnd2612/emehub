// The typed data layer — Handoff › State Management › "Data fetching
// (production)".
//
// This file is a **barrel and nothing else**. Every function lives in the
// per-resource module named after what it fetches, and this re-exports them, so
// the public API screens import (`@/data`) is unchanged by the split. Screens
// must import from HERE, never from a resource module or `data/fixtures/*`
// directly.
//
//   types.ts        the wire types
//   auth.ts         sessions, API keys
//   credentials.ts  LIVE — real .credentials.json parsing + the stored credential
//   models.ts       LIVE — per-user Claude model preferences
//   connections.ts  provider connections, integrations, PROVIDERS
//   projects.ts     LIVE — the registry + project configuration
//   knowledge.ts    LIVE — knowledge metadata + the learned sections
//   tickets.ts      LIVE — tickets (server-side filtered), the schema, sync
//   people.ts       LIVE — member accounts + invite
//   overview.ts     activity feed, KPI tiles, product cards
//   agents.ts       LIVE — the launch registry (GET /agents)
//
// The split exists so later slices can each own one module without colliding.
// Identity, projects, knowledge and tickets are real calls through `@/lib/api`;
// the rest still resolves from `data/fixtures/` behind a `// STUB:` comment
// naming the endpoint that will replace it.
//
// `getKnowledgeSources` used to live here as a stub that would never become an
// endpoint. It is gone with the source table it fed (#191) — the hub has no
// knowledge-source resource and is not getting one.
//
// (`buildKnowledge` used to be a stub too. ADR 0007 made it real: the hub clones
// the repository and runs `project-bootstrap` itself.)
//
// CLAUDE.md: "Where an endpoint does not exist, stub it behind the typed data
// layer — and say so in your response. Never invent an API route silently."

// `timing.ts` is gone (#191). Its `after()` / READ_DELAY_MS were scaffolding
// that made a fixture read feel like a request; the last stubs using them went
// with the screens that rendered them.
export * from "./types";
export * from "./agents";
export * from "./auth";
export * from "./credentials";
export * from "./models";
export * from "./connections";
export * from "./projects";
export * from "./knowledge";
export * from "./savedQueries";
export * from "./ticketSource";
export * from "./tickets";
export * from "./people";
export * from "./overview";
