// QAgent's "Linked test cases" card — id, title, state, an Open link — read
// live from the provider through the hub's own PAT.
//
// ## One thing to know about the scope
//
// The hub's `GET /tickets/{id}/test-cases` reports `projectWide`, and for Azure
// DevOps it is always `true`: ADO has no cheap per-work-item test-case query, so
// the ticket in the path selects the *connection*, not the result set. This card
// presents the result as this work item's cases anyway — a deliberate decision,
// recorded here so it does not read as an oversight. The count can therefore be
// the project's rather than the ticket's on ADO.
//
// Loaded on demand, not with the detail: it costs a provider round trip, and
// nothing above the fold needs it.

import { useCallback, useEffect, useState } from "react";

import { Button, Icon, Pill, Spinner } from "@/components/ui";
import { getTicketTestCases, type ProviderKey, type ProviderTestCase } from "@/data";
import { ApiError } from "@/lib/api";

import { caseStateTone } from "./shared";

/** `78px | 1fr | 92px | 92px` — QAgent's column set. */
const COLUMNS = "78px minmax(0,1fr) 100px 92px";

export interface TestCasesProps {
  externalId: string;
  provider: ProviderKey | null;
  providerName: string;
}

export function TestCases({
  externalId,
  provider,
  providerName,
}: TestCasesProps) {
  const [cases, setCases] = useState<ProviderTestCase[]>([]);
  const [supported, setSupported] = useState(true);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setStatus("loading");
    setError("");
    return getTicketTestCases(externalId, provider)
      .then((read) => {
        setCases(read.items);
        setSupported(read.supported);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "The hub could not reach the provider.",
        );
        setStatus("error");
      });
  }, [externalId, provider]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <span className="flex-1 text-[14px] font-bold text-txt">
          Linked test cases
        </span>
        {status === "ready" && supported && cases.length > 0 && (
          <Pill tone="ok" size="sm" mono>
            {cases.length}
          </Pill>
        )}
        <Button
          size="sm"
          icon={
            status === "loading" ? (
              <Spinner size={13} speed="run" />
            ) : (
              <Icon name="refresh" size={13} strokeWidth={2.2} />
            )
          }
          disabled={status === "loading"}
          onClick={() => void load()}
        >
          Refresh
        </Button>
      </div>

      {/* A failed provider read is said out loud and never rendered as "none" —
          the whole point of the hub answering 502 instead of an empty list. */}
      {status === "error" && (
        <p className="m-0 text-[12.5px] text-danger">
          Could not read test cases: {error}
        </p>
      )}

      {status === "ready" && !supported && (
        <p className="m-0 text-[12.5px] text-muted">
          {providerName} has no test-case concept, so there is nothing to link.
        </p>
      )}

      {status === "ready" && supported && cases.length === 0 && (
        <div className="flex flex-col items-center gap-1.5 rounded-[14px] border border-dashed border-bd2 bg-card3 px-5 py-7 text-center">
          <Icon
            name="checkSquare"
            size={26}
            strokeWidth={1.8}
            className="mb-1 text-label"
          />
          <p className="m-0 text-[13.5px] font-semibold text-txt2">
            No test cases yet
          </p>
          <p className="m-0 max-w-[320px] text-[12.5px] leading-relaxed text-muted">
            Q-Agent creates them in {providerName} and links them back to this
            work item. They appear here as soon as it has.
          </p>
        </div>
      )}

      {status === "ready" && supported && cases.length > 0 && (
        <div className="overflow-hidden rounded-[13px] border border-bd3">
          <div
            className="grid gap-2.5 bg-card3 px-3.5 py-[9px] text-[10px] font-bold tracking-[.05em] text-label"
            style={{ gridTemplateColumns: COLUMNS }}
          >
            <span>ID</span>
            <span>TITLE</span>
            <span>STATE</span>
            <span>LINK</span>
          </div>
          {cases.map((tc) => (
            <div
              key={tc.externalId || tc.title}
              className="grid items-center gap-2.5 border-t border-bd3 px-3.5 py-[11px] text-[12.5px]"
              style={{ gridTemplateColumns: COLUMNS }}
            >
              <span className="truncate font-mono font-semibold text-ps-text">
                {tc.externalId || "—"}
              </span>
              <span className="truncate text-txt3">{tc.title}</span>
              <span>
                {tc.state ? (
                  <Pill tone={caseStateTone(tc.state)} size="sm">
                    {tc.state}
                  </Pill>
                ) : (
                  <span className="text-[11px] text-faint">—</span>
                )}
              </span>
              <span>
                {/* An empty `url` means the hub has no link to offer, not a
                    broken one — so nothing is rendered rather than a dead
                    anchor. Never reconstructed from the org URL. */}
                {tc.url ? (
                  <a
                    href={tc.url}
                    target="_blank"
                    rel="noreferrer"
                    title={`Open in ${providerName}`}
                    className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-ps-text no-underline hover:underline"
                  >
                    Open
                    <Icon name="externalLink" size={12} strokeWidth={2.2} />
                  </a>
                ) : (
                  <span className="text-[11px] text-faint">—</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
