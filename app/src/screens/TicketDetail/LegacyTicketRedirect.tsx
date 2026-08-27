// The redirect that keeps saved `/app/tickets/:externalId` links working after
// containment moved the ticket routes under their project (#219, ADR 0011 §1).
//
// A bare ticket link does not say which project it belongs to, and the hub is
// the only thing that knows: `GET /tickets/{externalId}` returns the ticket's
// own `project_id` (a real FK since #217). So this screen asks, maps the row id
// to the GUID the project routes are keyed by (`resolveTicketProject`), and then
// expresses the answer as a `<Navigate replace>` — never as an imperative
// redirect, and never as a guess.
//
//   project_id set   → /app/projects/:projectId/tickets/:externalId
//   project_id NULL  → /app/unassigned/tickets/:externalId
//
// `replace` matters: the flat URL must not stay on the history stack, or Back
// from the nested page replays the redirect and the user is trapped.
//
// `?source=` rides along untouched. It is the provider, and ticket identity is
// `(providerKind, externalId)` — dropping it here would make the redirect target
// resolve a different row than the link asked for.

import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";

import { LoadingState } from "@/components/ui";
import { resolveTicketProject, type ProviderKey } from "@/data";

import { UNASSIGNED_TICKETS_PATH } from "@/screens/ProjectDetail/shared";

const isProvider = (value: string | null): value is ProviderKey =>
  value === "ado" || value === "jira" || value === "gh";

export default function LegacyTicketRedirect() {
  const { externalId = "" } = useParams();
  const [params] = useSearchParams();

  const source = params.get("source");
  const provider: ProviderKey | null = isProvider(source) ? source : null;
  const search = params.toString();

  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void resolveTicketProject(externalId, provider)
      .then((projectId) => {
        if (!live) return;
        setTarget(
          projectId
            ? `/app/projects/${encodeURIComponent(projectId)}/tickets`
            : UNASSIGNED_TICKETS_PATH,
        );
      })
      // The hub did not answer, or the id is not mirrored. The Unassigned
      // bucket is the honest destination: the ticket detail there reports the
      // 404 itself rather than this screen inventing a project for it.
      .catch(() => {
        if (live) setTarget(UNASSIGNED_TICKETS_PATH);
      });
    return () => {
      live = false;
    };
  }, [externalId, provider]);

  if (!target) return <LoadingState label="Loading work item…" />;

  const path = `${target}/${encodeURIComponent(externalId)}`;
  return <Navigate to={search ? `${path}?${search}` : path} replace />;
}
