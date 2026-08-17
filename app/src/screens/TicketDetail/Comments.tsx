// The comment thread, mirroring QAgent's card — avatar tile, author, timestamp,
// body.
//
// ## Two sources, one shape
//
// The detail payload's `comments` is the snapshot as of `syncedAt`; the hub's
// `GET /tickets/{id}/comments` reads the same shape **live** from the provider
// through its own PAT. Identical fields, different freshness, so Refresh swaps
// one for the other with nothing to reconcile — and the card says which one it
// is showing, because "3 comments" from a week-old sync and "3 comments" from
// ten seconds ago are not the same claim.
//
// A failed live read leaves the snapshot on screen and says the refresh failed.
// It must never blank the thread: a failed load rendering as "no comments" is
// the exact failure the hub's `supported` flag exists to prevent one level down.

import { useState } from "react";

import { Button, Icon, Pill, Spinner } from "@/components/ui";
import { getTicketComments, type ProviderKey, type TicketComment } from "@/data";
import { ApiError } from "@/lib/api";

/** Initials for the avatar tile. The hub sends a display name, not initials. */
const initials = (who: string): string => {
  const parts = who.trim().split(/[\s.@_-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

export interface CommentsProps {
  externalId: string;
  provider: ProviderKey | null;
  /** The snapshot from the detail payload. */
  snapshot: TicketComment[];
  /** Humanised `syncedAt`, for the line that dates the snapshot. */
  synced: string;
}

export function Comments({
  externalId,
  provider,
  snapshot,
  synced,
}: CommentsProps) {
  /** `null` until a live read succeeds; then it replaces the snapshot. */
  const [live, setLive] = useState<TicketComment[] | null>(null);
  const [supported, setSupported] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const comments = live ?? snapshot;

  const refresh = () => {
    setBusy(true);
    setError("");
    void getTicketComments(externalId, provider)
      .then((read) => {
        setLive(read.items);
        setSupported(read.supported);
      })
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "The hub could not reach the provider.",
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <>
      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <span className="flex-1 text-[14px] font-bold text-txt">Comments</span>
        {comments.length > 0 && (
          <Pill tone="neutral" size="sm" mono>
            {comments.length}
          </Pill>
        )}
        <Button
          size="sm"
          icon={
            busy ? (
              <Spinner size={13} speed="run" />
            ) : (
              <Icon name="refresh" size={13} strokeWidth={2.2} />
            )
          }
          disabled={busy}
          onClick={refresh}
        >
          Refresh
        </Button>
      </div>

      <p className="m-0 mb-3.5 text-[11.5px] text-faint">
        {live
          ? "Read live from the provider."
          : `From the last import${synced ? ` · ${synced}` : ""}.`}
      </p>

      {error && (
        <p className="m-0 mb-3.5 text-[12px] text-danger">
          Could not refresh: {error}
        </p>
      )}

      {!supported && (
        <p className="m-0 mb-3.5 text-[12px] text-muted">
          This provider has no comment thread, so there is nothing to read.
        </p>
      )}

      {comments.length === 0 ? (
        <p className="m-0 text-[13px] text-muted">
          {supported
            ? "No comments on this work item yet."
            : "Comments live in the provider for the ones that have them."}
        </p>
      ) : (
        <div className="flex flex-col gap-3.5">
          {comments.map((c, i) => (
            <div key={`${i}-${c.who}-${c.when}`} className="flex gap-[11px]">
              <span className="flex size-[30px] shrink-0 items-center justify-center rounded-[9px] bg-accent-grad text-[11px] font-bold text-white">
                {initials(c.who)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="mb-[3px] text-[12.5px]">
                  <span className="font-bold text-txt">
                    {c.who || "Unknown author"}
                  </span>
                  {c.when && (
                    <span className="text-faint"> · {c.when}</span>
                  )}
                </div>
                <div className="text-[13px] leading-[1.55] whitespace-pre-wrap text-txt3">
                  {c.text}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
