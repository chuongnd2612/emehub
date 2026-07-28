// Handoff § 0. App shell — the frame every /app page renders inside.
//
//   root:   position:relative; display:flex; height:100vh; width:100%;
//           padding:14px; gap:14px  (everything floats over the ambient stack)
//   aside:  268px sidebar
//   main:   page header + the scroll region (flex:1; min-height:0;
//           overflow-y:auto; padding:2px 4px 20px 2px)
//
// Overlays (command palette, Claude credential popover) portal to
// document.body — see components/overlays.

import { useCallback, useEffect, useRef } from "react";
import { Outlet } from "react-router-dom";

import { CommandPalette } from "@/components/overlays";
import {
  BackgroundStack,
  HeaderProvider,
  PageHeader,
  Sidebar,
} from "@/components/shell";
import { useUi } from "@/store/ui";

export default function AppLayout() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const togglePalette = useUi((s) => s.togglePalette);
  const setClaudeOpen = useUi((s) => s.setClaudeOpen);
  const closeAll = useUi((s) => s.closeAll);

  // Handoff › Keyboard: ⌘K / Ctrl+K toggles the palette; Esc closes every
  // overlay. Individual overlays also handle Esc so they work in isolation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setClaudeOpen(false);
        togglePalette();
        return;
      }
      if (e.key === "Escape") closeAll();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeAll, setClaudeOpen, togglePalette]);

  // Handoff › Interactions › Navigation: the sidebar resets the scroll
  // container to scrollTop = 0.
  const resetScroll = useCallback(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, []);

  return (
    <HeaderProvider>
      <BackgroundStack />

      <div className="relative z-[2] flex h-screen w-full gap-3.5 p-3.5">
        <Sidebar onNavigate={resetScroll} />

        <main className="flex min-w-0 flex-1 flex-col gap-3.5">
          <PageHeader />

          <div
            ref={scrollRef}
            className="min-h-0 flex-1 overflow-y-auto pt-[2px] pr-1 pb-5 pl-[2px]"
          >
            <Outlet />
          </div>
        </main>
      </div>

      <CommandPalette />
    </HeaderProvider>
  );
}
