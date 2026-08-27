// `/app/projects/:projectId` with no tab segment — and the legacy `?tab=` links
// that used to be the only way to name a tab (#219, ADR 0011 §1).
//
// Since the tab became a path segment, a bare project URL is not a view: it
// resolves, once, to the project's default tab. Old links keep working because
// `?tab=` is read here and turned into that segment, so a bookmarked
// `/app/projects/x?tab=knowledge` lands on `/app/projects/x/knowledge` with the
// dead parameter dropped.
//
// **How long does `?tab=` acceptance stay?** Until the agent cutover is done
// (ROADMAP Phase 4) and no hub link older than #219 can still be in anyone's
// bookmarks or in a sibling repo's docs — i.e. a deliberate removal, not a
// deadline. It is four lines and it costs nothing to keep; deleting it silently
// breaks bookmarks, which is the one thing the nesting was supposed to avoid.
//
// `replace` is load-bearing: the bare URL must not stay on the history stack, or
// Back from the tab it redirected to replays the redirect forever.

import { Navigate, useParams, useSearchParams } from "react-router-dom";

import {
  DEFAULT_PROJECT_TAB,
  isProjectTab,
  projectPath,
} from "./shared";

export default function ProjectTabRedirect() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();

  const legacy = params.get("tab");
  const tab = isProjectTab(legacy) ? legacy : DEFAULT_PROJECT_TAB;

  // Everything except the retired `tab` is carried across — nothing else on a
  // project URL is this screen's to throw away.
  const rest = new URLSearchParams(params);
  rest.delete("tab");
  const search = rest.toString();
  const path = projectPath(projectId, tab);

  return <Navigate to={search ? `${path}?${search}` : path} replace />;
}
