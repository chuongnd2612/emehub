// Handoff § 1. Landing (`view === 'landing'`).
//
// The landing view has NO app shell — it is its own full-page layout over the
// same ambient background stack the shell uses: a flat `--bg` fill plus the
// two `glowPulse` blooms whose opacity is the Ambient user setting.
//
// Single column, max-width 1400px: header (22/44) → hero (70/44/44) →
// product cards → capability grid → final CTA → compact footer.

import { useEffect, useState } from "react";

import { getProducts, type Product } from "@/data";
import { useAppearance } from "@/store/appearance";
import { CapabilityGrid } from "./CapabilityGrid";
import { FinalCta } from "./FinalCta";
import { Hero } from "./Hero";
import { LandingFooter } from "./LandingFooter";
import { LandingHeader } from "./LandingHeader";
import { ProductCard } from "./ProductCard";
import { SectionLabel } from "./SectionLabel";

export default function LandingScreen() {
  const ambient = useAppearance((s) => s.ambient);
  const [products, setProducts] = useState<Product[]>([]);

  useEffect(() => {
    let live = true;
    void getProducts().then((rows) => {
      if (live) setProducts(rows);
    });
    return () => {
      live = false;
    };
  }, []);

  // Ambient bloom opacity is a user setting (0–100) — a computed value, the
  // documented exception to the no-inline-styles rule.
  const glow = { opacity: ambient / 100 };

  return (
    <div className="relative min-h-screen w-full">
      {/* Background stack — all position:fixed; inset:0. */}
      <div className="fixed inset-0 z-0 bg-bg" />
      <div
        className="pointer-events-none fixed top-[-16%] left-[-8%] z-[1] size-[660px] animate-glow-pulse rounded-full bg-[radial-gradient(circle,var(--pt),transparent_62%)] blur-[34px]"
        style={glow}
      />
      <div
        className="pointer-events-none fixed right-[-6%] bottom-[-22%] z-[1] size-[740px] animate-glow-pulse rounded-full bg-[radial-gradient(circle,var(--bloom2),transparent_62%)] blur-[34px] [animation-delay:1s] [animation-duration:11s]"
        style={glow}
      />

      <div className="relative z-[2] flex min-h-screen flex-col">
        <LandingHeader />
        <Hero />

        <section
          id="products"
          className="mx-auto w-full max-w-[1400px] animate-fade-in-up px-11 pt-[26px] pb-2.5"
        >
          <SectionLabel>THE AGENTS</SectionLabel>
          <div className="grid grid-cols-2 gap-3.5">
            {products.map((product) => (
              <ProductCard key={product.key} product={product} />
            ))}
          </div>
        </section>

        <CapabilityGrid />
        <FinalCta />
        <LandingFooter />
      </div>
    </div>
  );
}
