// Project detail › Settings › the destructive action (issue #64).
//
// Not in the handoff — there was no delete endpoint when it was written, so a
// mistaken project was permanent. `DELETE /projects/{key}` now exists and this
// is its one entry point.
//
// Two deliberate frictions, both from the handoff's destructive-action styling
// (rose text on a rose tint, `Button variant="destructive"`):
//
//   • the action is behind a two-step reveal, so the button is never one
//     mis-click away from destroying a configuration;
//   • confirmation is **type the project key**, not an "Are you sure?". The key
//     is what every agent addresses the project by, so typing it is a
//     meaningful act of identification rather than a reflex.
//
// The hub refuses with 409 while work items still mirror into the project; that
// message says what to do next, so it is surfaced verbatim rather than
// paraphrased into "Could not delete".

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, GlassCard, Icon, Input, Notice, Spinner, toast } from "@/components/ui";
import { deleteProject, type Project } from "@/data";
import { ApiError } from "@/lib/api";

export function DangerZone({ project }: { project: Project }) {
  const navigate = useNavigate();
  const [armed, setArmed] = useState(false);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const confirmed = typed.trim() === project.id;

  const disarm = () => {
    setArmed(false);
    setTyped("");
    setError("");
  };

  const remove = async () => {
    if (!confirmed) return;
    setDeleting(true);
    setError("");
    try {
      await deleteProject(project.id);
      toast("Project deleted", "warn");
      navigate("/app/projects");
    } catch (err) {
      // The hub's own sentence, whatever it is — the 409 explains the fix.
      setError(
        err instanceof ApiError
          ? err.message
          : "The hub did not respond. Try again in a moment.",
      );
      setDeleting(false);
    }
  };

  return (
    <GlassCard className="rounded-[20px] border-danger/25 p-[22px]">
      <div className="flex items-center gap-[14px]">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-button border border-danger/30 bg-danger-tint text-danger">
          <Icon name="trash" size={18} strokeWidth={2.1} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
            Delete this project
          </div>
          <div className="mt-[3px] text-[12.5px] text-muted text-pretty">
            Removes the registry entry, its configuration and test accounts, and
            every knowledge base built for it. This cannot be undone.
          </div>
        </div>
        {!armed && (
          <Button variant="destructive" onClick={() => setArmed(true)}>
            Delete project
          </Button>
        )}
      </div>

      {armed && (
        <div className="mt-4 border-t border-danger/20 pt-4">
          <Input
            label="TYPE THE PROJECT KEY TO CONFIRM"
            placeholder={project.id}
            mono
            autoFocus
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />

          {error && (
            <Notice tone="danger" className="mt-3">
              {error}
            </Notice>
          )}

          <div className="mt-3 flex gap-2.5">
            <Button
              variant="destructive"
              disabled={!confirmed || deleting}
              icon={
                deleting ? (
                  <Spinner size={14} speed="run" />
                ) : (
                  <Icon name="trash" size={14} />
                )
              }
              onClick={() => void remove()}
            >
              {deleting ? "Deleting…" : `Delete ${project.name}`}
            </Button>
            <Button variant="ghost" disabled={deleting} onClick={disarm}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </GlassCard>
  );
}
