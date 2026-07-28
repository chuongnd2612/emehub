// Prototype `PROV`, `PRODUCTS` and `INTEGRATIONS`, typed.

import type { Integration, Product, Provider, ProviderKey } from "../types";

export const PROVIDERS: Record<ProviderKey, Provider> = {
  ado: { key: "ado", name: "Azure DevOps", glyph: "A", color: "azure" },
  jira: { key: "jira", name: "Jira Cloud", glyph: "J", color: "jira" },
  gh: { key: "gh", name: "GitHub", glyph: "G", color: "github" },
};

export const PROVIDER_ORDER: ProviderKey[] = ["ado", "jira", "gh"];

export const PRODUCTS: Product[] = [
  {
    key: "q",
    name: "Q-Agent",
    code: "qa.emesoft.net",
    live: true,
    role: "QA / QC automation",
    description:
      "Turns tickets into reviewed test cases, runs Playwright suites end to end, and publishes evidence straight back to your provider.",
    tags: ["Test generation", "Playwright", "Evidence publishing"],
    metric: "1,204",
    metricLabel: "RUNS THIS MONTH",
    stats: [
      { k: "SUITES", v: "38" },
      { k: "PASS RATE", v: "96%" },
      { k: "OPEN RUNS", v: "3" },
    ],
  },
  {
    key: "d",
    name: "D-Agent",
    code: "ticket-executor",
    live: false,
    role: "Developer assistant",
    description:
      "Picks up a ticket, plans the change, writes the code and opens the pull request — inheriting the same knowledge base Q-Agent indexes.",
    tags: ["Codegen", "PR review", "Repo context"],
    metric: "Q4 2026",
    metricLabel: "TARGET RELEASE",
    stats: [
      { k: "REPOS WIRED", v: "2" },
      { k: "DRY RUNS", v: "17" },
      { k: "STATUS", v: "Beta" },
    ],
  },
];

export const INTEGRATIONS: Integration[] = [
  {
    id: "ado",
    name: "Azure DevOps",
    state: "Connected",
    meta: "emesoft/Surveyor · 4 projects",
    auth: "OAuth · expires in 84 days",
    sync: "Every 5 min",
    last: "2 min ago",
    items: "128 work items",
  },
  {
    id: "jira",
    name: "Jira Cloud",
    state: "Connected",
    meta: "emesoft.atlassian.net · 2 projects",
    auth: "API token · s.kaya@emesoft.net",
    sync: "Every 15 min",
    last: "11 min ago",
    items: "64 issues",
  },
  {
    id: "gh",
    name: "GitHub",
    state: "Attention",
    meta: "emesoft org · 6 repositories",
    auth: "GitHub App · re-auth required",
    sync: "Paused",
    last: "6h ago",
    items: "6 repositories",
  },
];
