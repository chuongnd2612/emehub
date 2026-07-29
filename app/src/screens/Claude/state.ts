// Handoff › State Management › the `Claude` group, wired to the hub.
//
// The credential half is now real: `GET /credentials/claude` is the source of
// truth for what is stored and which credential a run would use, and every
// mutation goes through `@/data`. The models / agent-preferences half is still
// local component state — the hub has no settings resource (verified against
// `/api/openapi.json`), and the tabs that render it say so.
//
// Two shapes the prototype got wrong, corrected against the API:
//
//   • There is ONE shared workspace credential and ONE own credential per
//     user, not a list of shared accounts.
//   • No response returns credential material, so there is no masked token and
//     nothing to reveal. `GET /credentials/claude/resolve` is the agents'
//     endpoint and is deliberately not called from the SPA.

import { useCallback, useEffect, useState } from "react";
import { toast } from "@/components/ui";
import {
  InvalidCredentialFileError,
  INVALID_CREDENTIAL_TOAST,
  credentialStatus,
  deleteOwnCredential,
  deleteSharedCredential,
  getClaudeUsage,
  getCredentialState,
  setCredentialMode,
  testCredential,
  uploadOwnCredential,
  uploadSharedCredential,
  type ClaudeCredentialMeta,
  type ClaudeCredentialState,
  type ClaudeUsage,
  type CredentialSource,
  type CredentialStatus,
  type CredentialTestOutcome,
} from "@/data";
import { ApiError } from "@/lib/api";

/* ── Static option sets ───────────────────────────────────────────────────
   Handoff › 6. Claude Settings › Models. Model and product metadata rather
   than workspace data, and the hub exposes no settings endpoint, so they are
   declared here and the tabs that use them label themselves preview.        */

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

/** `active | expiring | expired` -> the StatusPill label. */
export function statusLabel(
  daysLeft: number | null,
): "Active" | "Expiring" | "Expired" {
  const s: CredentialStatus = credentialStatus(daysLeft);
  return s === "active" ? "Active" : s === "expiring" ? "Expiring" : "Expired";
}

/** The hub's message when it has one, the exception's otherwise. */
export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

export type LoadStatus = "loading" | "ready" | "error";

export interface ClaudeSettings {
  /* credential state */
  load: LoadStatus;
  loadError: string | null;
  reload: () => void;
  hasOwn: boolean;
  hasShared: boolean;
  /** Which credential a run would actually authenticate with. */
  mode: ClaudeCredentialState["mode"];
  own: ClaudeCredentialMeta | null;
  shared: ClaudeCredentialMeta | null;

  /* the source chooser */
  credSource: CredentialSource;
  chooseSource: (next: CredentialSource) => void;
  switching: boolean;

  /* uploads */
  uploadingPersonal: boolean;
  uploadingShared: boolean;
  attachPersonal: (file: File) => void;
  removePersonal: () => void;
  addShared: (file: File) => void;
  removeShared: () => void;

  /* credential check */
  testing: boolean;
  testResult: CredentialTestOutcome | null;
  testConnection: () => void;

  /* usage */
  usage: ClaudeUsage | null;
  usageError: string | null;

  /* models — local only, no endpoint */
  mainModel: string;
  setMainModel: (next: string) => void;
  fastModel: string;
  setFastModel: (next: string) => void;
  thinking: number;
  setThinking: (next: number) => void;
  parallel: number;
  setParallel: (next: number) => void;

  /* agent preferences — local only, no endpoint */
  prefAuto: boolean;
  setPrefAuto: (next: boolean) => void;
  prefEvidence: boolean;
  setPrefEvidence: (next: boolean) => void;
  prefStream: boolean;
  setPrefStream: (next: boolean) => void;
}

