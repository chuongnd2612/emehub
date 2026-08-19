// Azure DevOps setup — the credential-first flow (#166 / #168).
//
// The generic field grid asks for an organisation URL, a project name and a
// token, in that order, all typed, none verified until `Test connection`. Two
// of those three are things the provider already knows, and the third — the
// token — is the only one the user genuinely has to go and fetch. So this asks
// for the token first and then answers its own questions:
//
//   1. paste the PAT and save        -> the connection now holds a credential
//   2. pick the organisation         -> GET /connections/{id}/organizations
//   3. pick the project              -> GET /connections/{id}/projects
//
// ## The organisation step types by default; the project step picks
//
// Measured against the live service: a PAT scoped to a single organisation — the
// default in the current Azure DevOps UI — is refused by the only host that
// serves the account list, while authenticating perfectly everywhere else. So
// for most tokens the organisation genuinely cannot be discovered, and showing a
// picker that resolves into a text field a second later would be theatre.
//
// The organisation field therefore starts as a text field and *upgrades* to a
// picker only if discovery actually returns something, and only while the field
// is still empty. The project step keeps the picker: it reads
// `dev.azure.com/{org}/_apis/projects`, which an org-scoped token can do, so it
// works for everyone.
//
// Either way both steps keep their text field: an on-premises collection has no
// accounts API at all, and pasting a project URL straight from the ADO address
// bar has always worked and still must.
//
// ## Values still live on `connection.fields`
//
// A picker writes `baseUrl` / `config.project` through the same `onFieldChange`
// the inputs use, so saving, dirty-tracking and the PATCH payload are untouched.
// This component chooses how a value is *entered*, and nothing else.

import { useCallback, useEffect, useRef, useState } from "react";

import { Dropdown, Icon, Input, Spinner } from "@/components/ui";
import {
  discoverConnectionProjects,
  getConnectionOrganizations,
  type Connection,
  type ProviderOrganization,
} from "@/data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

/** What a discovery call can be doing, from the field's point of view. */
type Phase =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready" }
  /** Discovery cannot help — fall back silently, this is not a failure. */
  | { state: "unsupported" }
  /**
   * It failed, and `message` is what the user can act on.
   *
   * `retryable` is the difference between "the provider answered, and the answer
   * was no" and "we never got an answer". Offering `Try again` for the first is
   * worse than offering nothing: a token scoped to one organisation will be
   * refused every time, and a button that promises otherwise wastes the one
   * moment the user was ready to read the sentence next to it.
   */
  | { state: "error"; message: string; retryable: boolean };

const FIELD_BASE_URL = "baseUrl";
const FIELD_PROJECT = "config.project";

/** Sentinel for the picker's last item, which opens the text field instead. */
const MANUAL_ORG = "__manual__";

/**
 * The organisation root of whatever was stored, e.g.
 * `https://dev.azure.com/DDKS/Surveyor` -> `https://dev.azure.com/DDKS`.
 *
 * `base_url` keeps what the user typed, and pasting a *project* URL is both
 * normal and supported (the adapter splits the project back out). Two
 * connections into the same organisation therefore commonly hold two different
 * strings, and a picker listing both would offer the same organisation twice.
 */
function orgRoot(url: string): string {
  const trimmed = (url || "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  try {
    const parsed = new URL(
      /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`,
    );
    const [first] = parsed.pathname.split("/").filter(Boolean);
    // The legacy `{org}.visualstudio.com` host carries the organisation in the
    // hostname, so its first path segment is already the project.
    if (parsed.hostname.toLowerCase().endsWith(".visualstudio.com")) {
      return `${parsed.protocol}//${parsed.host}`;
    }
    return first
      ? `${parsed.protocol}//${parsed.host}/${first}`
      : `${parsed.protocol}//${parsed.host}`;
  } catch {
    return trimmed;
  }
}

/** What to call an organisation in the list: its name, not its URL. */
function orgLabel(url: string): string {
  const root = orgRoot(url);
  try {
    const parsed = new URL(root);
    const [first] = parsed.pathname.split("/").filter(Boolean);
    return first || parsed.hostname;
  } catch {
    return root;
  }
}

