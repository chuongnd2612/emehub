// The ticket detail view, at all three of its addresses (#219, #221):
//
//   /app/projects/:projectId/tickets/:externalId    inside its project
//   /app/unassigned/tickets/:externalId             the Unassigned bucket
//   /app/tickets/:externalId                        legacy, via LegacyTicketRedirect
//
// One screen for all three: the ticket is the same row, and only the way back
// differs — which is why `backTo` is derived from the URL rather than fixed.
//
// Mirrors QAgent's `app/src/screens/TicketDetail.tsx` (#157) in EmeHub's token
// layer. The handoff draws no detail state for Tickets, so QAgent's is the
// reference, as CLAUDE.md directs for ambiguous ticket behaviour.
//
// ## Why the provider is in the URL
//
// Ticket identity in the hub is `(providerKind, externalId)`, so an Azure DevOps
// `1234` and a GitHub `1234` are two different rows and the path alone cannot
// say which one is meant. The provider therefore rides in `?source=`, and this
// is the ONE place in the ticket flow that still carries it: #221 removed it from
// the list route, where it was a provider *switch* on a set of rows, but here it
// disambiguates a single row's identity and nothing derives it. Omitting it is
// still valid: the hub then picks, which is the right behaviour for a caller that
// genuinely does not know.
//
// ## What QAgent has that this does not
//
// The `note` block. QAgent's `note` is a QA-run annotation, and the hub stores no
// such column on purpose — it is domain work, which the hub does not do
// (`api/app/models/ticket.py`, CLAUDE.md › What this repo is). There is no field
// to render and there should not be one.
//
// Everything else is here, and every field comes from `GET /tickets/{id}` except
// the two cards that read live through the hub's PAT (comments refresh, test
// cases). No endpoint is invented and nothing is stubbed.

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

import {
  EmptyState,
  ErrorState,
  GlassCard,
  Glyph,
  Icon,
  Pill,
  Skeleton,
  statusTone,
} from "@/components/ui";
import {
  PROVIDER_DISPLAY,
  getTicketDetail,
  type ProviderKey,
  type TicketDetail,
} from "@/data";
import {
  PROVIDER_GLYPH,
  UNASSIGNED_TICKETS_PATH,
  UNKNOWN_GLYPH,
  projectPath,
} from "@/screens/ProjectDetail/shared";
import { ApiError } from "@/lib/api";

import { AcceptanceCriteria } from "./AcceptanceCriteria";
import { Comments } from "./Comments";
import { TestCases } from "./TestCases";
import { priorityTone } from "./shared";

const isProvider = (value: string | null): value is ProviderKey =>
  value === "ado" || value === "jira" || value === "gh";

/**
 * Reset the shell's scroll region on mount.
 *
 * Same reasoning as `ProjectDetail`: the scroll container belongs to the app
 * shell, so walk up to the nearest scrollable ancestor rather than reaching into
 * another component. Arriving halfway down a work item is disorienting.
 */
function useResetScrollOnMount() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let el: HTMLElement | null = ref.current?.parentElement ?? null;
    while (el) {
      const overflowY = getComputedStyle(el).overflowY;
      if (overflowY === "auto" || overflowY === "scroll") {
        el.scrollTop = 0;
        return;
      }
      el = el.parentElement;
    }
    window.scrollTo(0, 0);
  }, []);
  return ref;
}

