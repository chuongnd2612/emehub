// Prototype `TICKETS` + `TICKET_SCHEMA`, typed.
//
// Exactly one provider is active at a time and the filter set changes with it
// (Handoff › 4. Tickets). Switching source clears all field filters.

import type { Ticket, TicketFilterSchema } from "../types";

export const TICKETS: Ticket[] = [
  { id: "SUR-1428", title: "Signature capture fails on iOS 18 Safari", provider: "ado", status: "In progress", agent: "q", sync: "Imported", project: "Surveyor Web", owner: "A. Demir", sprint: "Sprint 24", area: "Surveyor\\QA", type: "Bug" },
  { id: "SUR-1431", title: "Add bulk export to inspection report list", provider: "ado", status: "New", agent: null, sync: "Imported", project: "Surveyor Web", owner: "M. Yilmaz", sprint: "Sprint 24", area: "Surveyor\\Reports", type: "User Story" },
  { id: "SUR-1402", title: "Offline queue drops photos larger than 8MB", provider: "ado", status: "Done", agent: "q", sync: "Imported", project: "Surveyor Mobile", owner: "E. Kaya", sprint: "Sprint 23", area: "Surveyor\\Mobile", type: "Bug" },
  { id: "NOV-77", title: "Invoice PDF renders wrong VAT for DE customers", provider: "ado", status: "New", agent: null, sync: "Importing", project: "Nova Billing", owner: "L. Braun", sprint: "Sprint 24", area: "Nova\\Billing", type: "Bug" },
  { id: "LED-822", title: "Reconciliation job times out over 50k rows", provider: "jira", status: "Blocked", agent: "q", sync: "Failed", project: "Ledger API", owner: "S. Kaya", sprint: "LED Sprint 12", epic: "Reconciliation", type: "Bug", priority: "High" },
  { id: "LED-830", title: "Expose idempotency key on payment intents", provider: "jira", status: "In progress", agent: "d", sync: "Importing", project: "Ledger API", owner: "J. Novak", sprint: "LED Sprint 12", epic: "Payments API", type: "Story", priority: "Medium" },
  { id: "ATL-114", title: "Portal login redirect loop behind SSO", provider: "jira", status: "In review", agent: "q", sync: "Imported", project: "Atlas Portal", owner: "A. Demir", sprint: "LED Sprint 11", epic: "Single sign-on", type: "Bug", priority: "Highest" },
  { id: "TEX-19", title: "Wire repository context loader to knowledge base", provider: "gh", status: "In progress", agent: "d", sync: "Imported", project: "Ticket Executor", owner: "E. Kaya", milestone: "v0.3", label: "enhancement" },
  { id: "TEX-24", title: "Cache cloned repositories between agent runs", provider: "gh", status: "New", agent: null, sync: "Imported", project: "Ticket Executor", owner: "J. Novak", milestone: "v0.4", label: "qa" },
];

/** One filter pill per field, in toolbar order. Also drives the import dialog. */
export const TICKET_FILTER_SCHEMA: TicketFilterSchema = {
  ado: [
    { key: "sprint", label: "Sprint", options: ["Sprint 24", "Sprint 23"] },
    { key: "area", label: "Area path", options: ["Surveyor\\QA", "Surveyor\\Reports", "Surveyor\\Mobile", "Nova\\Billing"] },
    { key: "status", label: "State", options: ["New", "In progress", "In review", "Blocked", "Done"] },
    { key: "type", label: "Work item type", options: ["User Story", "Bug", "Task"] },
  ],
  jira: [
    { key: "sprint", label: "Sprint", options: ["LED Sprint 12", "LED Sprint 11"] },
    { key: "epic", label: "Epic", options: ["Reconciliation", "Payments API", "Single sign-on"] },
    { key: "status", label: "Status", options: ["New", "In progress", "In review", "Blocked", "Done"] },
    { key: "type", label: "Issue type", options: ["Story", "Bug", "Task"] },
    { key: "priority", label: "Priority", options: ["Highest", "High", "Medium", "Low"] },
  ],
  gh: [
    { key: "milestone", label: "Milestone", options: ["v0.3", "v0.4"] },
    { key: "label", label: "Label", options: ["bug", "enhancement", "qa"] },
    { key: "status", label: "State", options: ["New", "In progress", "In review", "Done"] },
    { key: "owner", label: "Assignee", options: ["E. Kaya", "J. Novak", "A. Demir"] },
  ],
};

/** Handoff › 5. Import dialog › Basic — the three "WHAT TO PULL" radio rows. */
export const IMPORT_SCOPES = [
  { key: "sprint" as const, label: "Active sprint", hint: "~24 items" },
  { key: "assigned" as const, label: "Assigned to me", hint: "~9 items" },
  { key: "all" as const, label: "All open work items", hint: "~118 items" },
];
