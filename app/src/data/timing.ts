// Shared plumbing for the stub data layer.
//
// Every resource module resolves from `data/fixtures/` after the dwell the
// Handoff › "Async behaviours" table specifies, so screens see the same
// Promise-shaped API they will see once the real endpoints land.
//
// Per-resource dwells live with their resource (`IMPORT_DELAY_MS` in
// `tickets.ts`, `TEST_CONNECTION_DELAY_MS` in `connections.ts`,
// `CREDENTIAL_DELAY_MS` in `credentials.ts`) so a module can be swapped to a
// real call without touching anything shared.

/** Reads resolve instantly in the prototype; kept so screens still await. */
export const READ_DELAY_MS = 0;

export const after = <T>(value: T, ms: number): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));
