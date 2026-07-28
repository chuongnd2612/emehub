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
  type ActivityEvent,
  type Integration,
  type Kpi,
  type Product,
  type Project,
} from "@/data";

import { ActivityFeed } from "./ActivityFeed";
import { GreetingRow } from "./GreetingRow";
import { KpiTiles } from "./KpiTiles";
import { ProductCard } from "./ProductCard";
import { IntegrationStrip, TopProjects } from "./SummaryPanels";

export default function OverviewScreen() {
  const [products, setProducts] = useState<Product[]>([]);
  const [kpis, setKpis] = useState<Kpi[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    let live = true;
    void Promise.all([
      getProducts(),
      getKpis(),
      getActivity(),
      getIntegrations(),
      getProjects(),
    ]).then(([pr, kp, ac, ig, pj]) => {
      if (!live) return;
      setProducts(pr);
      setKpis(kp);
      setActivity(ac);
      setIntegrations(ig);
      setProjects(pj);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <GreetingRow />

      <div className="grid grid-cols-2 gap-[14px]">
        {products.map((p) => (
          <ProductCard key={p.key} product={p} />
        ))}
      </div>

      <KpiTiles kpis={kpis} />

      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-[14px]">
        <ActivityFeed events={activity} />
        <div className="flex flex-col gap-[14px]">
          <IntegrationStrip integrations={integrations} />
          <TopProjects projects={projects} />
        </div>
      </div>
    </div>
  );
}