/**
 * Turn a bare organisation name into the URL the adapter wants.
 *
 * Typing `DDKS` is the obvious thing to do in a field labelled Organisation, and
 * it used to save a value nothing could connect to. Anything already containing
 * a dot or a slash is left exactly as typed — an on-premises collection or a
 * pasted project URL must not be rewritten.
 */
function normalizeOrgInput(value: string): string {
  const trimmed = (value || "").trim().replace(/\/+$/, "");
  if (!trimmed || /[./\:]/.test(trimmed)) return trimmed;
  return `https://dev.azure.com/${trimmed}`;
}

function messageOf(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

/** A label above a field, matching the generic grid's. */
function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-[7px] text-[11.5px] font-semibold text-muted">
      {children}
    </div>
  );
}

/** The shared trigger: reads like the text input it replaces. */
function PickerButton({
  value,
  placeholder,
  busy,
  open,
  onClick,
  triggerRef,
  label,
}: {
  value: string;
  placeholder: string;
  busy: boolean;
  open: boolean;
  onClick: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  label: string;
}) {
  return (
    <button
      ref={triggerRef}
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-expanded={open}
      className={cn(
        "flex h-10 w-full cursor-pointer items-center gap-2 rounded-control border border-bd2",
        "bg-card2 px-[11px] text-left text-[12.5px] transition-colors duration-200",
        "hover:border-bd focus-visible:border-pb focus-visible:outline-none",
        value ? "text-txt2" : "text-faint",
      )}
    >
      <span className="min-w-0 flex-1 truncate">{value || placeholder}</span>
      {busy ? (
        <Spinner size={13} speed="run" />
      ) : (
        <Icon
          name="chevronRight"
          size={13}
          strokeWidth={2.4}
          className={cn(
            "shrink-0 text-muted transition-transform duration-[.22s]",
            open ? "-rotate-90" : "rotate-90",
          )}
        />
      )}
    </button>
  );
}

/** A one-line explanation under a field, plus the way back to typing. */
function StepNote({
  children,
  action,
  onAction,
}: {
  children: React.ReactNode;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <p className="mt-[6px] mb-0 text-[11.5px] leading-[1.5] text-faint">
      {children}
      {action && onAction && (
        <>
          {" "}
          <button
            type="button"
            onClick={onAction}
            className={cn(
              "cursor-pointer border-0 bg-transparent p-0 text-[11.5px] font-semibold",
              // Muted until hovered. These are secondary affordances sitting under
              // every field; in the accent colour with a permanent underline they
              // read as errors, and three of them turn a calm form into one that
              // looks like it is complaining.
              "text-muted underline decoration-transparent underline-offset-2",
              "transition-colors duration-200 hover:text-txt2 hover:decoration-current",
            )}
          >
            {action}
          </button>
        </>
      )}
    </p>
  );
}

export interface AzureDevOpsSetupProps {
  connection: Connection;
  onFieldChange: (fieldKey: string, value: string) => void;
  /**
   * Organisation URLs already configured elsewhere in the workspace.
   *
   * The reason the picker exists at all for most tokens: Azure DevOps will not
   * enumerate organisations for a token scoped to one of them, but the hub does
   * not need Azure DevOps to know which organisations this workspace uses — it
   * is holding them. So the second connection into an organisation is a choice
   * even though the first one had to be typed.
   */
  knownOrgUrls?: string[];
}

