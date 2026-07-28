// Stamps `data-mode` and `data-accent` on the app root so the token layer in
// styles/theme.css resolves. Everything downstream reads tokens, never a hex.

import { useEffect, type ReactNode } from "react";
import { useAppearance } from "@/store/appearance";

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const mode = useAppearance((s) => s.mode);
  const accent = useAppearance((s) => s.accent);

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-mode", mode);
    root.setAttribute("data-accent", accent);
  }, [mode, accent]);

  return <>{children}</>;
}
