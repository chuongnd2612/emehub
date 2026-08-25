// Handoff § 1. Landing — product card.
//
// Pointer tilt (`useCardTilt`, gated by Depth on hover) PLUS the radial
// cursor-follow wash the same hook drives through `--gx` / `--gy`.
//
// The whole card is the click target (prototype: `onClick={pr.open}` on the
// card div), so it is a `div[role=button]` with a keyboard handler rather than
// a `<button>` — the card contains paragraphs and a grid, which a button's
// phrasing-only content model does not allow.
//
// ## A closed product is not a card you can click (#191)
//
// This card used to branch only on `product.live`, the *design* badge, and so
// showed a green "Live" pill and stayed clickable for a product an admin had
// switched off in Settings › Product availability. `getProducts` now resolves
// `enabled` from the public `GET /agents/{id}/open`, which a signed-out visitor
// can actually read, and a closed product loses `role="button"`, its tab stop
// and its handlers outright rather than keeping a live-looking affordance that
// silently does nothing. The copy is #186's, from the coming-soon page and the
// Overview card — not new vocabulary.

import type { KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Icon, Pill, toast } from "@/components/ui";
import { useCardTilt } from "@/hooks/useTilt";
import type { Product } from "@/data";
import { PRODUCT_ICON, PRODUCT_VISUALS } from "./productVisuals";

export function ProductCard({ product }: { product: Product }) {
  const tilt = useCardTilt();
  const navigate = useNavigate();
  const visual = PRODUCT_VISUALS[product.key];

  // Closed outranks everything else the card could say: an admin has decided
  // the product is not open, so the Live/Placeholder distinction is moot.
  const comingSoon = product.enabled === false;

  // The landing page is public, and `GET /agents` is hub-audience only — so this
  // card cannot know where an agent lives, and must not be given a public
  // endpoint just to find out. Sending a live product to /app is the honest
  // move: RequireAuth either restores the session and lands on Overview, where
  // the real Launch button is, or bounces to /login. One redirect, no new
  // public surface, and the URL stays the source of truth.
  const open = () => {
    if (comingSoon) return;
    if (product.live) {
      navigate("/app");
    } else {
      toast("D-Agent is not live yet", "warn");
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  };

  return (
    <div className="[perspective:1200px]">
      <div
        {...(comingSoon
          ? { "aria-disabled": true }
          : {
              role: "button",
              tabIndex: 0,
              onClick: open,
              onKeyDown,
            })}
        ref={tilt.ref}
        onMouseMove={tilt.onMouseMove}
        onMouseLeave={tilt.onMouseLeave}
        className={`group relative flex min-h-[330px] flex-col gap-[18px] rounded-[24px] border border-bd2 bg-inset p-[26px] shadow-[0_24px_60px_-22px_var(--shadow)] transition-[transform,border-color,box-shadow] duration-300 [backdrop-filter:blur(24px)] [transform-style:preserve-3d] ${
          comingSoon ? "cursor-default" : "cursor-pointer hover:border-pb"
        }`}
      >
        {/* Cursor-follow wash — fades in on hover; its centre tracks
            --gx / --gy, which useCardTilt writes on every mousemove. */}
        <span
          className={`pointer-events-none absolute inset-0 rounded-[24px] opacity-0 transition-opacity duration-300 group-hover:opacity-100 ${visual.wash}`}
        />

        <div className="relative flex items-start gap-4">
          <span
            className={`flex size-14 shrink-0 items-center justify-center rounded-[17px] text-white [transform:translateZ(30px)] ${visual.tile}`}
          >
            <Icon name={PRODUCT_ICON[product.key]} size={26} strokeWidth={2.1} />
          </span>
          <div className="flex-1">
            <div className="flex items-center gap-2.5">
              <span className="text-[25px] font-black tracking-[-.03em] text-txt">
                {product.name}
              </span>
              {comingSoon ? (
                <Pill tone="neutral" size="sm">
                  Coming soon
                </Pill>
              ) : product.live ? (
                <Pill tone="ok" size="sm">
                  Live
                </Pill>
              ) : (
                <Pill tone="info" size="sm">
                  Placeholder
                </Pill>
              )}
            </div>
            <div className="mt-[5px] text-[12.5px] font-semibold text-muted">
              {product.role}
            </div>
            <div
              className={`mt-1 font-mono text-[11px] font-semibold tracking-[.02em] ${visual.text}`}
            >
              {product.code}
            </div>
          </div>
        </div>

        <p className="relative m-0 text-[14px] leading-[1.6] text-txt3 [text-wrap:pretty]">
          {product.description}
        </p>

        <div className="relative flex flex-wrap gap-[7px]">
          {product.tags.map((tag) => (
            <Pill key={tag} tone="neutral">
              {tag}
            </Pill>
          ))}
        </div>

        {/* The three stat boxes and the trailing metric are gone — see the
            `Product` type: they were an agent's run history, which the hub does
            not store and cannot fetch, so they could only be invented. */}

        <div className="relative mt-auto flex items-center justify-between gap-3 pt-1.5">
          <span
            className={
              product.live && !comingSoon
                ? `inline-flex items-center gap-2 rounded-[12px] px-[18px] py-[11px] text-[13.5px] font-bold text-white [transform:translateZ(36px)] ${visual.cta}`
                : "inline-flex items-center gap-2 rounded-[12px] border border-bd2 bg-inset px-[18px] py-[11px] text-[13.5px] font-semibold text-muted [transform:translateZ(36px)]"
            }
          >
            {/* "Launch Q-Agent" is the handoff's copy, verbatim, on both
                cards — D-Agent's card has read it since `live` was flipped
                true. Copy is final, so it is left alone here and raised
                separately rather than paraphrased in a deletion PR. */}
            {comingSoon
              ? "Coming soon"
              : product.live
                ? "Launch Q-Agent"
                : "In development"}
            <Icon name="arrowRight" size={15} strokeWidth={2.4} />
          </span>
        </div>
      </div>
    </div>
  );
}
