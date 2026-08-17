// The acceptance criteria block, in the three states the hub's two AC fields
// produce (QAgent's `TicketDetail.tsx`, same precedence):
//
//   ≥2 split criteria  → the numbered chip list. The useful rendering: each
//                        criterion is separately readable and countable.
//   otherwise + HTML   → the provider's own markup, sanitized. The criteria did
//                        not divide cleanly, so imposing a list on them would
//                        misrepresent a table or a nested structure as one item.
//   exactly 1, no HTML → that one criterion as a paragraph. A "1." chip in front
//                        of a single item is a list that isn't one.
//   nothing            → said plainly. Never a blank space.
//
// ## Why the HTML is sanitized rather than trusted
//
// `acceptanceCriteriaHtml` is the **provider's** markup, authored by whoever
// wrote the work item, stored by the hub verbatim and never inspected. It is
// exactly the shape of untrusted input that `dangerouslySetInnerHTML` is
// dangerous for, so DOMPurify runs on every render and every surviving anchor is
// forced to open in a new tab — a criterion linking somewhere must not be able
// to navigate the hub away from itself.

import DOMPurify from "dompurify";

/**
 * Force every sanitized anchor to open in a new tab.
 *
 * Registered once at module scope because DOMPurify hooks are global — adding it
 * per render would stack duplicates. This module is the only place in the app
 * that sanitizes, so a global hook is safe here and would not be if that changed.
 */
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.getAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noreferrer");
  }
});

/**
 * The provider's AC markup, sanitized and styled through the token layer.
 *
 * The child selectors are the only way to reach nodes this component does not
 * author. Each one binds to a token, so the block is theme-correct without the
 * markup knowing anything about the theme.
 */
function CriteriaHtml({ html }: { html: string }) {
  return (
    <div
      className="text-[13px] leading-[1.6] text-txt3 [&_a]:text-ps-text [&_a]:underline [&_h1]:mb-2 [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:font-bold [&_h3]:mb-1.5 [&_h3]:font-bold [&_li]:mb-1 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-2 [&_strong]:font-semibold [&_table]:my-2 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-bd2 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-bd2 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-5"
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }}
    />
  );
}

export interface AcceptanceCriteriaProps {
  criteria: string[];
  html: string;
}

export function AcceptanceCriteria({ criteria, html }: AcceptanceCriteriaProps) {
  if (criteria.length >= 2) {
    return (
      <div className="flex flex-col gap-2">
        {criteria.map((text, i) => (
          <div
            key={`${i}-${text.slice(0, 24)}`}
            className="flex gap-2.5 text-[13px] leading-[1.55] text-txt3"
          >
            <span className="flex size-[22px] shrink-0 items-center justify-center rounded-[7px] bg-pt font-mono text-[11px] font-bold text-p-on">
              {i + 1}
            </span>
            <span className="min-w-0">{text}</span>
          </div>
        ))}
      </div>
    );
  }

  if (html) return <CriteriaHtml html={html} />;

  if (criteria.length === 1) {
    return (
      <p className="m-0 text-[13px] leading-[1.6] text-txt3">{criteria[0]}</p>
    );
  }

  return (
    <p className="m-0 text-[13px] text-muted">
      This work item has no acceptance criteria in the provider.
    </p>
  );
}
