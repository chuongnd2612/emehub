// Derivations the TicketDetail cards share. Nothing here is a design decision —
// it is QAgent's `badges.tsx` mapping expressed against EmeHub's token layer,
// which is where the light-mode darkening already lives.

import type { PillTone } from "@/components/ui";
import type { ProviderKey } from "@/data";

/**
 * QAgent's `priorityColor` as a tone.
 *
 * It maps `High → #fb7185`, `Medium → #fbbf24`, everything else → slate — which
 * is exactly `danger` / `warn` / `neutral` in this token layer. Going through
 * the tones rather than the hexes is what gets light mode for free: `--danger`
 * and `--warn` already carry their darkened foregrounds, and a literal `#fb7185`
 * measures 2.4:1 on a pale card.
 */
export const priorityTone = (priority: string): PillTone => {
  if (priority === "High") return "danger";
  if (priority === "Medium") return "warn";
  return "neutral";
};

/**
 * Provider-side test-case states, toned.
 *
 * QAgent maps `Design → violet`, `Ready → green`, `Open → cyan`,
 * `To Do → amber`, with violet as the fallback. Violet is QAgent's brand accent
 * and EmeHub's is red, so the fallback here is `accent` — the *current* accent,
 * whichever of the four the user has chosen, rather than a borrowed one.
 */
export const caseStateTone = (state: string): PillTone => {
  switch (state) {
    case "Ready":
    case "Closed":
      return "ok";
    case "Open":
      return "info";
    case "To Do":
      return "warn";
    default:
      return "accent";
  }
};

/**
 * A link to one ticket's detail page **when the caller does not know its
 * project** — today only the command palette, which searches rows and holds a
 * project *name*, not the GUID the nested routes are keyed by.
 *
 * This is the legacy flat address on purpose: `LegacyTicketRedirect` resolves it
 * to `/app/projects/:projectId/tickets/:externalId`, or to the Unassigned bucket
 * for a row with no project (#219). A caller that already knows the container
 * uses `projectTicketPath` / `unassignedTicketPath` (`ProjectDetail/shared.ts`)
 * and skips the round trip.
 *
 * `?source=` carries the provider because ticket identity is
 * `(providerKind, externalId)` — an ADO `1234` and a GitHub `1234` are two rows,
 * and the path alone cannot say which. It is a disambiguator on one row, not the
 * provider switch #221 removed from the lists.
 */
export const ticketPath = (
  externalId: string,
  provider: ProviderKey | null,
): string => {
  const path = `/app/tickets/${encodeURIComponent(externalId)}`;
  return provider ? `${path}?source=${provider}` : path;
};
