import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import "./styles/theme.css";
import { AppearanceProvider } from "./components/AppearanceProvider";
import { Constellation } from "./components/background";
import { ToastHost } from "./components/ui";
import { router } from "./router";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppearanceProvider>
      {/* Ambient WebGL field — global, not per screen: it sits under both the
          landing view and the app shell, and must survive navigation between
          them. It owns its own fixed container (see Constellation.tsx). */}
      <Constellation />
      <RouterProvider router={router} />
      <ToastHost />
    </AppearanceProvider>
  </StrictMode>,
);
