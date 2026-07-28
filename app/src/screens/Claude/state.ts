// Handoff › State Management › the `Claude` group:
//   credSource, personalCred, sharedCreds[], revealed{}, credMenu,
//   uploadingPersonal, uploadingShared, mainModel, fastModel, thinking,
//   prefAuto, prefEvidence, prefStream, prefParallel, apiKey, showKey.
//
// All of it is screen-local UI/data state, so it lives in one hook that the
// screen root owns — switching tabs must not lose an upload or a model choice,
// and `store/ui.ts` is reserved for cross-screen UI state (CLAUDE.md).
//
// Everything that talks to a credential goes through the typed data layer
// (`@/data`); the `.credentials.json` parser there is REAL, not a stub.

import { useCallback, useEffect, useState } from "react";
import { toast } from "@/components/ui";
import {
  credentialStatus,
  getSharedCredentials,
  removeCredential,
  rotateCredential,
  setDefaultCredential,
  uploadCredential,
  INVALID_CREDENTIAL_TOAST,
  type CredentialSource,
  type CredentialStatus,
  type PersonalCredential,
  type SharedCredential,
} from "@/data";

/* ── Static option sets ───────────────────────────────────────────────────
   Handoff › 6. Claude Settings › Models. These are model/product metadata
   rather than workspace data, and the hub exposes no endpoint for them yet,
   so they are declared here. When `GET /api/settings/claude` lands they move
   behind the data layer with everything else.                              */

export const MODELS: string[] = [
  "Claude Opus 4.6",
  "Claude Sonnet 4.6",
  "Claude Haiku 4.5",
];

export const THINKING_LEVELS: string[] = ["Off", "Low", "Medium", "High"];

/** One line per thinking level, in the same order. Copy is final. */
export const THINKING_NOTES: string[] = [
  "Agents answer directly — fastest, cheapest.",
  "Short reasoning before acting.",
  "Balanced reasoning for most QA and coding work.",
  "Deep reasoning on every step — slowest.",
];

/**
 * The CI fallback key. Never rendered in full unless the user presses `Show`
 * (CLAUDE.md › "Never log or return a secret" — the UI equivalent is that a
 * secret is masked until an explicit reveal).
 */
// STUB: GET /api/settings/claude — the hub will return this masked.
const API_KEY_FALLBACK = "sk-ant-api03-7fJk2LmQ9xRb4TnW8vZc1Hs6";

/** Handoff › Async behaviours › "Test connection" — 1300 ms. */
const TEST_DELAY_MS = 1300;

/** `active | expiring | expired` -> the StatusPill label. */
export function statusLabel(daysLeft: number | null): "Active" | "Expiring" | "Expired" {
  const s: CredentialStatus = credentialStatus(daysLeft);
  return s === "active" ? "Active" : s === "expiring" ? "Expiring" : "Expired";
}

/** The default shared credential: `isDefault`, falling back to the first. */
export function defaultShared(creds: SharedCredential[]): SharedCredential | null {
  return creds.find((c) => c.isDefault) ?? creds[0] ?? null;
}

export interface ClaudeSettings {
  /* credentials */
  credSource: CredentialSource;
  chooseSource: (next: CredentialSource) => void;
  personal: PersonalCredential | null;
  shared: SharedCredential[];
  uploadingPersonal: boolean;
  uploadingShared: boolean;
  revealed: Record<string, boolean>;
  toggleReveal: (id: string) => void;
  attachPersonal: (file: File) => void;
  removePersonal: () => void;
  addShared: (file: File) => void;
  rotateShared: (id: string, file: File) => void;
  removeShared: (id: string) => void;
  makeDefault: (id: string) => void;
  apiKey: string;
  showKey: boolean;
  setShowKey: (next: boolean) => void;

  /* connection health */
  testing: boolean;
  testConnection: () => void;

  /* models */
  mainModel: string;
  setMainModel: (next: string) => void;
  fastModel: string;
  setFastModel: (next: string) => void;
  thinking: number;
  setThinking: (next: number) => void;
  parallel: number;
  setParallel: (next: number) => void;

  /* agent preferences */
  prefAuto: boolean;
  setPrefAuto: (next: boolean) => void;
  prefEvidence: boolean;
  setPrefEvidence: (next: boolean) => void;
  prefStream: boolean;
  setPrefStream: (next: boolean) => void;
}

