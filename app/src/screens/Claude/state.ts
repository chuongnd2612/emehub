// Handoff › State Management › the `Claude` group, wired to the hub.
//
// Both halves are now real. `GET /credentials/claude` is the source of truth for
// what is stored and which credential a run would use, and `GET|PUT
// /me/model-preferences` is the source of truth for which models it runs.
//
// ## The two halves persist differently, and that is the point (#200)
//
// Every CREDENTIAL mutation below is its own request that returns fresh state —
// attaching a token, removing one, switching which account runs. There is no
// draft to hold: the file either uploaded or it did not, and holding "you
// removed your token" back behind a Save button would be describing a state the
// hub is not in. Those stay immediate.
//
// MODEL PREFERENCES are a form, and used to be neither: every pick fired a
// `PUT` on change, so there was no way to try a combination before committing
// to it and no way to change your mind. They now edit a draft and commit
// through the shared `SaveBar`, which is the one settings-save idiom across the
// hub. `models` is what the hub has; `draftModels` is what is on screen.
//
// Two shapes the prototype got wrong, corrected against the API:
//
//   • There is ONE shared workspace credential and ONE own credential per
//     user, not a list of shared accounts.
//   • No response returns credential material, so there is no masked token and
//     nothing to reveal. `GET /credentials/claude/resolve` is the agents'
//     endpoint and is deliberately not called from the SPA.

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { toast } from "@/components/ui";
import {
  InvalidCredentialFileError,
  INVALID_CREDENTIAL_TOAST,
  credentialStatus,
  deleteOwnCredential,
  deleteSharedCredential,
  getClaudeCredentialRevision,
  getClaudeUsage,
  getCredentialState,
  getModelPreferences,
  getModelPreferencesRevision,
  setCredentialMode,
  setModelPreferences,
  subscribeModelPreferences,
  statusOfCredential,
  subscribeClaudeCredentials,
  testCredential,
  uploadOwnCredential,
  uploadSharedCredential,
  type ClaudeCredentialMeta,
  type ClaudeCredentialState,
  type ClaudeUsage,
  type CredentialSource,
  type ModelPreferences,
  type CredentialStatus,
  type CredentialTestOutcome,
} from "@/data";
import { ApiError } from "@/lib/api";

/* ── The model catalogue ──────────────────────────────────────────────────
   Handoff › 6. Claude Settings › Models. Product metadata rather than workspace
   data, so it is declared here rather than fetched — but the *ids* are now the
   contract with the hub, which validates a preference against the same set
   (`api/app/services/model_preferences.py` › `KNOWN_MODELS`).

   The id is what is stored and sent; the label is what is shown. They were the
   same string before, which is why this list could drift to naming three models
   that no longer exist without anything failing.                            */

export interface ModelOption {
  /** What the hub stores. Never shown to a user. */
  id: string;
  /** What a user sees. Never sent to the hub. */
  label: string;
  /** Context window, ready to render — e.g. the header chip's "1M ctx" pill. */
  ctxWindow: string;
}

