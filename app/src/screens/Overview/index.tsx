// Handoff § 2. Overview (`page === 'overview'`).
//
// Renders INSIDE the app shell's scroll region — no sidebar, no page header
// here. Page root: display:flex; flex-direction:column; gap:14px;
// animation:fadeInUp .38s ease both.
//
// All data comes from the typed data layer (`@/data`), which is still stubbed
// against fixtures — see the `// STUB:` comments there for the endpoints that
// will replace it.

import { useEffect, useState } from "react";

import {
  getActivity,
  getIntegrations,
  getKpis,
  getProducts,
  getProjects,
  getTicketCounts,
  type ActivityEvent,
  type Integration,
  type Kpi,
  type Product,
  type Project,
  type TicketCounts,
} from "@/data";

import { ImportDialog, useImportRun } from "@/components/import";
import {
  ActivityRowsSkeleton,
  GlassCard,
  KpiTilesSkeleton,
  PanelHeadingSkeleton,
  ProductCardsSkeleton,
  SummaryPanelSkeleton,
} from "@/components/ui";
import { useUi } from "@/store/ui";

import { ActivityFeed } from "./ActivityFeed";
import { GreetingRow } from "./GreetingRow";
import { KpiTiles } from "./KpiTiles";
import { ProductCard } from "./ProductCard";
import { ProjectComparison } from "./ProjectComparison";
import { IntegrationStrip, TopProjects } from "./SummaryPanels";

export default function OverviewScreen() {
  const [products, setProducts] = useState<Product[]>([]);
  const [kpis, setKpis] = useState<Kpi[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  /**
   * The one counting path (#217). `null` means "not loaded, or the read
   * failed" — the comparison table renders no number rather than a fabricated
   * zero, which is the property `useSidebarStats()` established.
   */
  const [counts, setCounts] = useState<TicketCounts | null>(null);

  // Handoff § 5: the Import dialog also opens from the Overview quick action.
  // The spinner belongs to the chip that opened it, so the run state lives
  // here and the dialog is mounted alongside (see `useImportRun`).
  const modal = useUi((s) => s.modal);
  const setModal = useUi((s) => s.setModal);
  const { importing, run } = useImportRun();
  /**
   * The first load has finished. The greeting's status line needs this: counts
   * of 0 are indistinguishable from "still loading", and "0 projects" rendered
   * for a moment is a false statement rather than a placeholder.
   */
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    void Promise.all([
      getProducts(),
      getKpis(),
      getActivity(),
      getIntegrations(),
      getProjects(),
      // Caught here and nowhere else: a failed count must not blank the whole
      // page, and it must not become a `0` either. `null` says "unavailable".
      getTicketCounts().catch(() => null),
    ]).then(([pr, kp, ac, ig, pj, tc]) => {
      if (!live) return;
      setProducts(pr);
      setKpis(kp);
      setActivity(ac);
      setIntegrations(ig);
      setProjects(pj);
      setCounts(tc);
      setLoaded(true);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <GreetingRow
        importing={importing}
        onImport={() => setModal("import")}
        projectCount={loaded ? projects.length : null}
        connectionCount={loaded ? integrations.length : null}
      />

      {/* Skeletons, not a spinner: every block below has a known geometry, so
          the layout can land immediately and fill in. The page used to sit
          blank behind bare panel headings while five requests resolved. */}
      {loaded ? (
        <div className="grid grid-cols-2 gap-[14px]">
          {products.map((p) => (
            <ProductCard key={p.key} product={p} />
          ))}
        </div>
      ) : (
        <ProductCardsSkeleton />
      )}

      {loaded ? <KpiTiles kpis={kpis} /> : <KpiTilesSkeleton />}

      {/* The cross-project view (#218) — the workspace-wide question that used
          to be asked on the standalone Tickets screen. It has to exist here
          before that entry is removed (ADR 0011). */}
      <ProjectComparison
        projects={projects}
        counts={counts}
        loading={!loaded}
      />

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-[14px]">
        {loaded ? (
          <ActivityFeed events={activity} />
        ) : (
          <GlassCard radius="panel" className="flex flex-col p-5">
            <PanelHeadingSkeleton />
            <ActivityRowsSkeleton />
          </GlassCard>
        )}
        <div className="flex flex-col gap-[14px]">
          {loaded ? (
            <>
              <IntegrationStrip integrations={integrations} />
              <TopProjects projects={projects} />
            </>
          ) : (
            <>
              <GlassCard radius="panel" className="flex flex-col gap-3.5 p-5">
                <PanelHeadingSkeleton />
                <SummaryPanelSkeleton rows={2} />
              </GlassCard>
              <GlassCard radius="panel" className="flex flex-col gap-3.5 p-5">
                <PanelHeadingSkeleton />
                <SummaryPanelSkeleton rows={3} />
              </GlassCard>
            </>
          )}
        </div>
      </div>

      {/* Workspace defaults are not persisted yet (Settings › Workspace
          defaults is screen state), so the Overview import opens on Azure
          DevOps — the workspace default shown there. */}
      <ImportDialog
        open={modal === "import"}
        provider="ado"
        onClose={() => setModal(null)}
        onImport={run}
      />
    </div>
  );
}
