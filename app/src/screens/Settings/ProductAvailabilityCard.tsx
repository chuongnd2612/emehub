// NO DESIGN WAS SUPPLIED FOR THIS CARD.
//
// Built from the existing Settings vocabulary — `GlassCard` + `ToggleRow` — so it
// reads as part of the screen rather than as something bolted on (#186).
//
// It writes immediately and says so. When the screen still had a save-bar draft
// this card deliberately stayed out of it: those were per-browser preferences
// saved in bulk, while this is workspace state that takes effect for everybody
// the moment it is flipped, and burying that behind a Save button would let an
// admin believe a product was closed while it was still open. The draft is gone
// now (#191); this card's behaviour is unchanged.
//
// Admin-only is enforced by the server (403), not by hiding the card: that is the
// hub's existing pattern — see `Users/MembersTable` — and it means a member sees
// why rather than wondering where the setting went.

import { useEffect, useState } from "react";

import { getAgents, setAgentEnabled } from "@/data/agents";
import type { AgentTarget } from "@/data/types";
import { GlassCard } from "@/components/ui";
import { ToggleRow } from "./SettingRow";

export function ProductAvailabilityCard() {
  const [agents, setAgents] = useState<AgentTarget[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAgents()
      .then((list) => {
        if (!cancelled) setAgents(list);
      })
      .catch(() => {
        // A failed read leaves the card empty rather than rendering toggles whose
        // position would be a guess — a switch showing the wrong state is worse
        // than no switch.
        if (!cancelled) setError("Could not load products.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const flip = async (agent: AgentTarget, enabled: boolean) => {
    setBusy(agent.id);
    setError(null);
    // Optimistic, then reconciled with what the server actually stored: the
    // toggle should move under the finger, but the truth is the response.
    setAgents((prev) =>
      (prev ?? []).map((a) => (a.id === agent.id ? { ...a, enabled } : a)),
    );
    try {
      const stored = await setAgentEnabled(agent.id, enabled);
      setAgents((prev) =>
        (prev ?? []).map((a) => (a.id === agent.id ? { ...a, enabled: stored } : a)),
      );
    } catch (err) {
      setAgents((prev) =>
        (prev ?? []).map((a) => (a.id === agent.id ? { ...a, enabled: !enabled } : a)),
      );
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Could not change availability.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <GlassCard className="flex flex-col gap-[2px] p-[18px]">
      {error && (
        <p className="m-0 mb-2 text-[12px] text-danger" role="alert">
          {error}
        </p>
      )}
      {agents?.map((agent) => (
        <ToggleRow
          key={agent.id}
          label={agent.name}
          description={
            agent.enabled
              ? "Open to everyone in the workspace."
              : "Shows as coming soon. Its card cannot be launched and its URL redirects."
          }
          checked={agent.enabled}
          onChange={(next) => {
            if (busy !== agent.id) void flip(agent, next);
          }}
        />
      ))}
    </GlassCard>
  );
}
