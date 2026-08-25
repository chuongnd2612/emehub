// Agents — the launch registry, live against the hub.
//
//   GET /agents    getAgents
//
// This is what turns the product cards' Launch buttons from no-ops into real
// navigation. It answers two *different* questions per agent, and the UI has to
// keep them apart (ADR 0008):
//
//   registered    the hub will mint tokens for it (its URL is configured)
//   handoffReady  single sign-on can actually work — which additionally needs
//                 EMEHUB_COOKIE_DOMAIN set to a domain the agent sits under,
//                 because otherwise the browser never sends the refresh cookie
//                 to POST /auth/agent-token
//
// So an agent can be registered and still not launchable. When that happens
// `reason` names the missing configuration (`no_url` / `no_cookie_domain` /
// `domain_mismatch`) so the button can say why instead of just being dead. On
// the default localhost stack every agent reports `no_cookie_domain`, which is
// correct rather than pessimistic: SSO genuinely cannot work there.

import { api } from "@/lib/api";
import type { AgentTarget } from "./types";

/** LIVE: GET /agents — hub-audience only, so this is never called by an agent. */
export async function getAgents(): Promise<AgentTarget[]> {
  const body = await api.get<{ agents: AgentTarget[] }>("/agents");
  return body.agents ?? [];
}

/**
 * Human-readable explanation for a non-launchable agent.
 *
 * Deliberately names the environment variable: the only person who sees this is
 * whoever deploys the hub, and "not configured" on its own has never once helped
 * anybody.
 */
export function handoffBlockerText(agent: AgentTarget): string | null {
  switch (agent.reason) {
    case "no_url":
      return `Not configured — set EMEHUB_AGENT_${agent.id.toUpperCase()}_URL on the hub.`;
    case "no_cookie_domain":
      return "Single sign-on needs EMEHUB_COOKIE_DOMAIN set to the domain the hub and this agent share.";
    case "domain_mismatch":
      return `${agent.url ?? "This agent"} is not under the hub's cookie domain, so it cannot receive the session.`;
    default:
      return null;
  }
}

/**
 * LIVE: `PUT /agents/{key}/availability` — admin only; a member gets a 403 (#186).
 *
 * Turning a product off is a product decision, not configuration, which is why it
 * is a write here rather than an environment variable: it takes effect on the
 * next request instead of the next deploy.
 */
export async function setAgentEnabled(key: string, enabled: boolean): Promise<boolean> {
  const body = await api.put<{ key: string; enabled: boolean }>(
    `/agents/${key}/availability`,
    { enabled },
  );
  return body.enabled;
}

