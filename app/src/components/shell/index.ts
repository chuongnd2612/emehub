// Barrel for the app shell. Screens only ever need `useHeader` from here:
//
//     import { useHeader } from "@/components/shell";
//     useHeader("Tickets", "Read-only mirror of Azure DevOps and Jira work items");

export { BackgroundStack, CONSTELLATION_ROOT_ID } from "./BackgroundStack";
export { HeaderProvider, useHeader, useHeaderContent } from "./HeaderContext";
export { PageHeader } from "./PageHeader";
export { Sidebar } from "./Sidebar";
export { NAV_GROUPS, ROUTE_HEADER, routeHeader } from "./nav";
export type { HeaderContent, NavGroup, NavItem } from "./nav";