export const MODELS: ModelOption[] = [
  { id: "claude-opus-5", label: "Claude Opus 5", ctxWindow: "1M" },
  { id: "claude-sonnet-5", label: "Claude Sonnet 5", ctxWindow: "1M" },
  { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", ctxWindow: "200K" },
];

/** A stored id -> its display label. Falls back to the id so an unknown model
 *  (an older saved preference, a hub configured with something newer) renders
 *  as itself rather than as an empty control. */
export function modelLabel(id: string): string {
  return MODELS.find((m) => m.id === id)?.label ?? id;
}

/** A stored id -> its {@link ModelOption}, or null when the hub named one this
 *  build does not know about. */
export function modelOption(id: string): ModelOption | null {
  return MODELS.find((m) => m.id === id) ?? null;
}

/* ── Effort ───────────────────────────────────────────────────────────────
   Replaces the handoff's Off/Low/Medium/High "thinking level" chips. Those
   encoded a fixed thinking-token budget, which is not how the current models
   work — they reason adaptively, and the knob that remains is the Claude CLI's
   `--effort`. The five levels below are that flag's accepted values verbatim
   (`api/app/services/model_preferences.py` › `EFFORT_LEVELS`); anything else
   makes the CLI warn and quietly use its own default, which is why the hub
   refuses to store one.

   The handoff's four copy lines described token budgets and no longer map, so
   these are new. They say what the trade-off is and nothing more — there is no
   published speed or quality multiplier to quote.                            */

export interface EffortOption {
  /** What the hub stores, and what reaches `claude --effort`. */
  id: string;
  label: string;
  /** One line under the chips, explaining what picking it costs and buys. */
  note: string;
}

export const EFFORT_LEVELS: EffortOption[] = [
  {
    id: "low",
    label: "Low",
    note: "Fewest steps and least spend. Best for small, well-scoped work.",
  },
  {
    id: "medium",
    label: "Medium",
    note: "Some reasoning before acting, at moderate cost.",
  },
  {
    id: "high",
    label: "High",
    note: "Sustained reasoning. The default, and the right choice for most builds.",
  },
  {
    id: "xhigh",
    label: "Extra high",
    note: "More exploration on work that needs it. Costs more and takes longer.",
  },
  {
    id: "max",
    label: "Max",
    note: "Everything the model has, for the hardest problems. Slowest and most expensive.",
  },
];

/** A stored effort id -> its option, or null when the hub named an unknown one. */
export function effortOption(id: string): EffortOption | null {
  return EFFORT_LEVELS.find((e) => e.id === id) ?? null;
}

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

  /* models + effort — `GET|PUT /me/model-preferences` */
  /** What the hub has. Null until it has answered; the tab shows a loader. */
  models: ModelPreferences | null;
  /** What is on screen. Null alongside `models`, never on its own. */
  draftModels: ModelPreferences | null;
  modelsError: string | null;
  /** True while the save is in flight. */
  savingModels: boolean;
  /** How many model preferences differ from what is saved. Drives `SaveBar`. */
  modelsDirtyCount: number;
  setMainModel: (next: string) => void;
  setEffort: (next: string) => void;
  /** Put the saved values back on screen. */
  discardModels: () => void;
  /** Commit the draft. */
  saveModels: () => void;
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

  const [models, setModels] = useState<ModelPreferences | null>(null);
  const [draftModels, setDraftModels] = useState<ModelPreferences | null>(null);
  /**
   * Whether the user has actually PICKED a model or an effort level.
   *
   * Only consulted while the hub is showing workspace defaults, where a
   * selection equal to the value already on screen is still a real change (see
   * {@link ClaudeSettings.modelsDirtyCount}). It exists so that case does not
   * become "the bar is up the moment you open the tab": it is set from the two
   * setters below, which `Dropdown` calls only on an item click and the effort
   * chips only on a press, so focus, hover and opening the dropdown without
   * choosing anything all leave it false.
   */
  const [modelPicked, setModelPicked] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [savingModels, setSavingModels] = useState(false);

  const reload = useCallback(() => setReloadKey((n) => n + 1), []);

  // The same signal the header chip listens to, in the other direction: the
  // chip's Shared|Personal switch changes the credential from outside this
  // screen, and the screen behind it must not keep describing the old one.
  const revision = useSyncExternalStore(
    subscribeClaudeCredentials,
    getClaudeCredentialRevision,
  );
  useEffect(reload, [reload, revision]);

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

  // Model preferences, on the same signal pattern as the credential half — a
  // later reader (the header chip reports which model a run would use) gets a
  // live value by subscribing, without this screen knowing about it.
  const modelsRevision = useSyncExternalStore(
    subscribeModelPreferences,
    getModelPreferencesRevision,
  );

  useEffect(() => {
    let live = true;
    setModelsError(null);
    getModelPreferences()
      .then((next) => {
        if (!live) return;
        setModels(next);
        setDraftModels(next);
        setModelPicked(false);
      })
      .catch((err: unknown) => {
        if (live)
          setModelsError(errorMessage(err, "Could not load model preferences"));
      });
    return () => {
      live = false;
    };
  }, [modelsRevision]);

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

  const patchDraftModels = useCallback((patch: Partial<ModelPreferences>) => {
    setDraftModels((d) => (d ? { ...d, ...patch } : d));
    setModelPicked(true);
  }, []);

  const setMainModel = useCallback(
    (mainModel: string) => patchDraftModels({ mainModel }),
    [patchDraftModels],
  );
  const setEffort = useCallback(
    (effort: string) => patchDraftModels({ effort }),
    [patchDraftModels],
  );

  const discardModels = useCallback(() => {
    setDraftModels(models);
    setModelPicked(false);
  }, [models]);

  /**
   * How many preferences differ from what is saved.
   *
   * The `usingDefaults` clause is not a workaround for the diff — it is the
   * case the diff cannot see. While the hub is showing workspace defaults there
   * is no preference row at all, so selecting the very value already on screen
   * is a real change of state, from "no preference" to "this preference". A
   * pure value-diff scores that zero, which would leave the pick unsavable and
   * the "showing the defaults" notice up forever.
   *
   * It is gated on a SELECTION, not on the tab being open (#204). Counting it
   * from first paint put the bar on screen claiming a change nobody had made,
   * and a bar that appears because someone looked at the screen teaches people
   * to ignore it — which costs more than the case being protected. Focus,
   * hover, and opening the dropdown and closing it again all leave the count
   * at zero.
   */
  const modelsDirtyCount = useMemo(() => {
    if (!models || !draftModels) return 0;
    if (models.usingDefaults) return modelPicked ? 1 : 0;
    let changed = 0;
    if (draftModels.mainModel !== models.mainModel) changed += 1;
    if (draftModels.effort !== models.effort) changed += 1;
    return changed;
  }, [models, draftModels, modelPicked]);

  /**
   * The whole preference is sent together — the hub validates it and returns
   * the full new state, which becomes both the saved value and the draft. A
   * rejection leaves the draft exactly as the user left it, so the save bar
   * keeps its count and Save is one click from a retry.
   */
  const saveModels = useCallback(() => {
    if (!draftModels || savingModels) return;
    const next = draftModels;
    setSavingModels(true);
    setModelPreferences({ mainModel: next.mainModel, effort: next.effort })
      .then((stored) => {
        setModels(stored);
        setDraftModels(stored);
        // The pick has landed, so it is no longer a pick waiting to be made.
        // `stored.usingDefaults` is false after any write, but clearing this
        // keeps the count honest without depending on that.
        setModelPicked(false);
        toast("Model preferences saved");
      })
      .catch((err: unknown) => {
        toast(
          "Could not save the model preferences",
          "warn",
          errorMessage(err, "The hub rejected the change"),
        );
      })
      .finally(() => setSavingModels(false));
  }, [draftModels, savingModels]);

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
    models,
    draftModels,
    modelsError,
    savingModels,
    modelsDirtyCount,
    setMainModel,
    setEffort,
    discardModels,
    saveModels,
  };
}
