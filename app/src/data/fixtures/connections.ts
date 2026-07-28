// Prototype `CONNECTIONS`, typed. Field values are already masked where the
// real API would only ever return `hasPat: true` (CLAUDE.md › Security rules:
// never log or return a secret).

import type { ProviderConnectionGroup } from "../types";

export const CONNECTION_GROUPS: ProviderConnectionGroup[] = [
  {
    provider: "ado",
    projectsLabel: "4 projects",
    connections: [
      {
        id: "ado-1",
        label: "EMESOFT · Surveyor",
        summary: "dev.azure.com/emesoft/Surveyor",
        status: "Connected",
        lastSync: "2 min ago",
        fields: [
          { key: "url", label: "Organisation URL", value: "https://dev.azure.com/emesoft", type: "text" },
          { key: "project", label: "Project", value: "Surveyor", type: "text" },
          { key: "pat", label: "Personal access token", value: "wxy7••••••••••••••••", type: "password" },
          { key: "area", label: "Area path", value: "Surveyor\\QA", type: "text" },
        ],
      },
      {
        id: "ado-2",
        label: "EMESOFT · Nova",
        summary: "dev.azure.com/emesoft/Nova",
        status: "Connected",
        lastSync: "14 min ago",
        fields: [
          { key: "url", label: "Organisation URL", value: "https://dev.azure.com/emesoft", type: "text" },
          { key: "project", label: "Project", value: "Nova", type: "text" },
          { key: "pat", label: "Personal access token", value: "k28f••••••••••••••••", type: "password" },
          { key: "area", label: "Area path", value: "Nova\\Billing", type: "text" },
        ],
      },
    ],
  },
  {
    provider: "jira",
    projectsLabel: "2 projects",
    connections: [
      {
        id: "jira-1",
        label: "EMESOFT Atlassian",
        summary: "emesoft.atlassian.net",
        status: "Connected",
        lastSync: "11 min ago",
        fields: [
          { key: "url", label: "Site URL", value: "https://emesoft.atlassian.net", type: "text" },
          { key: "email", label: "Account email", value: "s.kaya@emesoft.net", type: "text" },
          { key: "token", label: "API token", value: "atl_••••••••••••••••", type: "password" },
          { key: "jql", label: "Default JQL", value: "project in (LED, ATL)", type: "text" },
        ],
      },
    ],
  },
  {
    provider: "gh",
    projectsLabel: "6 repositories",
    connections: [
      {
        id: "gh-1",
        label: "emesoft (organisation)",
        summary: "github.com/emesoft · GitHub App #48213",
        status: "Attention",
        lastSync: "6h ago",
        fields: [
          { key: "org", label: "Organisation", value: "emesoft", type: "text" },
          { key: "app", label: "App installation ID", value: "48213", type: "text" },
          { key: "pem", label: "Private key", value: "-----BEGIN••••••••", type: "password" },
          { key: "branch", label: "Default branch", value: "main", type: "text" },
        ],
      },
    ],
  },
];
