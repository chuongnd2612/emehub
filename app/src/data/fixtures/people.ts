// Prototype `ROLES` and `INVITES`, typed.
//
// The prototype's `MEMBERS` array is GONE: `getMembers()` now reads
// `GET /auth/users`, so a fixture member list could only ever be rendered as if
// it were real — the one thing the empty/error-state rules forbid.
// `CURRENT_USER` is gone for the same reason: the signed-in principal comes
// from `store/auth.ts`, which holds what `/auth/me` returned.

import type { Invitation, Role } from "../types";

export const ROLES: Role[] = [
  {
    name: "Owner",
    count: 1,
    description: "Full control including billing, deletion and ownership transfer.",
    permissions: ["Everything an Admin can do", "Manage billing", "Transfer or delete workspace"],
  },
  {
    name: "Admin",
    count: 1,
    description: "Manages the platform: credentials, integrations, people and access.",
    permissions: ["Configure Claude credentials", "Manage integrations & SSO", "Invite and remove members"],
  },
  {
    name: "Member",
    count: 3,
    description: "Runs agents day to day and maintains project knowledge.",
    permissions: ["Launch Q-Agent and D-Agent", "Edit project knowledge", "View tickets and projects"],
  },
  {
    name: "Viewer",
    count: 1,
    description: "Read-only visibility into results and reports.",
    permissions: ["View runs, tickets and reports", "No configuration access", "No knowledge editing"],
  },
];

export const INVITATIONS: Invitation[] = [
  { email: "deniz.arslan@emesoft.net", role: "Member", sent: "2d ago", by: "Ayse Demir" },
  { email: "qa.contractor@partner.io", role: "Viewer", sent: "5d ago", by: "Emre Kaya" },
  { email: "tolga.sen@emesoft.net", role: "Member", sent: "1w ago", by: "Ayse Demir" },
];
