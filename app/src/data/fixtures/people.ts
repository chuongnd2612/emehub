// Prototype `MEMBERS`, `ROLES`, `INVITES`, typed.

import type { Invitation, Member, Role } from "../types";

export const MEMBERS: Member[] = [
  { name: "Emre Kaya", email: "emre.kaya@emesoft.net", role: "Owner", lastActive: "active now", initials: "EK", credential: "shared", credentialId: "sc1" },
  { name: "Ayse Demir", email: "ayse.demir@emesoft.net", role: "Admin", lastActive: "12m ago", initials: "AD", credential: "shared", credentialId: "sc1" },
  { name: "Mert Yilmaz", email: "mert.yilmaz@emesoft.net", role: "Member", lastActive: "2h ago", initials: "MY", credential: "personal", credentialId: null },
  { name: "Selin Kaya", email: "selin.kaya@emesoft.net", role: "Member", lastActive: "yesterday", initials: "SK", credential: "shared", credentialId: "sc2" },
  { name: "Jakub Novak", email: "j.novak@emesoft.net", role: "Member", lastActive: "3d ago", initials: "JN", credential: "shared", credentialId: "sc1" },
  { name: "Lena Braun", email: "lena.braun@partner.io", role: "Viewer", lastActive: "1w ago", initials: "LB", credential: "none", credentialId: null },
];

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

/** The signed-in user shown in the sidebar chip. */
export const CURRENT_USER = {
  name: "Emre Kaya",
  initials: "EK",
  role: "Owner · EMESOFT",
  email: "emre.kaya@emesoft.net",
};
