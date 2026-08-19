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
// ## Every step keeps its text field
//
// The pickers are the fast path, never the only one. A PAT scoped without
// `vso.profile` cannot list organisations while working perfectly for everything
// else; an on-premises collection has no accounts API at all; and pasting a
// project URL straight from the ADO address bar has always worked and still
// must. Each step therefore falls back to typing — automatically when discovery
// says it cannot help, and on request otherwise — with the reason shown rather
// than a picker that is mysteriously empty.
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
  /** It failed, and `message` is what the user can act on. */
  | { state: "error"; message: string };

const FIELD_BASE_URL = "baseUrl";
const FIELD_PROJECT = "config.project";

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
            className="cursor-pointer border-0 bg-transparent p-0 text-[11.5px] font-semibold text-pl underline underline-offset-2"
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
}

export function AzureDevOpsSetup({
  connection,
  onFieldChange,
}: AzureDevOpsSetupProps) {
  const fieldValue = (key: string) =>
    connection.fields.find((f) => f.key === key)?.value ?? "";
  const baseUrl = fieldValue(FIELD_BASE_URL);
  const project = fieldValue(FIELD_PROJECT);
  const patField = connection.fields.find((f) => f.key === "pat");

  const [orgs, setOrgs] = useState<ProviderOrganization[]>([]);
  const [orgPhase, setOrgPhase] = useState<Phase>({ state: "idle" });
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
        setOrgManual(true);
        return;
      }
      if (result.error) {
        setOrgPhase({ state: "error", message: result.error });
        setOrgManual(true);
        return;
      }
      setOrgs(result.organizations);
      setOrgPhase({ state: "ready" });
    } catch (err) {
      setOrgPhase({
        state: "error",
        message: messageOf(err, "The hub could not reach Azure DevOps."),
      });
      setOrgManual(true);
    }
  }, [connection.id]);

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
          <StepNote>
            Save the token and EmeHub will list the organisations and projects it
            can reach, so there is nothing else to type.
          </StepNote>
        </div>
      </div>
    );
  }

  const orgBusy = orgPhase.state === "loading";
  const projectBusy = projectPhase.state === "loading";
  const orgItems = orgs.map((o) => ({ value: o.url, label: o.name }));
  const projectItems = projects.map((name) => ({ value: name, label: name }));
  const selectedOrg = orgs.find((o) => o.url === baseUrl);

  return (
    <div className="my-4 grid grid-cols-2 gap-[14px]">
      {/* ── 2. the organisation ──────────────────────────────────────────── */}
      <div>
        <FieldLabel>Organisation</FieldLabel>
        {orgManual || orgPhase.state === "error" || orgPhase.state === "unsupported" ? (
          <>
            <Input
              type="text"
              value={baseUrl}
              placeholder="https://dev.azure.com/your-org"
              onChange={(e) => onFieldChange(FIELD_BASE_URL, e.target.value)}
              autoComplete="off"
              aria-label="Organisation URL"
              className="h-10"
            />
            {orgPhase.state === "error" ? (
              <StepNote action="Try again" onAction={() => void loadOrgs()}>
                {orgPhase.message}
              </StepNote>
            ) : orgPhase.state === "unsupported" ? (
              <StepNote>
                Paste the organisation or project URL — a project URL works too.
              </StepNote>
            ) : (
              <StepNote
                action="Choose from a list"
                onAction={() => setOrgManual(false)}
              >
                Paste the organisation or project URL.
              </StepNote>
            )}
          </>
        ) : (
          <>
            <Dropdown
              ddKey={`ado-org-${connection.id}`}
              heading="ORGANISATION"
              width={280}
              value={baseUrl || null}
              items={orgItems}
              onSelect={(url) => {
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
            {orgPhase.state === "ready" && orgs.length === 0 ? (
              <StepNote action="Enter it manually" onAction={() => setOrgManual(true)}>
                This token cannot see any organisations.
              </StepNote>
            ) : (
              <StepNote action="Enter it manually" onAction={() => setOrgManual(true)}>
                Listed from your token.
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
                action="Try again"
                onAction={() => void loadProjects(connection.savedBaseUrl)}
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
