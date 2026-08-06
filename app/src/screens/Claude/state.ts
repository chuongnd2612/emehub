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
  statusOfCredential,
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

export type CredentialStatusLabel =
  | "Active"
  | "Expiring"
  | "Refreshes"
  | "Expired";

const STATUS_LABEL: Record<CredentialStatus, CredentialStatusLabel> = {
  active: "Active",
  expiring: "Expiring",
  // Issue #63. Not "Active" — the access token on file really has lapsed. Not
  // "Expired" — nothing is broken and there is nothing for the user to do.
  refreshable: "Refreshes",
  expired: "Expired",
};

/** `active | expiring | refreshable | expired` -> the StatusPill label. */
export function statusLabel(daysLeft: number | null): CredentialStatusLabel {
  return STATUS_LABEL[credentialStatus(daysLeft)];
}

/**
 * The pill for one stored credential. Prefer this over {@link statusLabel}
 * wherever the whole `ClaudeCredentialMeta` is in hand: `daysLeft` alone cannot
 * express "elapsed, but it refreshes itself" (issue #63), and it rounds, so an
 * access token that lapsed three hours ago looks merely *expiring* through it.
 */
export function metaStatusLabel(
  meta: ClaudeCredentialMeta,
): CredentialStatusLabel {
  return STATUS_LABEL[statusOfCredential(meta)];
}

/** One line explaining a `Refreshes` pill, or null when there is nothing to say. */
export function statusNote(meta: ClaudeCredentialMeta): string | null {
  if (statusOfCredential(meta) !== "refreshable") return null;
  return "The access token has expired — the Claude CLI renews it from the refresh token on the next run.";
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
          toast("Attach your Claude account", "info");
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
            "ok",
          );
        })
        .catch((err: unknown) => {
          setSourceOverride(null);
          toast(
            "Could not switch account",
            "warn",
            errorMessage(err, "The hub rejected the change"),
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
          toast("Personal token attached");
        })
        .catch((err: unknown) => {
          if (err instanceof InvalidCredentialFileError) {
            // The body explains WHY the file was rejected, which the user needs
            // in order to export the right one.
            toast(
              INVALID_CREDENTIAL_TOAST.title,
              "warn",
              INVALID_CREDENTIAL_TOAST.body,
            );
            return;
          }
          toast(
            "Upload failed",
            "warn",
            errorMessage(err, "The hub rejected the credential"),
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
        // Kept: which account runs now is a consequence, not a restatement.
        toast(
          "Personal token removed",
          "warn",
          "Falling back to the shared account",
        );
      })
      .catch((err: unknown) => {
        toast(
          "Could not remove the token",
          "warn",
          errorMessage(err, "The hub rejected the change"),
        );
      });
  }, [apply]);

  const addShared = useCallback(
    (file: File) => {
      setUploadingShared(true);
      uploadSharedCredential(file)
        .then((updated) => {
          apply(updated);
          toast("Shared credential added");
        })
        .catch((err: unknown) => {
          if (err instanceof InvalidCredentialFileError) {
            // The body explains WHY the file was rejected, which the user needs
            // in order to export the right one.
            toast(
              INVALID_CREDENTIAL_TOAST.title,
              "warn",
              INVALID_CREDENTIAL_TOAST.body,
            );
            return;
          }
          toast(
            "Upload failed",
            "warn",
            errorMessage(err, "The hub rejected the credential"),
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
          "warn",
          "Assigned members fall back to the default account",
        );
      })
      .catch((err: unknown) => {
        toast(
          "Could not remove the credential",
          "warn",
          errorMessage(err, "The hub rejected the change"),
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
        // The hub's verdict is reported verbatim on failure; a success needs
        // no elaboration.
        toast(
          result.ok ? "Credential verified" : "Credential check failed",
          result.ok ? "ok" : "warn",
          result.ok ? undefined : result.message,
        );
      })
      .catch((err: unknown) => {
        const message = errorMessage(err, "The hub did not answer");
        setTestResult({ ok: false, result: "error", message });
        toast("Credential check failed", "warn", message);
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
