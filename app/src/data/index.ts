// The typed data layer — Handoff › State Management › "Data fetching
// (production)".
//
// This file is a **barrel and nothing else**. Every function lives in the
// per-resource module named after what it fetches, and this re-exports them, so
// the public API screens import (`@/data`) is unchanged by the split. Screens
// must import from HERE, never from a resource module or `data/fixtures/*`
// directly.
//
//   timing.ts       shared `after()` + READ_DELAY_MS
//   types.ts        the wire types
//   auth.ts         sessions, API keys
//   credentials.ts  real .credentials.json parsing + the credential stubs
//   connections.ts  provider connections, integrations, PROVIDERS
//   projects.ts     the project registry
//   knowledge.ts    per-project knowledge sources and sections
//   tickets.ts      tickets, the filter schema, import
//   people.ts       members, roles, invitations
//   overview.ts     activity feed, KPI tiles, product cards
//
// The split exists so later slices can each own one module without colliding.
// Most functions are still STUBS resolving from `data/fixtures/` — each carries
// a `// STUB:` comment naming the endpoint that will replace it. Swapping a stub
// for a real call (through `@/lib/api`) is deliberately a later slice.
//
// CLAUDE.md: "Where an endpoint does not exist, stub it behind the typed data
// layer — and say so in your response. Never invent an API route silently."

// `timing.ts` is deliberately NOT re-exported: `after()` and READ_DELAY_MS are
// scaffolding for the stubs, not public API, and they disappear when the last
// stub becomes a real call.
export * from "./types";
export * from "./auth";
export * from "./credentials";
export * from "./connections";
export * from "./projects";
export * from "./knowledge";
export * from "./tickets";
export * from "./people";
export * from "./overview";