export default function TicketDetailScreen() {
  const { externalId = "", projectId } = useParams();
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const rootRef = useResetScrollOnMount();

  const source = params.get("source");
  /** `null` — not a guess — when the URL does not say. The hub then picks. */
  const provider: ProviderKey | null = isProvider(source) ? source : null;

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing" | "error">(
    "loading",
  );
  const [error, setError] = useState("");

  const load = useCallback(() => {
    let live = true;
    setStatus("loading");
    void getTicketDetail(externalId, provider)
      .then((loaded) => {
        if (!live) return;
        setTicket(loaded);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        // A 404 is not a failure: the row is not mirrored, or belongs to another
        // member (the hub 404s rather than 403s so it cannot confirm it exists).
        // Either way the answer is "not here", which is an empty state and not
        // an error card with a Retry that will fail identically.
        if (err instanceof ApiError && err.status === 404) {
          setStatus("missing");
          return;
        }
        setError(
          err instanceof ApiError ? err.message : "The hub did not respond.",
        );
        setStatus("error");
      });
    return () => {
      live = false;
    };
  }, [externalId, provider]);

  useEffect(load, [load]);

  /**
   * Back to the list this work item was reached from (#221).
   *
   * Derived from the URL, because since containment the detail page has three
   * addresses and each has its own list: inside a project, in the Unassigned
   * bucket, or the legacy flat link that redirects. `/app/tickets` is no longer
   * a list at all — it redirects to `/app/projects` (#219) — so the old
   * unconditional `backTo` sent every Back to All projects, which is not where
   * the user came from.
   *
   * No `?source=` on the way back: the list derives its provider from the
   * project, so a provider parameter on it would be a control that does nothing.
   */
  const backTo = projectId
    ? projectPath(projectId, "tickets")
    : pathname.startsWith("/app/unassigned/")
      ? UNASSIGNED_TICKETS_PATH
      : "/app/projects";

  const back = (
    <Link
      to={backTo}
      className="flex items-center gap-2 self-start text-[12.5px] font-semibold text-muted no-underline transition-colors duration-200 hover:text-txt2"
    >
      <Icon name="arrowLeft" size={14} strokeWidth={2.3} />
      All work items
    </Link>
  );

  if (status === "loading") {
    return (
      <div ref={rootRef} className="flex flex-col gap-3.5">
        {back}
        {/* The geometry is known, so the columns fill in rather than the layout
            jumping when the payload lands. */}
        <div className="grid grid-cols-1 items-start gap-3.5 lg:grid-cols-[1.55fr_1fr]">
          <Skeleton className="h-[420px] rounded-card" />
          <Skeleton className="h-[280px] rounded-panel" />
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div ref={rootRef} className="flex flex-col gap-3.5">
        {back}
        <GlassCard className="rounded-[20px]">
          <ErrorState
            title="Could not load this work item"
            detail={error}
            onRetry={load}
          />
        </GlassCard>
      </div>
    );
  }

  if (status === "missing" || !ticket) {
    return (
      <div ref={rootRef} className="flex flex-col gap-3.5">
        {back}
        <GlassCard className="rounded-[20px]">
          <EmptyState
            icon="ticket"
            title={`${externalId} is not in the mirror`}
            body="EmeHub only holds work items an import has pulled. Import a wider scope, or check that you are looking at the right provider."
            action={
              // A `Link` styled as the primary button rather than a `Button`
              // that navigates: this is a navigation, so it should be a real
              // anchor — middle-clickable, and keyboard-reachable as a link.
              <Link
                to={backTo}
                className="inline-flex h-9 items-center gap-2 rounded-button bg-accent-grad px-[18px] text-[12.5px] font-bold text-white no-underline shadow-primary transition-transform duration-200 hover:-translate-y-px"
              >
                <Icon name="arrowLeft" size={14} strokeWidth={2.3} />
                Back to work items
              </Link>
            }
          />
        </GlassCard>
      </div>
    );
  }

  const glyph = ticket.provider
    ? PROVIDER_GLYPH[ticket.provider]
    : UNKNOWN_GLYPH;
  const providerName = ticket.provider
    ? PROVIDER_DISPLAY[ticket.provider]
    : "the provider";

  return (
    <div ref={rootRef} className="flex animate-fade-in-up flex-col gap-3.5">
      {back}

      <div className="grid grid-cols-1 items-start gap-3.5 lg:grid-cols-[1.55fr_1fr]">
        <div className="flex min-w-0 flex-col gap-3.5">
          <GlassCard radius="panel" className="p-6">
            <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
              <Glyph size={26} fill={glyph.fill} label={glyph.letter} />
              <span className="font-mono text-[12.5px] font-semibold text-ps-text">
                {ticket.id}
              </span>
              {ticket.status && (
                <Pill tone={statusTone(ticket.status)}>{ticket.status}</Pill>
              )}
              {ticket.type && (
                <Pill tone="neutral" size="sm">
                  {ticket.type}
                </Pill>
              )}
              {/* An empty `url` means the hub has no link to offer — an adapter
                  with no org or base URL cannot build one — so the action is
                  absent rather than dead. Never reconstructed here. */}
              {ticket.url && (
                <a
                  href={ticket.url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto inline-flex items-center gap-1.5 rounded-control-lg border border-bd2 bg-inset px-3 py-[7px] text-[12px] font-bold text-txt3 no-underline transition-colors duration-200 hover:bg-bd3 hover:text-txt2"
                >
                  Open in {providerName}
                  <Icon name="externalLink" size={13} strokeWidth={2.2} />
                </a>
              )}
            </div>

            <h1 className="m-0 mb-4 text-[23px] leading-[1.25] font-black tracking-[-.035em] text-txt">
              {ticket.title}
            </h1>

            <p className="mb-[7px] text-[11px] font-semibold tracking-[.08em] text-faint">
              DESCRIPTION
            </p>
            {ticket.description ? (
              <p className="m-0 mb-[18px] text-[14px] leading-[1.6] whitespace-pre-wrap text-txt3">
                {ticket.description}
              </p>
            ) : (
              <p className="m-0 mb-[18px] text-[13px] text-muted">
                This work item has no description in {providerName}.
              </p>
            )}

            <p className="mb-2.5 text-[11px] font-semibold tracking-[.08em] text-faint">
              ACCEPTANCE CRITERIA
              {ticket.acceptanceCriteria.length >= 2 && (
                <> · {ticket.acceptanceCriteria.length}</>
              )}
            </p>
            <AcceptanceCriteria
              criteria={ticket.acceptanceCriteria}
              html={ticket.acceptanceCriteriaHtml}
            />
          </GlassCard>

          <GlassCard radius="panel" className="p-5">
            <TestCases
              externalId={ticket.id}
              provider={ticket.provider}
              providerName={providerName}
            />
          </GlassCard>

          <GlassCard radius="panel" className="p-5">
            <Comments
              externalId={ticket.id}
              provider={ticket.provider}
              snapshot={ticket.comments}
              synced={ticket.synced}
            />
          </GlassCard>
        </div>

        <div className="flex min-w-0 flex-col gap-3.5">
          <GlassCard radius="panel" className="p-[18px]">
            <div className="flex flex-col gap-[13px]">
              <MetaRow label="Priority">
                {ticket.priority ? (
                  <Pill tone={priorityTone(ticket.priority)} size="sm">
                    {ticket.priority}
                  </Pill>
                ) : (
                  <span className="text-faint">—</span>
                )}
              </MetaRow>
              <MetaRow label="Status">
                {/* `Pill` + `statusTone` rather than `StatusPill`: provider
                    states are project-configurable free text, so they are not
                    `StatusName`, and `statusTone` falls back to neutral for the
                    ones the handoff never named. */}
                {ticket.status ? (
                  <Pill tone={statusTone(ticket.status)} size="sm">
                    {ticket.status}
                  </Pill>
                ) : (
                  <span className="text-faint">—</span>
                )}
              </MetaRow>
              <MetaRow label="Assignee">
                <span className="font-semibold text-txt2">
                  {ticket.owner || "Unassigned"}
                </span>
              </MetaRow>
              <MetaRow label="Sprint">
                <span className="font-semibold text-txt2">
                  {ticket.sprint || "—"}
                </span>
              </MetaRow>
              {ticket.area && (
                <MetaRow label="Area path">
                  <span className="truncate font-mono text-[11.5px] text-txt4">
                    {ticket.area}
                  </span>
                </MetaRow>
              )}
              {ticket.epic && (
                <MetaRow label="Epic">
                  <span className="font-semibold text-txt2">{ticket.epic}</span>
                </MetaRow>
              )}
              <MetaRow label="Project">
                <span className="font-semibold text-txt2">
                  {ticket.project || "Unattributed"}
                </span>
              </MetaRow>
              <MetaRow label="Last import">
                <span className="text-txt4">{ticket.synced}</span>
              </MetaRow>

              {ticket.labels.length > 0 && (
                <div>
                  <p className="m-0 mb-2 text-[13px] text-muted">Labels</p>
                  <div className="flex flex-wrap gap-1.5">
                    {ticket.labels.map((l) => (
                      <Pill key={l} tone="neutral" size="sm">
                        {l}
                      </Pill>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </GlassCard>

          <GlassCard radius="panel" className="p-[18px]">
            <p className="m-0 mb-3 text-[13px] font-bold text-txt">
              Linked pull requests
            </p>
            {ticket.linkedPrs.length === 0 ? (
              <p className="m-0 text-[12px] text-muted">
                No pull requests are linked to this work item.
              </p>
            ) : (
              <div className="flex flex-col gap-[9px]">
                {ticket.linkedPrs.map((pr, i) => (
                  <div
                    key={`${pr.repo}-${pr.num}-${i}`}
                    className="flex items-center gap-2.5 rounded-[11px] bg-card3 p-[9px]"
                  >
                    <Icon
                      name="git"
                      size={15}
                      strokeWidth={2}
                      className="shrink-0 text-ps-text"
                    />
                    <div className="min-w-0 flex-1">
                      {pr.url ? (
                        <a
                          href={pr.url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 overflow-hidden text-[12px] font-semibold text-ps-text no-underline hover:underline"
                        >
                          <span className="truncate">
                            {pr.title || `Pull request ${pr.num}`}
                          </span>
                          <Icon
                            name="externalLink"
                            size={12}
                            strokeWidth={2.2}
                            className="shrink-0"
                          />
                        </a>
                      ) : (
                        <div className="truncate text-[12px] font-semibold text-txt2">
                          {pr.title || `Pull request ${pr.num}`}
                        </div>
                      )}
                      <div className="truncate font-mono text-[11px] text-faint">
                        {[pr.repo, pr.num && `#${pr.num}`]
                          .filter(Boolean)
                          .join(" ")}
                      </div>
                    </div>
                    {pr.status && (
                      <Pill tone={statusTone(pr.status)} size="sm">
                        {pr.status}
                      </Pill>
                    )}
                  </div>
                ))}
              </div>
            )}

            <p className="m-0 mt-4 mb-3 text-[13px] font-bold text-txt">
              Attachments
            </p>
            {ticket.attachments.length === 0 ? (
              <p className="m-0 text-[12px] text-muted">
                No attachments on this work item.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {ticket.attachments.map((at, i) => (
                  <div
                    key={`${at.name}-${i}`}
                    className="flex items-center gap-2.5 rounded-[11px] bg-card3 p-[9px]"
                  >
                    <Icon
                      name="doc"
                      size={15}
                      strokeWidth={2}
                      className="shrink-0 text-label"
                    />
                    <span className="min-w-0 flex-1 truncate text-[12px] text-txt3">
                      {at.name}
                    </span>
                    {at.size && (
                      <span className="shrink-0 font-mono text-[11px] text-faint">
                        {at.size}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          <p className="m-0 flex items-start gap-2 px-1 text-[11.5px] leading-[1.5] text-faint">
            <Icon
              name="lock"
              size={13}
              strokeWidth={2.2}
              className="mt-px shrink-0"
            />
            Read-only mirror. Edit this work item in {providerName} — the next
            import reflects the change.
          </p>
        </div>
      </div>
    </div>
  );
}

/** One `label / value` line in the meta card. */
function MetaRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-[13px]">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="min-w-0 text-right">{children}</span>
    </div>
  );
}
