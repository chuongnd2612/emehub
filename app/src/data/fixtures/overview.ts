// Prototype `ACTIVITY` + the Overview KPI tiles, typed.

import type { ActivityEvent, Kpi } from "../types";

export const ACTIVITY: ActivityEvent[] = [
  { text: "Q-Agent published 14 test cases and evidence for", ref: "SUR-1428", kind: "q", by: "Q-Agent", when: "4m ago", icon: "spark" },
  { text: "Azure DevOps import completed — 128 work items mirrored", ref: "ADO", kind: "sync", by: "System", when: "12m ago", icon: "upload" },
  { text: "Ayse Demir added a knowledge source", ref: "KB-101", kind: "kb", by: "Ayse Demir", when: "2h ago", icon: "book" },
  { text: "D-Agent dry run opened a draft pull request on", ref: "TEX-19", kind: "d", by: "D-Agent", when: "3h ago", icon: "code" },
  { text: "GitHub App authorisation expired and needs re-auth", ref: "GITHUB", kind: "warn", by: "System", when: "6h ago", icon: "alert" },
  { text: "Mert Yilmaz rotated the CI pipeline API key", ref: "ehk_live_9f2c", kind: "key", by: "Mert Yilmaz", when: "yesterday", icon: "key" },
];

export const KPIS: Kpi[] = [
  { label: "OPEN TICKETS", value: "128", unit: "across 6 projects", delta: "+12", direction: "up", bars: [42, 55, 38, 64, 58, 76, 70, 88] },
  { label: "SYNC HEALTH", value: "96", unit: "% of items in sync", delta: "-2", direction: "down", bars: [88, 92, 84, 96, 90, 94, 89, 96] },
  { label: "KNOWLEDGE SOURCES", value: "342", unit: "1.1M indexed chunks", delta: "+18", direction: "up", bars: [30, 44, 52, 48, 62, 70, 74, 82] },
  { label: "AGENT RUNS", value: "1,204", unit: "this month", delta: "+9%", direction: "up", bars: [50, 46, 62, 58, 72, 66, 80, 92] },
];
