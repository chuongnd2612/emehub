/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL every API call is prefixed with. Defaults to `/api`, which both
   * the Vite dev proxy and the nginx `location /api/` block forward to the
   * FastAPI backend with the prefix stripped — so the app is same-origin in
   * dev and in production alike, and no CORS or cookie-domain juggling is
   * needed. Override only when pointing the SPA at a differently-hosted hub.
   */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
