# ADR 0007 — Knowledge builds run on the hub

- **Status:** Accepted
- **Date:** 2026-07-29
- **Amends:** [ADR 0001](0001-emehub-is-the-source-of-truth.md) — narrows "the hub does no
  domain work"
- **Supersedes:** the Phase 4 filesystem split in [ROADMAP.md](../ROADMAP.md)

## Context

Phase 4 shipped with a deliberate split: the hub owns knowledge **metadata**, and *building* a
knowledge base — cloning the repository and running the `project-bootstrap` skill through the
Claude CLI — stays on the agent host. The hub only recorded the result through
`PUT /projects/{key}/repos/{repo}/knowledge`.

Three things were true when that was decided, and two of them still are:

1. Building is domain work, which [ADR 0001](0001-emehub-is-the-source-of-truth.md) reserved
   for agents. *(Still true — this ADR changes the rule, see below.)*
2. The hub owned no workspace filesystem. *(Still true, until this change.)*
3. Cloning needs the repository PAT decrypted onto disk, which sat awkwardly beside "provider
   PATs never leave the hub". *(This one was a misreading — see Consequences.)*

What that split produced in practice was a **"Build project knowledge" button that could not
build anything.** It was shipped as a documented stub. Worse, it left D-Agent — which has no
build capability of its own and no plans for one — permanently unable to obtain a knowledge
base, and made a knowledge base impossible to create before an agent existed at all.

## Decision

**Knowledge builds run on the hub.**

The hub clones the repository into a per-owner workspace, runs `project-bootstrap` through the
Claude CLI against that clone, writes `knowledge.md` / `knowledge.json`, and updates the
`project_knowledge` row itself. `POST /projects/{key}/repos/{repo}/knowledge/build` starts the
work in the background; the existing `indexing` status is the in-flight guard and the thing the
UI polls.

`PUT .../knowledge` **stays**. An agent that builds its own knowledge — Q-Agent already does —
can still report the result. The hub becomes *a* builder, not the only one.

### What this changes about ADR 0001

ADR 0001 said the hub does no domain work, and listed "no test generation, no code generation,
no browsers". That boundary holds for everything except this: **the hub may build the shared
artefacts it already owns the inputs for.** Knowledge is hub-owned data
([ADR 0001](0001-emehub-is-the-source-of-truth.md) puts "projects, repositories and knowledge
bases" squarely in the hub's column), and the hub already holds the repository connection, its
PAT, the project configuration and the Claude credential. Every input was already here; only
the compute was elsewhere.

The line is now: **the hub builds hub-owned data; it does not do an agent's job.** No test
generation, no code generation, no browser automation, no PR creation.

## Consequences

**Good.** The Build button does what it says. D-Agent gets knowledge bases without building
anything. A knowledge base can exist before any agent is connected. One builder means one
result, rather than each agent producing its own subtly different index.

**The hub now runs untrusted-ish code paths.** It clones arbitrary repositories and runs a
Claude CLI process against their contents. That is a materially larger attack surface than a
configuration store, and the failure modes (a hung clone, a runaway CLI, a repository that
fills the disk) are now the hub's problem. Builds are therefore backgrounded, status-guarded
and concurrency-bounded.

**The workspace volume becomes sensitive.** The hub decrypts a repository PAT to clone, and
materialises a Claude credential to a locked-down `CLAUDE_CONFIG_DIR` to run the CLI. Both
still **never leave the hub** — the INTEGRATION.md §4 contract is about what crosses the
boundary to an agent, and nothing here does. But `emehub-workspace` now holds plaintext
credential material for the duration of a build and must be treated accordingly: not a
world-readable mount, not a volume you casually copy.

**The image grows.** `git`, Node 20 and `@anthropic-ai/claude-code` join the Python base.
Chromium is deliberately *not* added — that is for DOM exploration and manual-login capture,
neither of which this ADR admits.

**Cost moves to the hub.** Builds are minutes long and consume Claude tokens against whichever
credential resolved for the owner. Usage is already recorded per owner
(`claude_usage`), so this is attributable — but the hub is now a place where money is spent,
which it previously was not.

## Alternatives rejected

- **Keep the split, delete the button.** Honest, and it was the status quo. Rejected because it
  leaves D-Agent permanently without knowledge and makes the hub's knowledge store
  write-only-by-proxy.
- **Have the hub ask an agent to build.** Preserves ADR 0001 exactly, but requires an agent to
  be connected, adds a job-dispatch protocol the suite does not otherwise need, and still
  leaves D-Agent out until it grows a build path. Revisit if hub CPU becomes the bottleneck.
