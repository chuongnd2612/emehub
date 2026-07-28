// Prototype `SESSIONS` + `KEYS`, typed.

import type { ApiKey, Session } from "../types";

export const SESSIONS: Session[] = [
  { id: "s1", device: "MacBook Pro · Chrome 141", where: "Istanbul, TR", ip: "88.241.14.7", when: "active now", current: true },
  { id: "s2", device: "iPhone 17 Pro · Safari", where: "Istanbul, TR", ip: "88.241.14.9", when: "26m ago", current: false },
  { id: "s3", device: "Windows 11 · Edge 141", where: "Ankara, TR", ip: "85.104.62.31", when: "yesterday", current: false },
  { id: "s4", device: "CI runner · headless", where: "Frankfurt, DE", ip: "18.196.4.88", when: "3h ago", current: false },
];

export const API_KEYS: ApiKey[] = [
  { id: "k1", name: "CI pipeline (Azure)", prefix: "ehk_live_9f2c", scope: "Read tickets, write evidence", used: "12m ago", created: "Mar 2026" },
  { id: "k2", name: "D-Agent runner", prefix: "ehk_live_4a71", scope: "Full agent access", used: "2h ago", created: "Jun 2026" },
  { id: "k3", name: "Reporting export", prefix: "ehk_live_be08", scope: "Read only", used: "6d ago", created: "Jan 2026" },
];
