// The tracked section label + hairline rule that opens each landing section
// (`THE AGENTS`, `THE PLATFORM UNDERNEATH`).

export function SectionLabel({ children }: { children: string }) {
  return (
    <div className="mb-[22px] flex items-baseline gap-[13px]">
      <span className="text-[11px] font-bold tracking-[.15em] text-label">
        {children}
      </span>
      <span className="h-px flex-1 bg-bd2" />
    </div>
  );
}