export function AzureDevOpsSetup({
  connection,
  onFieldChange,
  knownOrgUrls = [],
}: AzureDevOpsSetupProps) {
  const fieldValue = (key: string) =>
    connection.fields.find((f) => f.key === key)?.value ?? "";
  const baseUrl = fieldValue(FIELD_BASE_URL);
  const project = fieldValue(FIELD_PROJECT);
  const patField = connection.fields.find((f) => f.key === "pat");

  const [orgs, setOrgs] = useState<ProviderOrganization[]>([]);
  const [orgPhase, setOrgPhase] = useState<Phase>({ state: "idle" });
  // Manual mode is now entered only by asking for it. A failed discovery no
  // longer forces it: the picker is also fed by the organisations this workspace
  // already reaches, so a token that cannot enumerate them does not mean there is
  // nothing to choose from. When there really is nothing, `canPickOrg` is false
  // and the field renders anyway.
  const [orgManual, setOrgManual] = useState(false);

  const [projects, setProjects] = useState<string[]>([]);
  const [projectPhase, setProjectPhase] = useState<Phase>({ state: "idle" });
  const [projectManual, setProjectManual] = useState(false);

  // Which base URL the loaded project list belongs to. Without this, switching
  // organisation leaves the previous org's projects on screen looking like
  // this one's — the worst kind of wrong, because every name is plausible.
  const projectsFor = useRef<string | null>(null);

  const loadOrgs = useCallback(async () => {
    setOrgPhase({ state: "loading" });
    try {
      const result = await getConnectionOrganizations(connection.id);
      if (!result.supported) {
        setOrgPhase({ state: "unsupported" });
        return;
      }
      if (result.error) {
        // The hub reached Azure DevOps and relayed its refusal — a considered
        // answer, not a hiccup.
        setOrgPhase({ state: "error", message: result.error, retryable: false });
        return;
      }
      setOrgs(result.organizations);
      setOrgPhase({ state: "ready" });
      // Upgrade to the picker when there is something to pick and nothing to
      // lose. "Nothing to lose" is the important half: a control that cannot
      // represent the organisation already configured would either drop the
      // value or show a blank where a real setting used to be. So the picker
      // takes over for an empty field, or for one whose value it can display —
      // and an on-premises collection, which discovery will never list, keeps
      // its text field rather than being quietly overwritten.
      const known = result.organizations.some((o) => o.url === baseUrl);
      if (result.organizations.length > 0 && (!baseUrl || known)) setOrgManual(false);
    } catch (err) {
      setOrgPhase({
        state: "error",
        message: messageOf(err, "The hub could not reach Azure DevOps."),
        retryable: true,
      });
    }
  }, [connection.id, baseUrl]);

  const loadProjects = useCallback(
    async (forUrl: string) => {
      setProjectPhase({ state: "loading" });
      try {
        const found = await discoverConnectionProjects(connection.id);
        projectsFor.current = forUrl;
        setProjects(found.map((p) => p.name).filter(Boolean));
        setProjectPhase({ state: "ready" });
      } catch (err) {
        setProjectPhase({
          state: "error",
          message: messageOf(err, "The hub could not list projects."),
          retryable: true,
        });
        setProjectManual(true);
      }
    },
    [connection.id],
  );

  // Organisations, once, as soon as there is a credential to ask with.
  useEffect(() => {
    if (!connection.hasPat) return;
    if (orgPhase.state !== "idle") return;
    void loadOrgs();
  }, [connection.hasPat, orgPhase.state, loadOrgs]);

  // Projects, whenever the *saved* organisation changes — `savedBaseUrl`, never
  // the editable field, because the hub reads the stored connection. So this
  // does not fire on every keystroke, and it does fire after a save.
  useEffect(() => {
    if (!connection.hasPat || !connection.savedBaseUrl) return;
    if (projectsFor.current === connection.savedBaseUrl) return;
    void loadProjects(connection.savedBaseUrl);
  }, [connection.hasPat, connection.savedBaseUrl, loadProjects]);

  /* ── 1. the credential ─────────────────────────────────────────────────── */
  if (!connection.hasPat) {
    return (
      <div className="my-4">
        <div className="max-w-[420px]">
          <FieldLabel>Personal access token</FieldLabel>
          <Input
            type="password"
            value={patField?.value ?? ""}
            placeholder="Required to reach the provider"
            onChange={(e) => onFieldChange("pat", e.target.value)}
            autoComplete="off"
            aria-label="Personal access token"
            className="h-10"
          />
          {/* Deliberately does not promise the organisation list. A token
              scoped to one organisation — the Azure DevOps default — cannot read
              it, so promising it here would set up the next step to look
              broken. */}
          <StepNote>
            Save the token and EmeHub will read what it can from Azure DevOps —
            the project list, and the organisations too if the token can see them.
          </StepNote>
        </div>
      </div>
    );
  }

  const orgBusy = orgPhase.state === "loading";
  const projectBusy = projectPhase.state === "loading";

  // Discovery first (it carries the provider's own names), then everything the
  // workspace already reaches, deduplicated by organisation root.
  const orgChoices = new Map<string, string>();
  for (const o of orgs) orgChoices.set(orgRoot(o.url), o.name || orgLabel(o.url));
  for (const url of knownOrgUrls) {
    const root = orgRoot(url);
    if (root && !orgChoices.has(root)) orgChoices.set(root, orgLabel(root));
  }
  const currentRoot = orgRoot(baseUrl);
  if (currentRoot && !orgChoices.has(currentRoot))
    orgChoices.set(currentRoot, orgLabel(currentRoot));

  const orgItems = [...orgChoices].map(([url, label]) => ({ value: url, label }));
  const projectItems = projects.map((name) => ({ value: name, label: name }));
  const selectedOrg = orgChoices.has(currentRoot)
    ? { name: orgChoices.get(currentRoot) as string }
    : undefined;
  // A picker is worth showing whenever there is anything in it — which, thanks to
  // the workspace's own organisations, is the usual case even when the token
  // cannot list them.
  const canPickOrg = orgItems.length > 0;

  return (
    <div className="my-4 grid grid-cols-2 gap-[14px]">
      {/* ── 2. the organisation ──────────────────────────────────────────── */}
      <div>
        <FieldLabel>Organisation</FieldLabel>
        {orgManual || !canPickOrg ? (
          <>
            <Input
              type="text"
              value={baseUrl}
              placeholder="your-org, or https://dev.azure.com/your-org"
              onChange={(e) => onFieldChange(FIELD_BASE_URL, e.target.value)}
              // On blur, not on change: rewriting the field under a cursor that
              // is still in it makes the next keystroke land somewhere
              // unexpected. Typing `DDKS` in a field labelled Organisation is
              // the obvious thing to do, and it used to save a value nothing
              // could connect to.
              onBlur={(e) => {
                const normalized = normalizeOrgInput(e.target.value);
                if (normalized !== e.target.value)
                  onFieldChange(FIELD_BASE_URL, normalized);
              }}
              autoComplete="off"
              aria-label="Organisation URL"
              className="h-10"
            />
            {orgPhase.state === "error" ? (
              <StepNote
                action={orgPhase.retryable ? "Try again" : undefined}
                onAction={orgPhase.retryable ? () => void loadOrgs() : undefined}
              >
                {orgPhase.message}
              </StepNote>
            ) : orgPhase.state === "unsupported" ? (
              <StepNote>
                Paste the organisation or project URL — a project URL works too.
              </StepNote>
            ) : orgs.length > 0 ? (
              <StepNote
                action="Choose from a list"
                onAction={() => setOrgManual(false)}
              >
                Paste the organisation or project URL.
              </StepNote>
            ) : (
              <StepNote>
                Paste the organisation or project URL — a project URL works too.
              </StepNote>
            )}
          </>
        ) : (
          <>
            <Dropdown
              ddKey={`ado-org-${connection.id}`}
              heading="ORGANISATION"
              width={280}
              value={currentRoot || null}
              items={[
                ...orgItems,
                // Always last, so the list is never a dead end for an
                // organisation the hub has not seen before — which is every
                // organisation, once.
                { value: MANUAL_ORG, label: "Enter a different organisation…" },
              ]}
              onSelect={(url) => {
                if (url === MANUAL_ORG) {
                  setOrgManual(true);
                  return;
                }
                onFieldChange(FIELD_BASE_URL, url);
                // A different organisation means a different project list, and
                // the old selection almost certainly does not exist in it.
                if (url !== baseUrl) onFieldChange(FIELD_PROJECT, "");
              }}
              trigger={({ ref, open, toggle }) => (
                <PickerButton
                  triggerRef={ref}
                  label="Organisation"
                  value={selectedOrg?.name ?? baseUrl}
                  placeholder={orgBusy ? "Reading your organisations…" : "Select an organisation"}
                  busy={orgBusy}
                  open={open}
                  onClick={toggle}
                />
              )}
            />
            {orgs.length > 0 ? (
              <StepNote>Listed from your token.</StepNote>
            ) : (
              // The honest provenance. These are the organisations this
              // workspace already connects to, not a list Azure DevOps gave us —
              // saying "listed from your token" here would be a small lie that
              // makes the missing ones look like a bug.
              <StepNote>
                Organisations this workspace already uses. Add another with
                “Enter a different organisation”.
              </StepNote>
            )}
          </>
        )}
      </div>

      {/* ── 3. the project ───────────────────────────────────────────────── */}
      <div>
        <FieldLabel>Project</FieldLabel>
        {projectManual || projectPhase.state === "error" ? (
          <>
            <Input
              type="text"
              value={project}
              placeholder="Project name"
              onChange={(e) => onFieldChange(FIELD_PROJECT, e.target.value)}
              autoComplete="off"
              aria-label="Project"
              className="h-10"
            />
            {projectPhase.state === "error" ? (
              <StepNote
                action={projectPhase.retryable ? "Try again" : undefined}
                onAction={
                  projectPhase.retryable
                    ? () => void loadProjects(connection.savedBaseUrl)
                    : undefined
                }
              >
                {projectPhase.message}
              </StepNote>
            ) : (
              <StepNote
                action="Choose from a list"
                onAction={() => setProjectManual(false)}
              >
                Type the project name exactly as Azure DevOps shows it.
              </StepNote>
            )}
          </>
        ) : (
          <>
            <Dropdown
              ddKey={`ado-project-${connection.id}`}
              heading="PROJECT"
              width={280}
              value={project || null}
              items={projectItems}
              onSelect={(name) => onFieldChange(FIELD_PROJECT, name)}
              trigger={({ ref, open, toggle }) => (
                <PickerButton
                  triggerRef={ref}
                  label="Project"
                  value={project}
                  placeholder={
                    projectBusy ? "Reading the projects…" : "Select a project"
                  }
                  busy={projectBusy}
                  open={open}
                  onClick={toggle}
                />
              )}
            />
            {/* The project list is read from the *saved* organisation, so this
                is the one place where "save first" has to be said out loud.
                
                The comparison is the selected organisation against the saved one
                — not against the one the list was loaded for. Those two are
                equal right after picking a different organisation, so keying on
                them left this claiming the previous organisation's projects were
                "listed from the saved organisation" while showing a project
                field that had just been cleared. */}
            {!baseUrl ? (
              <StepNote>Choose an organisation first.</StepNote>
            ) : baseUrl !== connection.savedBaseUrl ||
              projectsFor.current !== connection.savedBaseUrl ? (
              <StepNote action="Enter it manually" onAction={() => setProjectManual(true)}>
                Save the organisation to list its projects.
              </StepNote>
            ) : projectPhase.state === "ready" && projects.length === 0 ? (
              <StepNote action="Enter it manually" onAction={() => setProjectManual(true)}>
                No projects are visible to this token in that organisation.
              </StepNote>
            ) : (
              <StepNote action="Enter it manually" onAction={() => setProjectManual(true)}>
                Listed from the saved organisation.
              </StepNote>
            )}
          </>
        )}
      </div>

      {/* The credential keeps its field, so it can be rotated without starting
          again — empty means "keep the stored one", as everywhere else. */}
      <div>
        <FieldLabel>Personal access token</FieldLabel>
        <Input
          type="password"
          value={patField?.value ?? ""}
          placeholder="Stored — type a new one to replace it"
          onChange={(e) => onFieldChange("pat", e.target.value)}
          autoComplete="off"
          aria-label="Personal access token"
          className="h-10"
        />
      </div>
    </div>
  );
}
