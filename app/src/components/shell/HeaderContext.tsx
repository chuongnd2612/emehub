// The page header's title/subtitle come from the screen, not from the shell.
//
// Screens call:
//     useHeader("Projects & Repositories", "Repositories, connected agents…");
//
// The value is stored together with the pathname that set it. The reader
// compares against the CURRENT pathname and falls back to the route table when
// they differ, so navigating away never leaves the previous screen's title on
// screen — and we avoid the effect-ordering trap of "parent resets, child sets"
// (child effects run first, so a parent reset would clobber the new title).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";

import { routeHeader, type HeaderContent } from "./nav";

interface HeaderEntry extends HeaderContent {
  path: string;
}

interface HeaderCtxValue {
  entry: HeaderEntry | null;
  set: (entry: HeaderEntry) => void;
}

const HeaderCtx = createContext<HeaderCtxValue | null>(null);

export function HeaderProvider({ children }: { children: ReactNode }) {
  const [entry, setEntry] = useState<HeaderEntry | null>(null);

  const set = useCallback((next: HeaderEntry) => {
    setEntry((prev) =>
      prev &&
      prev.path === next.path &&
      prev.title === next.title &&
      prev.subtitle === next.subtitle
        ? prev
        : next,
    );
  }, []);

  const value = useMemo<HeaderCtxValue>(() => ({ entry, set }), [entry, set]);
  return <HeaderCtx.Provider value={value}>{children}</HeaderCtx.Provider>;
}

/**
 * Set the page header from a screen. Call it at the top of the screen
 * component; safe to call with values that change between renders.
 *
 * Outside the app shell (e.g. the landing view) it is a no-op.
 */
export function useHeader(title: string, subtitle = "") {
  const ctx = useContext(HeaderCtx);
  const { pathname } = useLocation();
  const set = ctx?.set;

  useEffect(() => {
    set?.({ path: pathname, title, subtitle });
  }, [set, pathname, title, subtitle]);
}

/** What the shell renders. Falls back to the route table. */
export function useHeaderContent(): HeaderContent {
  const ctx = useContext(HeaderCtx);
  const { pathname } = useLocation();

  return useMemo(() => {
    if (ctx?.entry && ctx.entry.path === pathname) {
      return { title: ctx.entry.title, subtitle: ctx.entry.subtitle };
    }
    return routeHeader(pathname);
  }, [ctx?.entry, pathname]);
}