export function useClaudeSettings(): ClaudeSettings {
  const [credSource, setCredSource] = useState<CredentialSource>("shared");
  const [personal, setPersonal] = useState<PersonalCredential | null>(null);
  const [shared, setShared] = useState<SharedCredential[]>([]);
  const [uploadingPersonal, setUploadingPersonal] = useState(false);
  const [uploadingShared, setUploadingShared] = useState(false);
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);

  const [mainModel, setMainModel] = useState<string>("Claude Sonnet 4.6");
  const [fastModel, setFastModel] = useState<string>("Claude Haiku 4.5");
  const [thinking, setThinking] = useState(2);
  const [parallel, setParallel] = useState(2);

  const [prefAuto, setPrefAuto] = useState(true);
  const [prefEvidence, setPrefEvidence] = useState(true);
  const [prefStream, setPrefStream] = useState(false);

  useEffect(() => {
    let live = true;
    void getSharedCredentials().then((rows) => {
      if (live) setShared(rows);
    });
    return () => {
      live = false;
    };
  }, []);

  /**
   * Connection health › `Test connection`. The handoff's Async-behaviours row
   * for a connection test is 1300 ms of `Testing…` + a spinner, then a toast;
   * the numbers echoed back are the ones the health row itself shows.
   */
  // STUB: POST /api/credentials/claude/test
  const testConnection = useCallback(() => {
    setTesting(true);
    window.setTimeout(() => {
      setTesting(false);
      toast("Connection verified", "Claude responded in 42 ms · HTTP 200", "ok");
    }, TEST_DELAY_MS);
  }, []);

  const toggleReveal = useCallback((id: string) => {
    setRevealed((r) => ({ ...r, [id]: !r[id] }));
  }, []);

  const chooseSource = useCallback(
    (next: CredentialSource) => {
      setCredSource(next);
      if (next === "personal" && !personal) {
        toast(
          "Attach your Claude account",
          "Drop your .credentials.json below to run on your own plan",
          "info",
        );
        return;
      }
      toast(
        next === "shared" ? "Using the shared account" : "Using your personal account",
        next === "shared"
          ? "Admin-maintained token applied to your agent runs"
          : "Your own Claude plan will be spent",
        "ok",
      );
    },
    [personal],
  );

  const attachPersonal = useCallback((file: File) => {
    setUploadingPersonal(true);
    // uploadCredential parses for real, then dwells the handoff's 850 ms.
    uploadCredential(file)
      .then((cred) => {
        setPersonal(cred);
        setCredSource("personal");
        toast("Personal token attached", "Your agents now run on your own Claude plan", "ok");
      })
      .catch(() => {
        toast(INVALID_CREDENTIAL_TOAST.title, INVALID_CREDENTIAL_TOAST.body, "warn");
      })
      .finally(() => setUploadingPersonal(false));
  }, []);

  const removePersonal = useCallback(() => {
    setPersonal(null);
    setCredSource("shared");
    setRevealed({});
    toast("Personal token removed", "Falling back to the shared workspace account", "warn");
  }, []);

  const addShared = useCallback((file: File) => {
    setUploadingShared(true);
    // STUB: POST /api/credentials/claude/shared — the data layer has no
    // add-shared call yet, so the personal upload path supplies the parsed
    // token and the workspace fields are filled in here.
    uploadCredential(file)
      .then((cred) => {
        setShared((rows) => {
          const next: SharedCredential = {
            id: `sc${Date.now()}`,
            label: cred.filename.replace(/\.json$/, "").replace(/\.credentials$/, ""),
            email: "—",
            subscription: cred.subscription,
            expiresDisplay: cred.expiresDisplay,
            daysLeft: cred.daysLeft,
            scopes: cred.scopes,
            lastRefreshed: cred.lastRefreshed,
            members: 0,
            // The first upload becomes the default (Handoff § 6).
            isDefault: rows.length === 0,
            token: cred.token,
            source: `uploaded · ${cred.filename}`,
          };
          return [...rows, next];
        });
        toast(
          "Shared credential added",
          "Written to .claude/.credentials.json for assigned members",
          "ok",
        );
      })
      .catch(() => {
        toast(INVALID_CREDENTIAL_TOAST.title, INVALID_CREDENTIAL_TOAST.body, "warn");
      })
      .finally(() => setUploadingShared(false));
  }, []);

  const rotateShared = useCallback((id: string, file: File) => {
    setUploadingShared(true);
    rotateCredential(id, file)
      .then((rotated) => {
        setShared((rows) =>
          rows.map((c) => (c.id === id ? { ...rotated, isDefault: c.isDefault, members: c.members, email: c.email } : c)),
        );
        toast("Token rotated", "Agent runs now authenticate with the new token", "ok");
      })
      .catch(() => {
        toast(INVALID_CREDENTIAL_TOAST.title, INVALID_CREDENTIAL_TOAST.body, "warn");
      })
      .finally(() => setUploadingShared(false));
  }, []);

  const removeShared = useCallback((id: string) => {
    setShared((rows) => rows.filter((c) => c.id !== id));
    void removeCredential(id);
    toast("Shared credential removed", "Assigned members fall back to the default account", "warn");
  }, []);

  const makeDefault = useCallback((id: string) => {
    // The endpoint returns the server's list; locally-added rows are not in it
    // yet, so the flag is flipped on the rows this screen actually holds.
    void setDefaultCredential(id);
    setShared((rows) => rows.map((c) => ({ ...c, isDefault: c.id === id })));
    toast("Default account set", "New agent runs authenticate with this credential", "ok");
  }, []);

  return {
    credSource,
    chooseSource,
    personal,
    shared,
    uploadingPersonal,
    uploadingShared,
    revealed,
    toggleReveal,
    attachPersonal,
    removePersonal,
    addShared,
    rotateShared,
    removeShared,
    makeDefault,
    apiKey: API_KEY_FALLBACK,
    showKey,
    setShowKey,
    testing,
    testConnection,
    mainModel,
    setMainModel,
    fastModel,
    setFastModel,
    thinking,
    setThinking,
    parallel,
    setParallel,
    prefAuto,
    setPrefAuto,
    prefEvidence,
    setPrefEvidence,
    prefStream,
    setPrefStream,
  };
}
