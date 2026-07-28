// Prototype `state.sharedCreds`, typed. In production these come from the hub
// encrypted at rest — the token field is only ever returned to an admin who
// explicitly reveals it.

import type { SharedCredential } from "../types";

export const SHARED_CREDENTIALS: SharedCredential[] = [
  {
    id: "sc1",
    label: "EMESOFT Team",
    email: "ai-team@emesoft.net",
    subscription: "Claude Max 20×",
    expiresDisplay: "12 Oct 2026",
    daysLeft: 76,
    scopes: ["user:inference", "user:profile"],
    lastRefreshed: "2 hours ago",
    members: 4,
    isDefault: true,
    token: "sk-ant-oat01-x8Kf2mQ9vL4pR7nT1wY6zB3cD5eG0hJ4f2a",
    source: ".claude/.credentials.json · synced",
  },
  {
    id: "sc2",
    label: "EMESOFT QA",
    email: "qa-bot@emesoft.net",
    subscription: "Claude Pro",
    expiresDisplay: "2 Aug 2026",
    daysLeft: 1,
    scopes: ["user:inference"],
    lastRefreshed: "5 days ago",
    members: 2,
    isDefault: false,
    token: "sk-ant-oat01-p0Q9r8S7t6U5v4W3x2Y1z0A9b8C7d6E9c11",
    source: "uploaded · qa.credentials.json",
  },
];

/** Handoff › 6. Claude Settings › Models. */
export const MODELS = [
  "Claude Opus 4.6",
  "Claude Sonnet 4.6",
  "Claude Haiku 4.5",
];

export const THINKING_LEVELS = ["Off", "Low", "Medium", "High"];

/** API key fallback used by headless CI runners. */
export const API_KEY_FALLBACK = "sk-ant-api03-7fJk2LmQ9xRb4TnW8vZc1Hs6";
