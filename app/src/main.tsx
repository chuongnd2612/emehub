import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import "./styles/theme.css";
import { AppearanceProvider } from "./components/AppearanceProvider";
import { ToastHost } from "./components/ui";
import { router } from "./router";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppearanceProvider>
      <RouterProvider router={router} />
      <ToastHost />
    </AppearanceProvider>
  </StrictMode>,
);