export function useClaudeSettings(): ClaudeSettings {
  const [state, setState] = useState<ClaudeCredentialState | null>(null);
  const [load, setLoad] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  /**
   * The chooser is a view over `mode`, with one override: a member who picks
   * "Your own account" before uploading anything needs to SEE the drop zone,
   * and there is nothing to persist until a file exists.
   */
  const [sourceOverride, setSourceOverride] = useState<CredentialSource | null>(
    null,
  );
  const [switching, setSwitching] = useState(false);
  const [uploadingPersonal, setUploadingPersonal] = useState(false);
  const [uploadingShared, setUploadingShared] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<CredentialTestOutcome | null>(
    null,
  );
  const [usage, setUsage] = useState<ClaudeUsage | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);

  const [mainModel, setMainModel] = useState<string>("Claude Sonnet 4.6");
  const [fastModel, setFastModel] = useState<string>("Claude Haiku 4.5");
  const [thinking, setThinking] = useState(2);
  const [parallel, setParallel] = useState(2);

  const [prefAuto, setPrefAuto] = useState(true);
  const [prefEvidence, setPrefEvidence] = useState(true);
  const [prefStream, setPrefStream] = useState(false);

  const reload = useCallback(() => setReloadKey((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    setLoad("loading");
    setLoadError(null);
    getCredentialState()
      .then((next) => {
        if (!live) return;
        setState(next);
        setLoad("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setLoadError(errorMessage(err, "Could not reach the hub"));
        setLoad("error");
      });
    return () => {
      live = false;
    };
  }, [reloadKey]);

  useEffect(() => {
    let live = true;
    setUsageError(null);
    getClaudeUsage()
      .then((next) => {
        if (live) setUsage(next);
      })
      .catch((err: unknown) => {
        if (live) setUsageError(errorMessage(err, "Could not load usage"));
      });
    return () => {
      live = false;
    };
  }, [reloadKey]);

  const hasOwn = state?.hasOwn ?? false;
  const hasShared = state?.hasShared ?? false;
  const mode = state?.mode ?? "none";
  const credSource: CredentialSource =
    sourceOverride ?? (mode === "own" ? "personal" : "shared");

  const apply = useCallback((next: ClaudeCredentialState) => {
    setState(next);
    setSourceOverride(null);
    // A changed credential invalidates the last verdict.
    setTestResult(null);
  }, []);

  const chooseSource = useCallback(
    (next: CredentialSource) => {
      if (next === credSource) return;
      setSourceOverride(next);

      if (!hasOwn) {
        // Nothing is stored under this user, so there is no preference to
        // persist — the hub 400s a mode change with no own credential on file.
        if (next === "personal") {
          toast(
            "Attach your Claude account",
            "Drop your .credentials.json below to run on your own plan",
            "info",
          );
        }
        return;
      }

      setSwitching(true);
      setCredentialMode(next === "personal" ? "own" : "shared")
        .then((updated) => {
          apply(updated);
          toast(
            next === "shared"
              ? "Using the shared account"
              : "Using your personal account",
            next === "shared"
              ? "Admin-maintained token applied to your agent runs"
              : "Your own Claude plan will be spent",
            "ok",
          );
        })
        .catch((err: unknown) => {
          setSourceOverride(null);
          toast(
            "Could not switch account",
            errorMessage(err, "The hub rejected the change"),
            "warn",
          );
        })
        .finally(() => setSwitching(false));
    },
    [apply, credSource, hasOwn],
  );

  /** Parse locally, then PUT. An invalid file never reaches the network. */
  const attachPersonal = useCallback(
    (file: File) => {
      setUploadingPersonal(true);
      uploadOwnCredential(file)
        .then((updated) => {
          apply(updated);
          toast(
            "Personal token attached",
            "Your agents now run on your own Claude plan",
            "ok",
          );
        })
        .catch((err: unknown) => {
          if (err instanceof InvalidCredentialFileError) {
            toast(
              INVALID_CREDENTIAL_TOAST.title,
              INVALID_CREDENTIAL_TOAST.body,
              "warn",
            );
            return;
          }
          toast(
            "Upload failed",
            errorMessage(err, "The hub rejected the credential"),
            "warn",
          );
        })
        .finally(() => setUploadingPersonal(false));
    },
    [apply],
  );

  const removePersonal = useCallback(() => {
    deleteOwnCredential()
      .then(getCredentialState)
      .then((updated) => {
        apply(updated);
        toast(
          "Personal token removed",
          "Falling back to the shared workspace account",
          "warn",
        );
      })
      .catch((err: unknown) => {
        toast(
          "Could not remove the token",
          errorMessage(err, "The hub rejected the change"),
          "warn",
        );
      });
  }, [apply]);

  const addShared = useCallback(
    (file: File) => {
      setUploadingShared(true);
      uploadSharedCredential(file)
        .then((updated) => {
          apply(updated);
          toast(
            "Shared credential added",
            "Written to .claude/.credentials.json for assigned members",
            "ok",
          );
        })
        .catch((err: unknown) => {
          if (err instanceof InvalidCredentialFileError) {
            toast(
              INVALID_CREDENTIAL_TOAST.title,
              INVALID_CREDENTIAL_TOAST.body,
              "warn",
            );
            return;
          }
          toast(
            "Upload failed",
            errorMessage(err, "The hub rejected the credential"),
            "warn",
          );
        })
        .finally(() => setUploadingShared(false));
    },
    [apply],
  );

  const removeShared = useCallback(() => {
    deleteSharedCredential()
      .then(getCredentialState)
      .then((updated) => {
        apply(updated);
        toast(
          "Shared credential removed",
          "Assigned members fall back to the default account",
          "warn",
        );
      })
      .catch((err: unknown) => {
        toast(
          "Could not remove the credential",
          errorMessage(err, "The hub rejected the change"),
          "warn",
        );
      });
  }, [apply]);

  /**
   * `POST /credentials/claude/test`. A storage check, not a liveness probe —
   * the hub never calls Claude — so the health row reports the hub's verdict
   * verbatim rather than a latency the prototype invented.
   */
  const testConnection = useCallback(() => {
    setTesting(true);
    testCredential()
      .then((result) => {
        setTestResult(result);
        toast(
          result.ok ? "Credential verified" : "Credential check failed",
          result.message,
          result.ok ? "ok" : "warn",
        );
      })
      .catch((err: unknown) => {
        const message = errorMessage(err, "The hub did not answer");
        setTestResult({ ok: false, result: "error", message });
        toast("Credential check failed", message, "warn");
      })
      .finally(() => setTesting(false));
  }, []);

  return {
    load,
    loadError,
    reload,
    hasOwn,
    hasShared,
    mode,
    own: state?.own ?? null,
    shared: state?.shared ?? null,
    credSource,
    chooseSource,
    switching,
    uploadingPersonal,
    uploadingShared,
    attachPersonal,
    removePersonal,
    addShared,
    removeShared,
    testing,
    testResult,
    testConnection,
    usage,
    usageError,
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
