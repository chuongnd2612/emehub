# EmeHub — Context & Glossary

Shared vocabulary for the EMESOFT agent suite. When a word below appears in an issue, a PR or
an ADR, it means what it says here.

---

## 1. The shape of the system

**Hub** — this application. Owns identity and shared configuration. Serves the landing page
and the admin console. Never performs domain work (it does not generate tests, write code, or
run browsers).

**Agent** — a specialised application that does domain work for one discipline. QAgent (QA),
DAgent (development), BAgent (business analysis, planned). An agent is a *consumer* of the
hub: it authenticates with a hub-issued token and reads its configuration from hub endpoints.

**Suite** — the hub plus every agent, as presented to a user.

---

## 2. Identity

**User** — a person. One record in the hub, one email, one password, optional TOTP. Roles are
`admin` and `member`. There is no per-agent user record; an agent knows a user only by the
`sub` claim in the token the hub issued.

**Session** — a login on one device. Holds the refresh token (hashed), user agent and IP.
Revoking a session logs that device out of *every* agent, because every agent's access token
carries the session id (`sid`).

**Access token** — short-lived, signed by the hub, audience-scoped to one agent. Presented as
a bearer token. Agents validate it locally; they do not call back to the hub per request.

**Refresh token** — long-lived, opaque, stored only as a hash. Held by the hub in an HttpOnly
cookie. Only the hub can exchange it.

**Organisation / tenant** — *does not exist yet.* QAgent emulates multi-tenancy with a
nullable `owner_id` on every table plus a `shared` (NULL-owner) namespace. Whether the hub
introduces a real organisation entity is deliberately left open until Phase 2; see
[ROADMAP.md](ROADMAP.md).

---

## 3. Credentials

**Claude credential** — the Anthropic account an agent runs Claude Code with. In QAgent today
this is a `.credentials.json` uploaded by the user, encrypted at rest, and *materialised* to
disk (as a `CLAUDE_CONFIG_DIR`) for the duration of a CLI invocation. Users may have their
own, or prefer a shared organisation credential.

**Materialise** — write a decrypted credential to a locked-down temporary location so the
Claude CLI can read it, then rely on the CLI's own token refresh being captured back into the
store. The term is worth keeping: it is the mechanism DAgent currently lacks.

**Provider connection** — a configured link to an external system: Azure DevOps, GitHub or
Jira. Holds the org/base URL and an encrypted PAT. A connection advertises *capabilities* —
`work_item` (it can supply tickets) and `repository` (it can supply repos) — so a project can
bind different providers for different jobs.

**Encryption key** vs **signing secret** — two distinct secrets in the hub. The signing secret
signs JWTs; the encryption key encrypts credentials at rest. QAgent conflates them into one
value, which is exactly what [ADR 0005](adr/0005-secret-and-key-management.md) exists to
avoid repeating.

---

## 4. Work

**Project** — a unit of work with a key, a base URL, one or more environments, test accounts,
and bindings to provider connections. Shared across agents: the same project is what QAgent
tests and DAgent implements against.

**Repository** — a git repo belonging to a project. Cloned per user into a scoped workspace.

**Knowledge / Knowledge base** — what we know about one repository: its stack, architecture,
routes, selectors, page objects, fixtures. Built by running a Claude skill over the cloned
source. Keyed by `project::repo`. Has a status (`not_indexed` → `indexing` → `indexed` →
`stale` / `error`) and a confidence score.

**Verified at runtime** — a knowledge entry (typically a selector or a route) that was
observed in a live browser rather than inferred from source. Takes precedence over
source-inferred entries.

**Ticket** — a work item from a provider, normalised: external id, title, type, status,
assignee, description, acceptance criteria, comments, links. Synced into the hub so both
agents see the same ticket.

**Run** *(QAgent)* — one pass of the eight-stage QA pipeline over a ticket. Hub does not own
runs.

**Execution** *(DAgent)* — one invocation of the Claude CLI against a ticket in a repo, with
its own worktree, streamed log, token and cost totals. Hub does not own executions.

**Skill** — a packaged instruction set the Claude CLI runs (`project-bootstrap`,
`test-case-generator`, `implement-ticket-v3`, …). Skills stay with the agent that uses them;
the hub does not distribute skills.

---

## 5. Who owns what

| Concept | Hub | QAgent | DAgent |
|---|:--:|:--:|:--:|
| User, role, session, 2FA | **owns** | consumes | consumes |
| Claude credential | **owns** | consumes | consumes |
| Provider connection | **owns** | consumes | consumes |
| Project, environments, test accounts | **owns** | consumes | consumes |
| Repository registry | **owns** | consumes | consumes |
| Knowledge base | **owns** | consumes + contributes | consumes |
| Ticket | **owns** | consumes | consumes |
| Audit trail | **owns** | writes to | writes to |
| Run, spec, evidence, pipeline | — | **owns** | — |
| Execution, worktree, PR | — | — | **owns** |
| Skills | — | **owns** | **owns** |
| Local Agent (paired device) | — | **owns** | — |

"Consumes" means: reads over HTTP, may cache, never writes its own authoritative copy.

---

## 6. Non-goals

- **Not a chat product.** The hub has no conversational surface; agents do the talking.
- **Not a workflow engine.** The hub does not orchestrate agents or pass work between them.
  Hand-off is a user action, made cheap because the context is already shared.
- **Not a model gateway.** Agents call Claude themselves with a credential resolved from the
  hub; the hub does not proxy inference.
- **Not a monorepo.** The three repositories stay separate and are integrated over HTTP; see
  [ADR 0003](adr/0003-integration-via-http-and-hub-issued-jwt.md).
